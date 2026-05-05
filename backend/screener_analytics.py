
import pandas as pd
import numpy as np
import logging
import os
import yfinance as yf
from sqlalchemy import Engine, text
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def _safe_float(val, default=0.0):
    """Convert value to a JSON-safe float. NaN/Inf become default."""
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def get_multi_factor_screen(engine: Engine, benchmark_symbol: str = "^NSEI") -> Dict:
    """
    Multi-dimensional equity screen.
    Returns enriched data for ALL universe stocks in a single pass.
    All filtering happens client-side.
    
    Computed per stock:
      - momentum_30d, momentum_90d, momentum_percentile
      - volatility_30d, vol_label
      - relative_1m, relative_3m, relative_label
      - price_vs_50dma, trend_label
      - signal (composite)
      - sector
    """
    try:
        # ── 0. Load universe with sector mapping ──
        universe_path = os.getenv("UNIVERSE_PATH", "./universe.csv")
        for candidate in [universe_path, "../universe.csv", "./universe.csv"]:
            if os.path.exists(candidate):
                universe_path = candidate
                break
        else:
            return {"error": "Universe CSV not found", "results": []}

        universe_df = pd.read_csv(universe_path)
        if "Symbol" not in universe_df.columns:
            return {"error": "Invalid universe CSV", "results": []}

        symbols = list(dict.fromkeys(universe_df["Symbol"].dropna().tolist()))
        sector_map = {}
        if "Sector" in universe_df.columns:
            sector_map = dict(zip(universe_df["Symbol"], universe_df["Sector"]))

        # ── 1. Fetch momentum scores (30d and 90d) ──
        mom_query = text("""
            SELECT symbol, lookback_days, momentum_score
            FROM factor_momentum
            WHERE as_of_date = (
                SELECT MAX(as_of_date) FROM factor_momentum WHERE lookback_days = :lb
            )
            AND lookback_days = :lb
        """)

        mom_30 = {}
        mom_90 = {}

        with engine.connect() as conn:
            df_30 = pd.read_sql(mom_query, conn, params={"lb": 30})
            df_90 = pd.read_sql(mom_query, conn, params={"lb": 90})

        if not df_30.empty:
            mom_30 = dict(zip(df_30["symbol"], df_30["momentum_score"].astype(float)))
        if not df_90.empty:
            mom_90 = dict(zip(df_90["symbol"], df_90["momentum_score"].astype(float)))

        # ── 2. Fetch price data (last 90 days for vol + returns + DMA) ──
        price_query = text("""
            SELECT date, symbol, close
            FROM price_daily
            WHERE date >= current_date - INTERVAL '120 days'
            ORDER BY date ASC
        """)

        with engine.connect() as conn:
            price_df = pd.read_sql(price_query, conn)

        if price_df.empty:
            return {"error": "No price data", "results": []}

        price_df["date"] = pd.to_datetime(price_df["date"])

        # Pivot: date x symbol → close
        pivoted = price_df.pivot_table(index="date", columns="symbol", values="close")
        pivoted = pivoted.ffill()

        # ── 3. Compute benchmark returns ──
        bench_col = benchmark_symbol if benchmark_symbol in pivoted.columns else None
        bench_ret_1m = 0.0
        bench_ret_3m = 0.0

        if bench_col:
            bench_prices = pivoted[bench_col].dropna()
            if len(bench_prices) > 21:
                bench_ret_1m = (bench_prices.iloc[-1] / bench_prices.iloc[-22]) - 1
            if len(bench_prices) > 63:
                bench_ret_3m = (bench_prices.iloc[-1] / bench_prices.iloc[-64]) - 1

        # ── 4. Compute per-stock metrics ──
        log_rets = np.log(pivoted / pivoted.shift(1))

        # SMA50 at latest date
        sma50 = pivoted.rolling(50, min_periods=50).mean().iloc[-1]

        # 30D volatility (annualized)
        last_30_rets = log_rets.tail(30)
        vols_30d = last_30_rets.std() * np.sqrt(252)

        # Stock returns
        current_prices = pivoted.iloc[-1]

        # Momentum percentile (cross-sectional on 90d)
        all_90d_scores = np.array([v for v in mom_90.values() if not np.isnan(v)])

        # Build results
        results = []
        as_of = pivoted.index[-1].strftime("%d-%m-%Y")

        for sym in symbols:
            if sym.startswith("^"):
                continue  # Skip index symbols

            # Skip if no price data
            if sym not in pivoted.columns or pd.isna(current_prices.get(sym)):
                continue

            price = float(current_prices[sym])

            # Momentum
            m30 = _safe_float(mom_30.get(sym))
            m90 = _safe_float(mom_90.get(sym))

            # Momentum percentile
            if len(all_90d_scores) > 0 and not np.isnan(m90):
                pct = float(np.searchsorted(np.sort(all_90d_scores), m90) / len(all_90d_scores) * 100)
            else:
                pct = 50.0

            # Volatility
            vol = _safe_float(vols_30d.get(sym))
            if vol < 0.15:
                vol_label = "Low"
            elif vol < 0.30:
                vol_label = "Normal"
            else:
                vol_label = "High"

            # Relative strength vs benchmark
            sym_prices = pivoted[sym].dropna()
            sym_ret_1m = 0.0
            sym_ret_3m = 0.0
            if len(sym_prices) > 21:
                sym_ret_1m = (sym_prices.iloc[-1] / sym_prices.iloc[-22]) - 1
            if len(sym_prices) > 63:
                sym_ret_3m = (sym_prices.iloc[-1] / sym_prices.iloc[-64]) - 1

            rel_1m = _safe_float(sym_ret_1m - bench_ret_1m)
            rel_3m = _safe_float(sym_ret_3m - bench_ret_3m)
            rel_label = "Outperforming" if rel_1m >= 0 else "Underperforming"

            # Trend (price vs SMA50)
            ma50_val = _safe_float(sma50.get(sym))
            if ma50_val > 0:
                price_vs_50 = (price / ma50_val) - 1
            else:
                price_vs_50 = 0.0

            if price_vs_50 > 0.02:
                trend_label = "Uptrend"
            elif price_vs_50 < -0.02:
                trend_label = "Downtrend"
            else:
                trend_label = "Sideways"

            # Composite signal
            if pct > 70 and trend_label == "Uptrend" and rel_1m > 0:
                signal = "Strong"
            elif pct > 50:
                signal = "Watch"
            else:
                signal = "Weak"

            sector = sector_map.get(sym, "—")

            results.append({
                "symbol": sym,
                "momentum_30d": round(m30, 4),
                "momentum_90d": round(m90, 4),
                "momentum_percentile": round(pct, 1),
                "volatility_30d": round(vol, 4),
                "vol_label": vol_label,
                "relative_1m": round(_safe_float(rel_1m), 4),
                "relative_3m": round(_safe_float(rel_3m), 4),
                "relative_label": rel_label,
                "price_vs_50dma": round(_safe_float(price_vs_50), 4),
                "trend_label": trend_label,
                "signal": signal,
                "sector": sector,
            })

        # Sort by momentum_90d descending by default
        results.sort(key=lambda x: x["momentum_90d"], reverse=True)

        # Assign ranks
        for i, r in enumerate(results):
            r["rank"] = i + 1

        return {
            "screener": "multi",
            "as_of": as_of,
            "universe": "NIFTY_UNIVERSE",
            "total": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Multi-Factor Screen Error: {e}", exc_info=True)
        return {"error": str(e), "results": []}


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
            score = _safe_float(row["momentum_score"])
            results.append({
                "symbol": row["symbol"],
                "score": round(score, 4),
                "rank": rank,
                "metrics": {
                    f"momentum_{lookback_days}d": round(score, 4)
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
            vol_safe = _safe_float(vol)
            results.append({
                "symbol": sym,
                "score": round(vol_safe, 4),
                "rank": rank,
                "metrics": {
                    "vol_30d": round(vol_safe, 4)
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
            pe_safe = _safe_float(row["pe_ratio"])
            results.append({
                "symbol": row["symbol"],
                "score": round(pe_safe, 2),
                "rank": rank,
                "metrics": {
                    "pe": round(pe_safe, 2)
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

