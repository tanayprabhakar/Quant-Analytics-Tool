
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, engine):
        self.engine = engine
        
    def fetch_data(self, start_date, end_date):
        # Buffer for lookback (e.g. 365 days)
        query_start = pd.to_datetime(start_date) - timedelta(days=400)
        
        # Fetch Price
        query = text("""
            SELECT date, symbol, close 
            FROM price_daily 
            WHERE date >= :start AND date <= :end
            ORDER BY date ASC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"start": query_start, "end": end_date})
            
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
            
        prices = df.pivot(index="date", columns="symbol", values="close")
        prices.index = pd.to_datetime(prices.index)
        prices = prices.ffill() # Fill missing
        
        # Fetch Fundamentals (All history available)
        f_query = text("""
            SELECT symbol, as_of_date, pe_ratio, market_cap 
            FROM fundamentals_snapshot
            ORDER BY as_of_date ASC
        """)
        with self.engine.connect() as conn:
            fund_df = pd.read_sql(f_query, conn)
            
        if not fund_df.empty:
            fund_df["as_of_date"] = pd.to_datetime(fund_df["as_of_date"])
            
        return prices, fund_df

    def run_simulation(self, params):
        try:
            factor = params.get("factor", "momentum")
            lookback = int(params.get("lookback_days", 90))
            top_n = int(params.get("top_n", 10))
            start_date = pd.to_datetime(params.get("start", "2023-01-01"))
            end_date = pd.to_datetime(params.get("end", datetime.now()))
            rebalance_freq = params.get("rebalance", "monthly")
            
            prices, fundamentals = self.fetch_data(start_date, end_date)
            
            if prices.empty:
                return {"error": "No price data available"}
                
            # Restrict prices to simulation range? No, keeps lookback
            # Determine Rebalance Schedule
            freq_map = {"monthly": "ME", "quarterly": "QE", "weekly": "W-FRI"}
            freq = freq_map.get(rebalance_freq, "ME")
            
            # Generate rebalance dates within START-END
            rebal_dates = pd.date_range(start=start_date, end=end_date, freq=freq)
            # Ensure start_date is included if not covered? 
            # Usually we rebalance AT start_date.
            if start_date not in rebal_dates:
                # Add start_date to rebal list logic? 
                # safer: ensure first rebal is start_date
                pass

            # Make Weights DataFrame (Daily)
            weights = pd.DataFrame(index=prices.index, columns=prices.columns).fillna(0.0)
            
            # Helper to get valid rebal dates that exist in price index
            # map rebal_dates to nearest trading day (backward or forward?)
            # Usually backward (known prices)
            
            # Clean rebal schedule:
            # For each intended rebal date, find index <= date
            
            # State
            current_weights = pd.Series(0.0, index=prices.columns)
            
            sim_prices = prices[prices.index >= (start_date - timedelta(days=lookback*2))] # Optimization
            
            # Loop strictly over rebal dates that are >= start_date
            active_dates = [d for d in rebal_dates if d >= start_date]
            if not active_dates and start_date < end_date:
                active_dates = [start_date] # Single rebal
            elif active_dates[0] > start_date:
                active_dates.insert(0, start_date)

            for date in active_dates:
                if date > end_date: break
                
                # Find observation day (on or before date)
                valid_days = sim_prices.index[sim_prices.index <= date]
                if valid_days.empty: continue
                obs_date = valid_days[-1]
                
                # Get history slice for Lookback
                # Slice: obs_date - lookback -> obs_date
                # Find loc
                loc = sim_prices.index.get_loc(obs_date)
                start_loc = max(0, loc - lookback)
                hist = sim_prices.iloc[start_loc : loc+1] # Include obs_date
                
                selected = []
                
                if factor == "momentum":
                    if len(hist) > 1:
                        # Return: Latest / First - 1
                        # Wait, hist is prices.
                        ret = (hist.iloc[-1] / hist.iloc[0]) - 1
                        # Drop NaNs
                        ret = ret.dropna()
                        # Sort Descending
                        selected = ret.sort_values(ascending=False).head(top_n).index.tolist()
                        
                elif factor == "low-vol":
                    if len(hist) > 10:
                        # Log returns
                        lrets = np.log(hist / hist.shift(1))
                        vol = lrets.std()
                        # Sort Ascending (Low Vol)
                        vol = vol.dropna()
                        selected = vol.sort_values(ascending=True).head(top_n).index.tolist()
                        
                elif factor == "value":
                    if not fundamentals.empty:
                        # Point-in-time filter
                        # Fundamentals known BY obs_date
                        valid = fundamentals[fundamentals["as_of_date"] <= obs_date]
                        if not valid.empty:
                            latest = valid.sort_values("as_of_date").groupby("symbol").last()
                            pe = latest["pe_ratio"].dropna()
                            # PE > 0 usually
                            pe = pe[pe > 0]
                            # Sort Ascending (Low PE)
                            selected = pe.sort_values(ascending=True).head(top_n).index.tolist()

                # Assign Weights (Equal Weight)
                # Filter selected to those in prices.columns
                valid_selected = [s for s in selected if s in prices.columns]
                
                if valid_selected:
                    w = 1.0 / len(valid_selected)
                    # Create series
                    new_w = pd.Series(0.0, index=prices.columns)
                    new_w.loc[valid_selected] = w
                    
                    # Set weight at this date in the DataFrame
                    # We utilize ffill later, so just setting at idx is enough?
                    # Problem: rebal date might not be in index exactly if weekend.
                    # use obs_date (trading day)
                    weights.loc[obs_date] = new_w

            # Propagate weights forward (ffill)
            weights = weights.replace(0.0, np.nan) # trick to ffill
            weights = weights.ffill().fillna(0.0)
            
            # Lag weights by 1 day (Execution T+1)
            # Signal generated at Close of T. Holdings start T+1.
            weights = weights.shift(1).fillna(0.0)
            
            # Filter to Simulation Range
            weights = weights[(weights.index >= start_date) & (weights.index <= end_date)]
            sim_daily_prices = prices[(prices.index >= start_date) & (prices.index <= end_date)]
            
            # Ensure consistency
            common_idx = weights.index.intersection(sim_daily_prices.index)
            weights = weights.loc[common_idx]
            sim_daily_prices = sim_daily_prices.loc[common_idx]
            
            # Calculate Daily Returns
            rets = sim_daily_prices.pct_change().fillna(0.0)
            
            # Portfolio Return = row sum (weight * return)
            # Assuming rebalance maintains weights? No, simplistic daily rebal approach:
            # Strategy Return = Sum(w_prev * r_t)
            strat_ret = (weights * rets).sum(axis=1)
            
            # Calculate Equity Curve
            equity_curve = (1 + strat_ret).cumprod()
            
            # Benchmark (Equal Weight Universe)
            # Average returns of all stocks available
            bench_ret = rets.mean(axis=1) # NaNs handled? sum/count
            bench_curve = (1 + bench_ret).cumprod()
            
            # Metrics
            total_ret = equity_curve.iloc[-1] - 1 if not equity_curve.empty else 0
            days = (end_date - start_date).days
            years = days / 365.25
            cagr = ((total_ret + 1) ** (1/years)) - 1 if years > 0 else 0
            
            valid_rets = strat_ret[strat_ret != 0]
            vol = valid_rets.std() * np.sqrt(252) if not valid_rets.empty else 0
            sharpe = (cagr - 0.05) / vol if vol > 0 else 0 # Rf=5% assumption
            
            # Drawdown
            rolling_max = equity_curve.cummax()
            drawdown = (equity_curve - rolling_max) / rolling_max
            max_dd = drawdown.min()
            
            # Convert curves for JSON
            curves = []
            # reduce points for UI? 
            # Send all daily
            for d in equity_curve.index:
                curves.append({
                    "date": d.strftime("%d-%m-%Y"),
                    "portfolio": round(float(equity_curve.loc[d]), 4),
                    "benchmark": round(float(bench_curve.loc[d]) if not bench_curve.empty else 1.0, 4)
                })
                
            return {
                "summary": {
                    "cagr": round(cagr, 4),
                    "volatility": round(vol, 4),
                    "sharpe": round(sharpe, 4),
                    "max_drawdown": round(max_dd, 4)
                },
                "equity_curve": curves,
                "holdings_count": int(top_n) # static
            }

        except Exception as e:
            logger.error(f"Backtest Error: {e}", exc_info=True)
            return {"error": str(e)}

def do_backtest(engine, params):
    bt = BacktestEngine(engine)
    return bt.run_simulation(params)
