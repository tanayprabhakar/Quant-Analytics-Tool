
import pandas as pd
import numpy as np
import logging
from sqlalchemy import Engine, text
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def get_market_summary(engine: Engine, benchmark_symbol: str = "^NSEI") -> Dict:
    """
    Compute Market Summary (Returns & Volatility) for the benchmark.
    Returns: { "as_of": ..., "benchmark": ..., "returns": {...}, "volatility": {...} }
    """
    try:
        # Fetch benchmark data (last 365 days)
        query = text("""
            SELECT date, close
            FROM price_daily
            WHERE symbol = :symbol
            AND date >= current_date - INTERVAL '730 days'
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": benchmark_symbol})
            
        if df.empty:
            # Auto-ingestion for Benchmark if missing
            try:
                import yfinance as yf
                from app import store_prices # Import helper to save to DB
                
                logger.info(f"Benchmark {benchmark_symbol} missing in DB. Fetching from Yahoo...")
                ticker = yf.Ticker(benchmark_symbol)
                history = ticker.history(period="2y") # Fetch enough for YTD and Volatility
                
                if not history.empty:
                    store_prices(history, benchmark_symbol)
                    
                    # Re-fetch from DB to ensure consistency
                    with engine.connect() as conn:
                        df = pd.read_sql(query, conn, params={"symbol": benchmark_symbol})
            except Exception as e:
                logger.error(f"Failed to ingest benchmark {benchmark_symbol}: {e}")

        if df.empty:
            return {
                "as_of": datetime.now().strftime("%d-%m-%Y"),
                "benchmark": benchmark_symbol,
                "returns": {"1D": 0, "1W": 0, "1M": 0, "YTD": 0},
                "volatility": {"30D": 0, "90D": 0}
            }

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        
        last_date = df.index[-1]
        last_close = df["close"].iloc[-1]
        
        # Helper for returns
        def get_ret(lookback_days):
            # Simple trading day lookback (iloc)
            if len(df) <= lookback_days: return 0.0
            prev_close = df["close"].iloc[-(lookback_days + 1)]
            return (last_close / prev_close) - 1

        # Helper for YTD
        ytd_start = datetime(last_date.year, 1, 1)
        ytd_df = df[df.index >= ytd_start]
        if not ytd_df.empty:
             first_close_ytd = ytd_df["close"].iloc[0]
             ret_ytd = (last_close / first_close_ytd) - 1
        else:
             ret_ytd = 0.0

        # Helper for Volatility (Log Returns)
        df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
        
        def get_vol(window):
            if len(df) < window: return 0.0
            std_dev = df["log_ret"].tail(window).std()
            return std_dev * np.sqrt(252)

        return {
            "as_of": last_date.strftime("%d-%m-%Y"),
            "benchmark": benchmark_symbol,
            "returns": {
                "1D": round(float(get_ret(1) * 100), 2),
                "1W": round(float(get_ret(5) * 100), 2),
                "1M": round(float(get_ret(21) * 100), 2),
                "YTD": round(float(ret_ytd * 100), 2)
            },
            "volatility": {
                "30D": round(float(get_vol(30)), 2),
                "90D": round(float(get_vol(90)), 2)
            }
        }
    except Exception as e:
        logger.error(f"Error in market summary: {e}")
        return {}

def get_market_breadth(engine: Engine) -> Dict:
    """
    Compute Market Breadth: Advancers, Decliners, DMA stats, Momentum stats.
    """
    try:
        # We need a snapshot of the latest state for ALL stocks.
        # This is expensive if we query full history for everyone.
        # Strategy:
        # A) Advancers/Decliners: Need Close(T) and Close(T-1) for all stocks.
        # B) DMA: Need Close(T) and AVG(Close, 50).
        # C) Momentum: Join with factor_momentum table.

        # Efficient Query for A & B using Window Functions?
        # Or fetch last 50 days for all stocks and compute in Pandas?
        # Fetching ~50 days * ~50 stocks = 2500 rows. Fast in Pandas.
        
        query = text("""
            SELECT date, symbol, close
            FROM price_daily
            WHERE date >= current_date - INTERVAL '90 days'
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
            
        if df.empty:
            return {}
            
        df["date"] = pd.to_datetime(df["date"])
        
        # Latest date in dataset
        latest_date = df["date"].max()
        
        # Pivot date x symbol
        # This aligns dates for all stocks
        pivoted = df.pivot(index="date", columns="symbol", values="close")
        pivoted = pivoted.ffill() # Ensure continuity
        
        if pivoted.empty:
             return {}

        # 1. Advancers/Decliners (Last row vs 2nd Last row)
        current_prices = pivoted.iloc[-1]
        if len(pivoted) > 1:
            prev_prices = pivoted.iloc[-2]
            change = current_prices - prev_prices
            advancers = (change > 0).sum()
            decliners = (change < 0).sum()
        else:
            advancers = 0
            decliners = 0
            
        # 2. % Above 50 DMA
        # Compute rolling mean on pivoted data
        ma_50 = pivoted.rolling(window=50).mean().iloc[-1]
        # Only consider stocks that actually exist today (not NaN)
        valid_stocks = current_prices.dropna().index
        
        above_dma_count = 0
        total_valid = 0
        
        for sym in valid_stocks:
             price = current_prices[sym]
             dma = ma_50[sym]
             if pd.notna(dma):
                 total_valid += 1
                 if price > dma:
                     above_dma_count += 1
                     
        pct_above_50 = (above_dma_count / total_valid * 100) if total_valid > 0 else 0.0
        
        # 3. % Positive Momentum
        # Fetch latest momentum from factor_momentum table
        # We want 30-day momentum (approx '1mo lookback' in factor table?)
        # User Req: "Momentum must come from factor_momentum (lookback = 30)"
        
        mom_query = text("""
            SELECT symbol, momentum_score
            FROM factor_momentum
            WHERE lookback_days = 30
            AND as_of_date = (SELECT MAX(as_of_date) FROM factor_momentum WHERE lookback_days = 30)
        """)
        
        with engine.connect() as conn:
            mom_df = pd.read_sql(mom_query, conn)
            
        if not mom_df.empty:
            pos_mom_count = (mom_df["momentum_score"] > 0).sum()
            total_mom = len(mom_df)
            pct_pos_mom = (pos_mom_count / total_mom * 100) if total_mom > 0 else 0.0
        else:
            pct_pos_mom = 0.0

        return {
            "as_of": latest_date.strftime("%d-%m-%Y"),
            "advancers": int(advancers),
            "decliners": int(decliners),
            "percent_above_50dma": round(pct_above_50, 1),
            "percent_positive_30d_momentum": round(pct_pos_mom, 1)
        }

    except Exception as e:
        logger.error(f"Error in market breadth: {e}")
        return {}

def get_leaders_laggards(engine: Engine) -> Dict:
    """
    Get top 5 gainers and losers (1D return).
    """
    try:
        # Can reuse logic from Breadth or fetch targeted
        # Let's fetch last 2 days for all stocks
        query = text("""
            SELECT date, symbol, close
            FROM price_daily
            ORDER BY date DESC
            LIMIT 2000 
        """)
        # Getting "last 2 days" via SQL limit is tricky without window functions per group
        # Better: Pandas approach with last 5 days fetch is robust.
        
        with engine.connect() as conn:
             # Fetch enough to get last 2 distinct dates
             df = pd.read_sql("SELECT date, symbol, close FROM price_daily WHERE date >= current_date - INTERVAL '5 days'", conn)
             
        if df.empty:
             return {"as_of": "", "gainers": [], "losers": []}
             
        df["date"] = pd.to_datetime(df["date"])
        
        # Find latest date
        latest_date = df["date"].max()
        
        pivoted = df.pivot(index="date", columns="symbol", values="close").ffill()
        
        if len(pivoted) < 2:
            return {"as_of": latest_date.strftime("%d-%m-%Y"), "gainers": [], "losers": []}
            
        current = pivoted.iloc[-1]
        prev = pivoted.iloc[-2]
        
        # Calculate returns
        returns = (current / prev) - 1
        returns = returns.dropna().sort_values(ascending=False)
        
        gainers = [{"symbol": s, "return_1d": round(v * 100, 2)} for s, v in returns.head(5).items()]
        losers = [{"symbol": s, "return_1d": round(v * 100, 2)} for s, v in returns.tail(5).items()] # tail is lowest (most negative)
        
        # Sort losers by magnitude or just keep tail order? Tail is usually "worst first" if sorted desc?
        # returns is 10, 5, ... -2, -5.
        # tail(5) is -2, -5... 
        # Requirement usually implies "Top Losers" -> Sorted Ascending. 
        losers.sort(key=lambda x: x["return_1d"]) # Ensure most negative is first
        
        return {
            "as_of": latest_date.strftime("%d-%m-%Y"),
            "gainers": gainers,
            "losers": losers
        }
        
    except Exception as e:
        logger.error(f"Error in leaders: {e}")
        return {}
