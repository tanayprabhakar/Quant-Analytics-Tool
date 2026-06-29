
import pandas as pd
import numpy as np
import yfinance as yf
from sqlalchemy import create_engine, text, bindparam
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PortfolioEngine:
    def __init__(self, engine):
        self.engine = engine

    def _ensure_prices(self, symbols, start_date, end_date):
        """Auto-fetch and store missing price data from Yahoo Finance."""
        all_symbols = list(set(symbols))
        query_start = pd.to_datetime(start_date) - timedelta(days=10)

        for symbol in all_symbols:
            try:
                # Check if we have data for this symbol in the date range
                check_query = text("""
                    SELECT COUNT(*) FROM price_daily
                    WHERE symbol = :symbol AND date >= :start AND date <= :end
                """)
                with self.engine.connect() as conn:
                    count = conn.execute(check_query, {
                        "symbol": symbol, "start": query_start, "end": end_date
                    }).scalar()

                if count and count > 10:
                    continue  # Sufficient data exists

                # Fetch from Yahoo Finance
                logger.info(f"Portfolio: Auto-fetching {symbol} from Yahoo Finance...")
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=query_start, end=pd.to_datetime(end_date) + timedelta(days=1))

                if hist.empty:
                    logger.warning(f"No Yahoo data for {symbol}")
                    continue

                # Store in DB
                records = []
                for idx, row in hist.iterrows():
                    records.append({
                        "symbol": symbol,
                        "date": idx.date(),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row.get("Close", 0)),
                        "volume": int(row.get("Volume", 0))
                    })

                if records:
                    insert_q = text("""
                        INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                        VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
                        ON CONFLICT (symbol, date) DO NOTHING
                    """)
                    with self.engine.begin() as conn:
                        conn.execute(insert_q, records)
                    logger.info(f"Portfolio: Stored {len(records)} records for {symbol}")

            except Exception as e:
                logger.error(f"Portfolio: Failed to fetch {symbol}: {e}")

    def fetch_data(self, symbols, benchmark_symbol, start_date, end_date):
        """Fetch daily prices for all requested symbols + benchmark."""
        all_symbols = list(set(symbols + [benchmark_symbol]))

        # Auto-fetch any missing data from Yahoo Finance
        self._ensure_prices(all_symbols, start_date, end_date)
        
        query_start = pd.to_datetime(start_date) - timedelta(days=10) # buffer for returns
        
        query = text("""
            SELECT date, symbol, close 
            FROM price_daily 
            WHERE symbol IN :symbols
            AND date >= :start AND date <= :end
            ORDER BY date ASC
        """).bindparams(bindparam("symbols", expanding=True))
        
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbols": all_symbols, "start": query_start, "end": end_date})
            
        if df.empty:
            return pd.DataFrame()
            
        prices = df.pivot(index="date", columns="symbol", values="close")
        prices.index = pd.to_datetime(prices.index)
        prices = prices.ffill() # Forward fill missing prices
        
        return prices

    def analyze_portfolio(self, params):
        try:
            symbols = params["symbols"]
            weights = params["weights"]
            start_date = pd.to_datetime(params["start"])
            end_date = pd.to_datetime(params["end"])
            benchmark_symbol = params.get("benchmark", "^NSEI")
            
            # Validation
            if abs(sum(weights) - 1.0) > 0.01:
                return {"error": "Weights must sum to 1.0"}
            
            # Map weights
            w_map = dict(zip(symbols, weights))
            
            # Fetch Data
            prices = self.fetch_data(symbols, benchmark_symbol, start_date, end_date)
            
            if prices.empty:
                return {"error": "No price data found"}
                
            # Filter to analytical range
            prices = prices[prices.index >= start_date]
            
            # Check if symbols present
            missing = [s for s in symbols if s not in prices.columns]
            if missing:
                return {"error": f"Missing data for: {missing}"}
                
            # If benchmark missing
            if benchmark_symbol not in prices.columns:
                 return {"error": f"Benchmark {benchmark_symbol} not found"}
                 
            # 1. Calculate Returns
            returns = prices.pct_change().fillna(0.0)
            
            # Portfolio Daily Returns (Daily Rebalancing Assumption)
            # R_p = w1*r1 + w2*r2 ...
            # Creates series
            port_daily_ret = pd.Series(0.0, index=returns.index)
            for sym, w in w_map.items():
                port_daily_ret += returns[sym] * w
                
            bench_daily_ret = returns[benchmark_symbol]
            
            # 2. Equity Curves
            # Base 1.0
            port_equity = (1 + port_daily_ret).cumprod()
            bench_equity = (1 + bench_daily_ret).cumprod()
            
            # 3. Summary Metrics
            days = (end_date - start_date).days
            years = days / 365.25
            
            # CAGR
            def get_cagr(series):
                total_ret = series.iloc[-1] - 1 if not series.empty else 0
                return ((total_ret + 1) ** (1/years)) - 1 if years > 0.1 else total_ret
                
            port_cagr = get_cagr(port_equity)
            bench_cagr = get_cagr(bench_equity)
            
            # Volatility (Annualized)
            port_vol = port_daily_ret.std() * np.sqrt(252)
            bench_vol = bench_daily_ret.std() * np.sqrt(252)
            
            # Beta
            # Cov(Rp, Rb) / Var(Rb)
            covariance = np.cov(port_daily_ret, bench_daily_ret)[0][1]
            variance = np.var(bench_daily_ret)
            beta = covariance / variance if variance > 0 else 1.0
            
            # Max Drawdown
            roll_max = port_equity.cummax()
            dd = (port_equity - roll_max) / roll_max
            max_dd = dd.min()
            
            # 4. Attribution Analysis (Risk & Return)
            attribution = []
            
            # Correlation Matrix (of constituent stocks only)
            stock_returns = returns[symbols]
            corr_matrix_df = stock_returns.corr()
            
            # Risk Attribution (Marginal Contribution * Weight)
            # MCR_i = Cov(Ri, Rp) / Vol_p
            # We calculate cov(stock, portfolio)
            
            for sym in symbols:
                w = w_map[sym]
                r_stock = returns[sym]
                
                # Risk Contrib
                # Covariance of this stock with portfolio
                if port_vol > 0:
                    cov_s_p = np.cov(r_stock, port_daily_ret)[0][1]
                    # Marginal Contribution to Risk
                    mcr = cov_s_p / (port_daily_ret.std() + 1e-9) # using std dev (not annualized here usually, but ratio same)
                    # Contribution = w * MCR
                    risk_contrib = w * mcr
                    # Normalize: Risk Contrib Sum should equal Portfolio Vol (roughly)
                    # Actually, Sum(w * MCR) = Sigma_p.
                    # Let's provide % contribution? Or absolute? 
                    # Prompt output example: "risk_contribution": 0.32 (seems absolute or ratio?)
                    # If vol is 0.19, maybe 0.32 is high? Or 32%?
                    # Let's standardize to Absolute contribution to Annualized Vol.
                    # MCR (Annualized) = MCR_daily * sqrt(252)
                    mcr_ann = mcr * np.sqrt(252)
                    abs_risk_contrib = w * mcr_ann
                else:
                    abs_risk_contrib = 0.0
                    
                # Return Attribution
                # Simple: Weight * Cumulative Return of Stock? 
                # Or Weight * CAGR of Stock?
                # Best for daily reval: Sum(w * r_i_t) over time.
                # Total Return Contribution = Sum(w * r_i_t)
                # This equals Weight * (Simple Cumulative Return of Stock? No.)
                # It equals Weight * Sum(r_i).
                # Actually, Total Portfolio Return = Sum(contribs).
                # Contrib = Sum(w * r_i_t).
                contrib_series = r_stock * w
                # Geometric linking is tricky.
                # Arithmetic approximation: Sum(daily contribs).
                ret_contrib = contrib_series.sum() 
                # This is arithmetic return contribution.
                # It won't match CAGR perfectly, but explains "Total Arithmetic Return".
                # For coherence, let's use: Contribution to Cumulative Return?
                # Prompt: "Contribution to return by stock". "return_contribution": 0.07 (implies 7%)
                
                attribution.append({
                    "symbol": sym,
                    "return_contribution": round(ret_contrib, 4),
                    "risk_contribution": round(abs_risk_contrib, 4)
                })
                
            # 5. Format Output
            
            # Equity Curve JSON
            curve = []
            for d in port_equity.index:
                curve.append({
                    "date": d.strftime("%d-%m-%Y"),
                    "portfolio": round(float(port_equity.loc[d]), 4),
                    "benchmark": round(float(bench_equity.loc[d]), 4)
                })
                
            # Corr Matrix
            corr_matrix = []
            for r in corr_matrix_df.index:
                row = {"symbol": r}
                for c in corr_matrix_df.columns:
                    row[c] = round(corr_matrix_df.loc[r, c], 2)
                corr_matrix.append(row)

            return {
                "summary": {
                    "cagr": round(port_cagr, 4),
                    "volatility": round(port_vol, 4),
                    "beta": round(beta, 4),
                    "max_drawdown": round(max_dd, 4)
                },
                "attribution": attribution,
                "equity_curve": curve,
                "correlation_matrix": corr_matrix # List of dicts (rows)
            }
            
        except Exception as e:
            logger.error(f"Portfolio Analysis Error: {e}", exc_info=True)
            return {"error": str(e)}

def analyze_portfolio_request(engine, params):
    pe = PortfolioEngine(engine)
    return pe.analyze_portfolio(params)
