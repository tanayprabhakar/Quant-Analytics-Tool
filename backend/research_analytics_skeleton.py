
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import logging
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, engine):
        self.engine = engine
        
    def fetch_price_history(self, start_date, end_date):
        """Fetch ALL daily prices for universe within range + lookback buffer"""
        # Buffer for lookback (e.g. 365 days)
        query_start = pd.to_datetime(start_date) - timedelta(days=400)
        
        query = text("""
            SELECT date, symbol, close 
            FROM price_daily 
            WHERE date >= :start AND date <= :end
            ORDER BY date ASC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"start": query_start, "end": end_date})
            
        if df.empty:
            return pd.DataFrame()
            
        # Pivot: Index=Date, Columns=Symbol, Values=Close
        prices = df.pivot(index="date", columns="symbol", values="close")
        prices.index = pd.to_datetime(prices.index)
        return prices.ffill() # Fill missing days

    def fetch_fundamentals(self, start_date, end_date):
        """Fetch point-in-time fundamentals"""
        query = text("""
            SELECT symbol, as_of_date, pe_ratio, market_cap 
            FROM fundamentals_snapshot
            WHERE as_of_date <= :end 
            ORDER BY as_of_date ASC
        """)
        # We fetch all history because we need to know the "latest known" at any point in time.
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"end": end_date})
        
        if df.empty:
            return pd.DataFrame()
        
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        return df

    def run_backtest(self, params):
        """
        params: factor (momentum/low-vol/value), lookback (int), top_n (int), 
                rebalance_freq (monthly), start, end
        """
        start_date = pd.to_datetime(params["start"])
        end_date = pd.to_datetime(params["end"])
        factor = params["factor"]
        top_n = params["top_n"]
        lookback = params.get("lookback_days", 90)
        
        # 1. Load Data
        prices = self.fetch_price_history(start_date, end_date)
        if prices.empty:
            return {"error": "No price data found"}
            
        fundamentals = None
        if factor == "value":
            fundamentals = self.fetch_fundamentals(start_date, end_date)
            if fundamentals.empty:
                return {"error": "No fundamental data found for Value factor"}

        # 2. Define Rebalance Dates (Monthly)
        # Get business month ends in range
        rebalance_dates = pd.date_range(start=start_date, end=end_date, freq="ME")
        
        portfolio_curve = [] # [{date, value}]
        benchmark_curve = [] # [{date, value}]
        
        current_capital = 1.0
        details = []

        # Benchmark: NIFTY if avail, else Equal Weight Universe
        # We'll calculate Equal Weight Universe dynamically.
        
        # Simulation Loop
        # We need daily returns to track portfolio value between rebalances.
        # But efficiently: Calculate portfolio at T, hold until T+1, apply returns.
        
        # Filter prices to evaluation range
        eval_prices = prices[prices.index >= start_date]
        if eval_prices.empty:
             return {"error": "Start date is after available data"}
             
        # Initialize
        holding_symbols = []
        
        # For simplicity, we iterate day by day? deeply slow.
        # Vectorized is hard with changing portfolio.
        # Chunk based on rebalance dates.
        
        # Add Start Date as first rebalance if not in list (to initialize)
        if start_date not in rebalance_dates:
            rebalance_dates = rebalance_dates.insert(0, start_date)
            rebalance_dates = rebalance_dates.sort_values()

        # Helper to get valid trading day
        valid_days = prices.index
        
        # Calculate Daily Returns for all stocks
        daily_returns = prices.pct_change()
        
        # Prepare Result Series
        portfolio_equity = pd.Series(index=eval_prices.index, dtype=float)
        portfolio_equity.iloc[0] = 1.0
        
        # Benchmark (Equal Weight of all cols)
        # Limit to those alive? `daily_returns.mean(axis=1)` handles NaNs (dead/not-born stocks)
        benchmark_returns = daily_returns.mean(axis=1)
        # Apply to curve (cumprod)
        benchmark_equity = (1 + benchmark_returns.loc[start_date:]).cumprod()
        # Normalize to 1.0
        if not benchmark_equity.empty:
             benchmark_equity = benchmark_equity / benchmark_equity.iloc[0]

        # Simulation
        holdings = []
        
        for i in range(len(rebalance_dates)):
            date = rebalance_dates[i]
            next_date = rebalance_dates[i+1] if i < len(rebalance_dates)-1 else end_date
            
            # 1. Ranking (at `date`)
            # Ensure we look strictly safely.
            # Momentum: Returns over lookback, excluding last 1 month? Or just t-lookback to t? 
            # BQuant standard: t-12m to t-1m? 
            # User simply asked "Momentum lookback: 30/60/90". Usually standard simple momentum.
            
            # Check price availability at `date` (or closest before)
            idx_loc = prices.index.get_indexer([date], method="pad")[0]
            if idx_loc < lookback: continue # detailed check
            
            curr_date_row = prices.index[idx_loc] # actual date used
            
            # Slice history for factor calc
            hist_slice = prices.iloc[idx_loc-lookback : idx_loc+1] # +1 to include today? 
            # Calculate Factor
            scores = {}
            
            if factor == "momentum":
                # (Price_t / Price_t-n) - 1
                start_p = hist_slice.iloc[0]
                end_p = hist_slice.iloc[-1]
                # Drop NaNs
                # Vectorized
                moms = (end_p / start_p) - 1
                scores = moms.dropna()
                
            elif factor == "low-vol":
                # Std Dev of log returns
                # ln(Pt / Pt-1)
                log_rets = np.log(hist_slice / hist_slice.shift(1))
                # Annualize: std * sqrt(252)
                vol = log_rets.std() * np.sqrt(252)
                scores = vol.dropna() * -1 # Invert so higher score = better (Total Rank)
                
            elif factor == "value":
                # Use fundamentals
                # Filter fundamentals known <= date
                valid_funds = fundamentals[fundamentals["as_of_date"] <= curr_date_row]
                # Get latest for each symbol
                latest_funds = valid_funds.sort_values("as_of_date").groupby("symbol").last()
                # PE Ratio
                pes = latest_funds["pe_ratio"].dropna()
                # We need inverse PE (Earnings Yield) or just rank PE ascending
                # Score = -PE (so lower PE is higher score)
                scores = pes * -1
            
            # Rank and Select
            if hasattr(scores, "empty") and scores.empty:
                current_allocation = []
            else:
                top_stocks = scores.sort_values(ascending=False).head(top_n).index.tolist()
                current_allocation = top_stocks
                
            # Store holdings for this period
            holdings = current_allocation
            
            # 2. Performance (date to next_date)
            # Get returns for held stocks in this period
            period_returns = daily_returns.loc[date:next_date]
            if period_returns.empty: continue
            
            # Exclude start date from return application (it's the rebal date)
            # Actually, if we rebal at Close of T, we get returns from T+1.
            period_returns = period_returns.iloc[1:] 
            if period_returns.empty: continue

            # Portfolio Return = Mean of selected stocks
            # If holdings empty > cash (0 return)
            if not holdings:
                port_ret = 0.0
            else:
                # Select cols
                # check if cols exist (some might delist?)
                valid_holdings = [h for h in holdings if h in period_returns.columns]
                if not valid_holdings:
                    port_ret = 0.0
                else:
                    # Daily returns of portfolio
                    port_daily = period_returns[valid_holdings].mean(axis=1)
                    
                    # Apply to equity curve
                    # We need to chain it.
                    # slice portfolio_equity
                    # Problem: chaining daily.
                    pass

        # Re-think implementation for speed & robustness:
        # Construct a "Signal Matrix" (0/1) for dates and symbols.
        # 1. Create DataFrame `positions` same shape as `prices` (dates x symbols)
        # 2. Fill with 0.
        # 3. For each rebalance date, compute ranks, set 1 for top N cols.
        # 4. Forward fill positions until next rebalance. (rebalance='monthly')
        # 5. Shift positions by 1 day (Exec at Close -> Exposure start next Open/Close). 
        # 6. Portfolio Daily Ret = (positions * daily_returns).sum(axis=1) / positions.sum(axis=1)
        
        positions = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        
        for date in rebalance_dates:
            # logic same as above to find top_stocks
            # ... (factor calc)
            idx_loc = prices.index.get_indexer([date], method="pad")[0]
            curr_date_row = prices.index[idx_loc]
            
            hist_slice = prices.iloc[max(0, idx_loc-lookback) : idx_loc+1]
            
            selected = []
            if factor == "momentum":
                if len(hist_slice) >= lookback:
                    ret = (hist_slice.iloc[-1] / hist_slice.iloc[0]) - 1
                    selected = ret.sort_values(ascending=False).head(top_n).index.tolist()
            elif factor == "low-vol":
                 if len(hist_slice) > 10:
                    lr = np.log(hist_slice / hist_slice.shift(1))
                    vol = lr.std()
                    selected = vol.sort_values(ascending=True).head(top_n).index.tolist()
            elif factor == "value":
                 if fundamentals is not None:
                     valid = fundamentals[fundamentals["as_of_date"] <= curr_date_row]
                     if not valid.empty:
                         latest = valid.sort_values("as_of_date").groupby("symbol").last()
                         pe = latest["pe_ratio"].dropna()
                         # Filter PE > 0 usually logic for Value
                         pe = pe[pe > 0]
                         selected = pe.sort_values(ascending=True).head(top_n).index.tolist()
            
            # Set 1 for next period (until next rebal)
            if selected:
                # Find range from date to next_rebal
                # If i < last:
                # Actually, simplest: Set row at `date` = 1. Then ffill() later.
                positions.loc[date, selected] = 1.0 / len(selected) # Equal weight
        
        # Resample positions to daily (ffill)
        # But we only set them on rebal dates. 
        # Reindex positions to daily? `positions` is already daily.
        # We replace 0s with NaN to ffill? No, we initialized 0.
        # New approach: Create `weights` df sparse.
        weights = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
        
        for date in rebalance_dates:
             # ... calculation ...
             # Set weights.loc[date] = 1/N
             pass 
             
             # Optimization: Do calc inside iteration.
             
        # ... (Complete logic in actual file)
        pass 
