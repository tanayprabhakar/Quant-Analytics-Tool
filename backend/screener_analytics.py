
import pandas as pd
import numpy as np
import logging
import os
import yfinance as yf
from sqlalchemy import Engine, text
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def get_momentum_screen(engine: Engine, lookback_days: int = 30, top_n: int = 20) -> Dict:
    """
    Rank stocks by momentum from factor_momentum table.
    Momentum = (Close_T / Close_T-k) - 1
    Returns: { "screener": "momentum", ..., "results": [...] }
    """
    try:
        # Fetch latest available momentum scores for the requested lookback
        # Strategy: Get Max Date per symbol? OR just Max Date overall?
        # "Use most recent as_of_date <= requested date" (implicit today)
        
        query = text("""
            SELECT symbol, momentum_score, as_of_date
            FROM factor_momentum
            WHERE lookback_days = :lookback
            AND as_of_date = (
                SELECT MAX(as_of_date) FROM factor_momentum WHERE lookback_days = :lookback
            )
            ORDER BY momentum_score DESC
            LIMIT :top_n
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"lookback": lookback_days, "top_n": top_n})
            
        if df.empty:
             return {"screener": "momentum", "error": "No data available", "results": []}
             
        results = []
        rank = 1
        as_of = df["as_of_date"].iloc[0] if not df["as_of_date"].empty else datetime.now().date()
        
        for _, row in df.iterrows():
            results.append({
                "symbol": row["symbol"],
                "score": round(float(row["momentum_score"]), 4),
                "rank": rank,
                "metrics": {
                    f"momentum_{lookback_days}d": round(float(row["momentum_score"]), 4)
                }
            })
            rank += 1
            
        return {
            "screener": "momentum",
            "as_of": as_of.strftime("%d-%m-%Y"),
            "universe": "NIFTY50_UNI", # Approximation
            "results": results
        }

    except Exception as e:
        logger.error(f"Momentum Screen Error: {e}")
        return {"error": str(e), "results": []}

def get_low_vol_screen(engine: Engine, top_n: int = 20) -> Dict:
    """
    Stocks with lowest 30-day annualized volatility.
    vol = std(log_returns) * sqrt(252)
    """
    try:
        # Fetch last ~45 days of price data for ALl stocks to compute 30D vol
        # We need a window.
        
        query = text("""
            SELECT date, symbol, close
            FROM price_daily
            WHERE date >= current_date - INTERVAL '60 days'
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
            
        if df.empty:
             return {"screener": "low-vol", "error": "No price data", "results": []}
             
        df["date"] = pd.to_datetime(df["date"])
        pivoted = df.pivot(index="date", columns="symbol", values="close")
        
        # Calculate Log Returns
        log_rets = np.log(pivoted / pivoted.shift(1))
        
        # Rolling 30D std dev at the last date
        # We only need the LATEST 30D vol.
        # Take last 30 observations
        last_30 = log_rets.tail(30)
        
        if len(last_30) < 20: # Minimum validation
             return {"screener": "low-vol", "error": "Insufficient data depth", "results": []}
             
        vols = last_30.std() * np.sqrt(252)
        
        # Sort Ascending
        vols = vols.sort_values(ascending=True)
        
        # Filter NaNs
        vols = vols.dropna()
        
        top_vols = vols.head(top_n)
        
        results = []
        rank = 1
        as_of = pivoted.index[-1].strftime("%d-%m-%Y")
        
        for sym, vol in top_vols.items():
            results.append({
                "symbol": sym,
                "score": round(float(vol), 4),
                "rank": rank,
                "metrics": {
                    "vol_30d": round(float(vol), 4)
                }
            })
            rank += 1
            
        return {
            "screener": "low-vol",
            "as_of": as_of,
            "universe": "NIFTY50_UNI",
            "results": results
        }

    except Exception as e:
        logger.error(f"LowVol Screen Error: {e}")
        return {"error": str(e), "results": []}


def _auto_ingest_fundamentals(engine: Engine):
    """
    Auto-fetch fundamentals from Yahoo Finance for all universe stocks
    when the fundamentals_snapshot table is empty.
    """
    logger.info("Value Screener: No fundamental data found. Auto-ingesting from Yahoo Finance...")
    
    # Find universe CSV
    universe_path = os.getenv("UNIVERSE_PATH", "../universe.csv")
    for candidate in [universe_path, "./universe.csv", "../universe.csv"]:
        if os.path.exists(candidate):
            universe_path = candidate
            break
    else:
        logger.error("Cannot find universe.csv for auto-ingestion")
        return False
    
    universe = pd.read_csv(universe_path)
    if "Symbol" not in universe.columns:
        return False
    
    symbols = universe["Symbol"].dropna().unique().tolist()
    today = datetime.now().date()
    success = 0
    
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            mcap = info.get("marketCap")
            pe = info.get("trailingPE")
            eps = info.get("trailingEps")
            sector = info.get("sector")
            
            query = text("""
                INSERT INTO fundamentals_snapshot (symbol, as_of_date, market_cap, pe_ratio, eps, sector)
                VALUES (:symbol, :date, :mcap, :pe, :eps, :sector)
                ON CONFLICT (symbol, as_of_date) DO UPDATE
                SET market_cap = EXCLUDED.market_cap,
                    pe_ratio = EXCLUDED.pe_ratio,
                    eps = EXCLUDED.eps,
                    sector = EXCLUDED.sector,
                    created_at = now()
            """)
            
            with engine.begin() as conn:
                conn.execute(query, {
                    "symbol": symbol, "date": today,
                    "mcap": mcap, "pe": pe, "eps": eps, "sector": sector
                })
            success += 1
            
        except Exception as e:
            logger.warning(f"Auto-ingest failed for {symbol}: {e}")
    
    logger.info(f"Auto-ingested fundamentals for {success}/{len(symbols)} stocks")
    return success > 0


def get_value_screen(engine: Engine, top_n: int = 20) -> Dict:
    """
    Lowest Valuation Stocks (P/E Ratio).
    Uses fundamentals_snapshot table. Auto-ingests if empty.
    """
    try:
        # Fetch latest snapshot
        query = text("""
            SELECT symbol, pe_ratio, as_of_date
            FROM fundamentals_snapshot
            WHERE as_of_date = (
                SELECT MAX(as_of_date) FROM fundamentals_snapshot
            )
            AND pe_ratio IS NOT NULL
            AND pe_ratio > 0 -- Usual constraint for Valid P/E
            ORDER BY pe_ratio ASC
            LIMIT :top_n
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"top_n": top_n})
            
        if df.empty:
            # Auto-ingest and retry
            if _auto_ingest_fundamentals(engine):
                with engine.connect() as conn:
                    df = pd.read_sql(query, conn, params={"top_n": top_n})
            
            if df.empty:
                return {"screener": "value", "error": "No fundamental data available", "results": []}
            
        as_of = df["as_of_date"].iloc[0].strftime("%d-%m-%Y")
        
        results = []
        rank = 1
        
        for _, row in df.iterrows():
            results.append({
                "symbol": row["symbol"],
                "score": round(float(row["pe_ratio"]), 2),
                "rank": rank,
                "metrics": {
                    "pe": round(float(row["pe_ratio"]), 2)
                }
            })
            rank += 1
            
        return {
            "screener": "value",
            "as_of": as_of,
            "universe": "NIFTY50_UNI",
            "results": results
        }

    except Exception as e:
        logger.error(f"Value Screen Error: {e}")
        return {"error": str(e), "results": []}

