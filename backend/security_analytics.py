
import pandas as pd
import numpy as np
import logging
from sqlalchemy import Engine, text
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf

logger = logging.getLogger(__name__)

def calculate_beta(stock_returns: pd.Series, market_returns: pd.Series) -> float:
    """
    Calculate Beta: Cov(stock, market) / Var(market)
    """
    if len(stock_returns) != len(market_returns) or len(stock_returns) < 30:
        return 0.0
    
    # Align indices
    common_idx = stock_returns.index.intersection(market_returns.index)
    if len(common_idx) < 30:
        return 0.0
        
    s_ret = stock_returns.loc[common_idx]
    m_ret = market_returns.loc[common_idx]
    
    covariance = np.cov(s_ret, m_ret)[0][1]
    variance = np.var(m_ret)
    
    if variance == 0:
        return 0.0
        
    return covariance / variance

def calculate_drawdown(prices: pd.Series) -> float:
    """
    Calculate Max Drawdown over the period.
    """
    if prices.empty: return 0.0
    
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return drawdown.min()

def get_security_overview(symbol: str, engine: Engine) -> Dict:
    """
    Get comprehensive security overview: Fundamentals, Risk, Factors.
    """
    try:
        with engine.connect() as conn:
            # 1. Fetch Fundamentals
            try:
                info = yf.Ticker(symbol).info
                fundamentals = {
                    "market_cap": info.get("marketCap", 0),
                    "pe_ratio": info.get("trailingPE", 0) or info.get("forwardPE", 0) or 0,
                    "sector": info.get("sector", "N/A"),
                    "eps": info.get("trailingEps", 0) or 0,
                    "name": info.get("shortName", symbol)
                }
            except Exception as e:
                logger.warning(f"Failed to fetch fundamentals for {symbol}: {e}")
                fundamentals = {
                    "market_cap": 0,
                    "pe_ratio": 0,
                    "sector": "N/A",
                    "eps": 0,
                    "name": symbol.replace(".NS", "")
                }
            
            # 2. Risk Metrics (Based on DB prices)
            # Fetch last 1 year of data for Stock AND Benchmark (^NSEI)
            query = text("""
                SELECT date, symbol, close
                FROM price_daily
                WHERE symbol IN (:symbol, '^NSEI')
                ORDER BY date ASC
            """)

            
            df = pd.read_sql(query, conn, params={"symbol": symbol})
            df["date"] = pd.to_datetime(df["date"])
            
            pivoted = df.pivot(index="date", columns="symbol", values="close").ffill()
            
            if symbol not in pivoted.columns or "^NSEI" not in pivoted.columns:
                return {"error": "Insufficient data"}
                
            stock_prices = pivoted[symbol] if symbol in pivoted.columns else pd.Series()
            market_prices = pivoted["^NSEI"] if "^NSEI" in pivoted.columns else pd.Series()
            
            # Check Benchmark Sufficiency (Need ~5 years for robust charts/stats)
            bench_count = len(market_prices)
            stock_count = len(stock_prices)
            
            logger.info(f"Data check for {symbol}: stock={stock_count} rows, bench={bench_count} rows")
            
            if bench_count < 1200:
                 logger.info(f"Insufficient benchmark data (^NSEI, rows={bench_count}). Fetching...")
                 try:
                    from app import store_prices
                    
                    bench = yf.Ticker("^NSEI")
                    bench_hist = bench.history(period="5y")
                    if not bench_hist.empty:
                        store_prices(bench_hist, "^NSEI")
                        logger.info(f"Stored {len(bench_hist)} records for ^NSEI")
                        # Re-fetch everything with NEW connection
                        df = pd.read_sql(query, conn, params={"symbol": symbol})
                        df["date"] = pd.to_datetime(df["date"])
                        pivoted = df.pivot(index="date", columns="symbol", values="close").ffill()
                        stock_prices = pivoted[symbol] if symbol in pivoted.columns else pd.Series()
                        market_prices = pivoted["^NSEI"] if "^NSEI" in pivoted.columns else pd.Series()
                        logger.info(f"After re-fetch: stock={len(stock_prices)}, bench={len(market_prices)}")
                 except Exception as b_err:
                     logger.error(f"Benchmark ingestion failed: {b_err}")
            
            # Returns
            # Check Data Sufficiency (Need > 1 year for Beta/Drawdown, prefer 5y)
            if stock_count < 1200:
                logger.info(f"Insufficient data for {symbol} (rows={stock_count}). Fetching from Yahoo...")
                try:
                    from app import store_prices
                    
                    stk = yf.Ticker(symbol)
                    hist = stk.history(period="5y")
                    if not hist.empty:
                        store_prices(hist, symbol)
                        # CRITICAL: Re-fetch data from DB to use the newly stored records
                        df = pd.read_sql(query, conn, params={"symbol": symbol})
                        df["date"] = pd.to_datetime(df["date"])
                        
                        # Re-pivot
                        if not df.empty:
                             pivoted = df.pivot(index="date", columns="symbol", values="close").ffill()
                             stock_prices = pivoted[symbol] if symbol in pivoted.columns else pd.Series()
                             market_prices = pivoted["^NSEI"] if "^NSEI" in pivoted.columns else pd.Series()
                             
                except Exception as s_err:
                     logger.error(f"Stock ingestion failed: {s_err}")

            if stock_prices.empty or market_prices.empty:
                 return {
                    "symbol": symbol,
                    "error": "Insufficient data even after fetch attempt",
                    "fundamentals": fundamentals,
                    # Return safe defaults
                    "risk": {"beta": 0, "volatility_30d": 0, "max_drawdown_1y": 0},
                    "factors": {"momentum_90d": 0, "momentum_percentile": 0}
                }

            # Calculations
            # Beta
            beta = 0.0
            if len(stock_prices) > 20 and len(market_prices) > 20:
                # Align dates
                common_index = stock_prices.index.intersection(market_prices.index)
                if len(common_index) > 20:
                    s_ret = stock_prices.loc[common_index].pct_change().dropna()
                    m_ret = market_prices.loc[common_index].pct_change().dropna()
                    
                    # Re-align after pct_change
                    common_ret_idx = s_ret.index.intersection(m_ret.index)
                    s_ret = s_ret.loc[common_ret_idx]
                    m_ret = m_ret.loc[common_ret_idx]
                    
                    if len(m_ret) > 10:
                        cov = np.cov(s_ret, m_ret)[0, 1]
                        var = np.var(m_ret)
                        if var > 0:
                            beta = cov / var

            # Volatility (30D)
            vol_30d = 0.0
            if len(stock_prices) > 30:
                s_ret_30 = stock_prices.pct_change().tail(30).dropna()
                if len(s_ret_30) > 10:
                     vol_30d = s_ret_30.std() * np.sqrt(252)
            
            # Drawdown (1Y)
            max_dd = calculate_drawdown(stock_prices)
            
            # 3. Factor Exposure & Percentile (30D & 90D)
            # Fetch latest momentum scores for ALL stocks to rank this one
            # combining queries for 30 and 90
            mom_query = text("""
                SELECT symbol, momentum_score, lookback_days
                FROM factor_momentum
                WHERE lookback_days IN (30, 90)
                AND as_of_date >= (current_date - INTERVAL '5 days') 
            """)
            # Note: The subquery MAX(date) might differ per lookback, so using a recent window is safer or window functions.
            # Simplified: Just get recent scores.
            
            mom_df = pd.read_sql(mom_query, conn)
            
            # Helper to get score and rank
            def get_mom_stats(lookup_days):
                subset = mom_df[mom_df["lookback_days"] == lookup_days]
                if subset.empty: return 0.0, 0.0
                
                # Rank
                s_row = subset[subset["symbol"] == symbol]
                if s_row.empty: return 0.0, 0.0
                
                score = s_row.iloc[0]["momentum_score"]
                # Percentile
                below = (subset["momentum_score"] < score).sum()
                rank = (below / len(subset)) * 100
                return score, rank

            mom_30, rank_30 = get_mom_stats(30)
            mom_90, rank_90 = get_mom_stats(90)
            
            # Trend Heuristic: Accelerating (30 > 90) vs Decelerating
            # Or simplified: if Positive momentum -> Rising, Negative -> Falling.
            # Better: Compare 30d vs 90d.
            trend = "Flat"
            if mom_30 > mom_90 + 0.05: trend = "Rising" # Accelerating
            elif mom_30 < mom_90 - 0.05: trend = "Falling" # Decelerating
            elif mom_90 > 0: trend = "Rising" # Both positive and similar
            else: trend = "Falling"

            # 1D Return
            ret_1d = 0.0
            last_close = 0.0
            if len(stock_prices) >= 2:
                last_close = stock_prices.iloc[-1]
                prev_close = stock_prices.iloc[-2]
                ret_1d = (last_close - prev_close) / prev_close
            elif len(stock_prices) == 1:
                last_close = stock_prices.iloc[-1]

            return {
                "symbol": symbol,
                "as_of": datetime.now().strftime("%d-%m-%Y"),
                "header": {
                    "name": fundamentals.get("name", symbol),
                    "sector": fundamentals.get("sector", "N/A"),
                    "market_cap": fundamentals.get("market_cap", 0),
                    "last_close": round(float(last_close), 2),
                    "return_1d": round(float(ret_1d * 100), 2)
                },
                "fundamentals": {
                    "market_cap": fundamentals.get("market_cap", 0),
                    "pe_ratio": fundamentals.get("pe_ratio", 0),
                    "eps": fundamentals.get("eps", 0)
                },
                "risk": {
                    "beta": round(float(beta), 2),
                    "volatility_30d": round(float(vol_30d * 100), 2),
                    "max_drawdown_1y": round(float(max_dd * 100), 2)
                },
                "factors": {
                    "momentum_30d": round(float(mom_30), 4),
                    "momentum_90d": round(float(mom_90), 4),
                    "momentum_percentile": round(float(rank_90), 1), # Using 90d as primary rank
                    "trend": trend
                }
            }
            
    except Exception as e:
        logger.error(f"Error in security overview: {e}")
        return {"error": str(e)}

def get_security_performance(symbol: str, engine: Engine) -> Dict:
    """
    Get price history with SMAs for charting.
    """
    try:
        query = text("""
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = :symbol
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": symbol})
            
        if df.empty or len(df) < 1000:
             # Auto-ingest for chart as well (Ensure 5y depth)
             try:
                from app import store_prices
                
                stk = yf.Ticker(symbol)
                hist = stk.history(period="5y")
                if not hist.empty:
                    store_prices(hist, symbol)
                    # Re-fetch
                    with engine.connect() as conn:
                         df = pd.read_sql(query, conn, params={"symbol": symbol})
             except Exception as e:
                logger.error(f"Chart auto-ingest failed: {e}")

        if df.empty:
            return {"symbol": symbol, "data": []}

        # Date conversion - MUST happen before string conversion
        df["date"] = pd.to_datetime(df["date"])
        
        # To do relative performance, we need the benchmark price series.
        # Fetch Benchmark
        bench_query = text("""
            SELECT date, close 
            FROM price_daily 
            WHERE symbol = '^NSEI' 
            AND date >= :start_date
            ORDER BY date ASC
        """)
        # Match dates
        start_date = df["date"].min()
        with engine.connect() as conn:
            bench_df = pd.read_sql(bench_query, conn, params={"start_date": start_date})
            
        # Convert bench dates to datetime BEFORE merge
        bench_df["date"] = pd.to_datetime(bench_df["date"])
        
        # Calculate SMAs BEFORE merge (on stock data)
        df["sma_50"] = df["close"].rolling(window=50).mean()
        df["sma_200"] = df["close"].rolling(window=200).mean()
        
        # Merge - both date columns are now datetime64
        merged = pd.merge(df, bench_df, on="date", how="left", suffixes=("", "_bench"))
        
        # Calculate Relative (Normalized to 1.0 at start)
        if not merged.empty and "close_bench" in merged.columns:
            # Forward fill benchmark gaps
            merged["close_bench"] = merged["close_bench"].ffill()
            
            # Normalize
            base_stock = merged["close"].iloc[0]
            base_bench = merged["close_bench"].iloc[0]
            
            if base_stock > 0 and base_bench > 0:
                merged["stock_normalized"] = merged["close"] / base_stock
                merged["bench_normalized"] = merged["close_bench"] / base_bench
                merged["relative_perf"] = merged["stock_normalized"] / merged["bench_normalized"]
            else:
                merged["relative_perf"] = 1.0
        else:
             merged["relative_perf"] = 1.0

        # Convert date to string for JSON (do this LAST)
        merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")

        # Clean NaN values for JSON (Pandas NaN -> None)
        df_clean = merged.astype(object).where(pd.notnull(merged), None)
        
        return {
            "symbol": symbol,
            "benchmark": "^NSEI",
            "data": df_clean.to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Error in security performance: {e}")
        return {}
