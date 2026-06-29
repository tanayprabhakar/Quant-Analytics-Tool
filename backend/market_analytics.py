

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
        
        # Check Staleness for Benchmark
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"]) # Ensure type here for check
            last_date = df["date"].max().date()
            today = datetime.now().date()
            
            if (today - last_date).days > 1:
                try:
                    import yfinance as yf
                    from app import store_prices
                    
                    logger.info(f"Benchmark {benchmark_symbol} is stale (Last: {last_date}). Fetching update...")
                    ticker = yf.Ticker(benchmark_symbol)
                    # Fetch efficient update
                    history = ticker.history(period="1mo", interval="1d")
                    
                    if not history.empty:
                        store_prices(history, benchmark_symbol)
                        # Re-fetch or append? Re-fetch ensures full range logic below works
                        with engine.connect() as conn:
                             df = pd.read_sql(query, conn, params={"symbol": benchmark_symbol})
                except Exception as e:
                    logger.error(f"Failed to update stale benchmark {benchmark_symbol}: {e}")

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
             df = pd.read_sql(text("SELECT date, symbol, close FROM price_daily WHERE date >= current_date - INTERVAL '5 days'"), conn)
             
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

def get_advanced_market_monitor(engine: Engine) -> Dict:
    """
    Consolidated analyst-grade market monitor data.
    Computes: regime, index structure, breadth, sector rotation (from universe),
    momentum breadth, volatility regime, and leaders/laggards with volume context.
    """
    import os
    try:
        # ── 0. Load universe with sector mapping ──
        universe_path = os.getenv("UNIVERSE_PATH", "./universe.csv")
        for candidate in [universe_path, "../universe.csv", "./universe.csv"]:
            if os.path.exists(candidate):
                universe_df = pd.read_csv(candidate)
                break
        else:
            universe_df = pd.DataFrame(columns=["Symbol", "Sector"])
        
        universe_symbols = list(dict.fromkeys(universe_df["Symbol"].dropna().tolist()))
        sector_map = {}
        if "Sector" in universe_df.columns:
            sector_map = dict(zip(universe_df["Symbol"], universe_df["Sector"]))

        # ── 1. Fetch Major Indices ──
        indices = {
            "NIFTY 50": "^NSEI",
            "BANK NIFTY": "^NSEBANK",
            "NIFTY IT": "^CNXIT",
            "S&P 500": "^GSPC"
        }
        
        index_stats = []
        nifty_50_df = None
        
        for name, sym in indices.items():
            query = text("""
                SELECT date, close, high, low
                FROM price_daily
                WHERE symbol = :symbol
                AND date >= current_date - INTERVAL '365 days'
                ORDER BY date ASC
            """)
            with engine.connect() as conn:
                df = pd.read_sql(query, conn, params={"symbol": sym})
            
            if df.empty or (datetime.now().date() - pd.to_datetime(df["date"]).max().date()).days > 1:
                try:
                    import yfinance as yf
                    from app import store_prices
                    ticker = yf.Ticker(sym)
                    history = ticker.history(period="1y")
                    if not history.empty:
                        store_prices(history, sym)
                        with engine.connect() as conn:
                            df = pd.read_sql(query, conn, params={"symbol": sym})
                except: pass

            if df.empty: continue
            
            df["date"] = pd.to_datetime(df["date"])
            if name == "NIFTY 50": nifty_50_df = df
            
            last_price = float(df["close"].iloc[-1])
            prev_price = float(df["close"].iloc[-2]) if len(df) > 1 else last_price
            ret_1d = (last_price / prev_price) - 1
            
            ma_50 = float(df["close"].rolling(50, min_periods=50).mean().iloc[-1]) if len(df) >= 50 else last_price
            
            high_52w = float(df["high"].max())
            dist_high = (last_price / high_52w) - 1
            
            index_stats.append({
                "name": name,
                "symbol": sym,
                "price": round(last_price, 2),
                "change_1d": round(ret_1d * 100, 2),
                "vs_50dma": round(((last_price / ma_50) - 1) * 100, 2),
                "dist_52w_high": round(dist_high * 100, 2)
            })

        # ── 2. Market Breadth & Sector Rotation (single query, universe-only) ──
        breadth_query = text("""
            SELECT date, symbol, close, volume
            FROM price_daily
            WHERE date >= current_date - INTERVAL '90 days'
            ORDER BY date ASC
        """)
        with engine.connect() as conn:
            all_df = pd.read_sql(breadth_query, conn)
        
        breadth_stats = {"above_20": 0, "above_50": 0, "total": 0,
                         "pct_above_20": 0, "pct_above_50": 0}
        advancers, decliners = 0, 0
        momentum_breadth = {"pct_positive_30d": 0, "pct_top_decile": 0}
        sector_results = []
        leader_vol_map = {}  # symbol -> volume_ratio for leaders context
        
        if not all_df.empty:
            all_df["date"] = pd.to_datetime(all_df["date"])
            
            # Filter to universe stocks only (exclude index symbols)
            stock_symbols = [s for s in universe_symbols if not s.startswith("^")]
            stock_df = all_df[all_df["symbol"].isin(stock_symbols)]
            
            if not stock_df.empty:
                price_pivot = stock_df.pivot_table(index="date", columns="symbol", values="close").ffill()
                vol_pivot = stock_df.pivot_table(index="date", columns="symbol", values="volume").fillna(0)
                
                if not price_pivot.empty and len(price_pivot) > 1:
                    current = price_pivot.iloc[-1]
                    prev = price_pivot.iloc[-2]
                    valid = current.dropna().index
                    breadth_stats["total"] = len(valid)
                    
                    ma20 = price_pivot.rolling(20, min_periods=20).mean().iloc[-1]
                    ma50 = price_pivot.rolling(50, min_periods=50).mean().iloc[-1]
                    
                    # Per-stock returns for sector rotation
                    ret_1d_all = {}
                    ret_1w_all = {}
                    ret_30d_all = {}
                    
                    for s in valid:
                        p = current[s]
                        pp = prev[s]
                        if pd.notna(pp) and pp > 0:
                            if p > pp: advancers += 1
                            elif p < pp: decliners += 1
                        if pd.notna(ma20.get(s)) and p > ma20[s]: breadth_stats["above_20"] += 1
                        if pd.notna(ma50.get(s)) and p > ma50[s]: breadth_stats["above_50"] += 1
                        
                        # 1D return
                        ret_1d_all[s] = ((p / pp) - 1) if pp > 0 else 0
                        # 1W return (5 trading days back)
                        if len(price_pivot) > 5:
                            pw = price_pivot[s].iloc[-6]
                            ret_1w_all[s] = ((p / pw) - 1) if pd.notna(pw) and pw > 0 else 0
                        else:
                            ret_1w_all[s] = 0
                        # 30D return
                        if len(price_pivot) > 21:
                            p30 = price_pivot[s].iloc[-22]
                            ret_30d_all[s] = ((p / p30) - 1) if pd.notna(p30) and p30 > 0 else 0
                        else:
                            ret_30d_all[s] = 0
                    
                    total = breadth_stats["total"]
                    if total > 0:
                        for k in ["above_20", "above_50"]:
                            breadth_stats[f"pct_{k}"] = round(breadth_stats[k] / total * 100, 1)
                    
                    # ── Momentum Breadth (real) ──
                    positive_30d = sum(1 for v in ret_30d_all.values() if v > 0)
                    if total > 0:
                        momentum_breadth["pct_positive_30d"] = round(positive_30d / total * 100, 1)
                        sorted_mom = sorted(ret_30d_all.values(), reverse=True)
                        decile_cutoff = len(sorted_mom) // 10
                        top_decile = sum(1 for v in ret_30d_all.values() if v >= sorted_mom[max(decile_cutoff - 1, 0)])
                        momentum_breadth["pct_top_decile"] = round(top_decile / total * 100, 1)
                    
                    # ── Sector Rotation (from universe Sector column) ──
                    if sector_map:
                        sector_groups = {}
                        for s in valid:
                            sec = sector_map.get(s)
                            if sec:
                                if sec not in sector_groups:
                                    sector_groups[sec] = {"ret_1d": [], "ret_1w": []}
                                sector_groups[sec]["ret_1d"].append(ret_1d_all.get(s, 0))
                                sector_groups[sec]["ret_1w"].append(ret_1w_all.get(s, 0))
                        
                        for sec, vals in sector_groups.items():
                            if len(vals["ret_1d"]) >= 2:  # need at least 2 stocks
                                sector_results.append({
                                    "sector": sec,
                                    "count": len(vals["ret_1d"]),
                                    "change_1d": round(np.mean(vals["ret_1d"]) * 100, 2),
                                    "change_1w": round(np.mean(vals["ret_1w"]) * 100, 2)
                                })
                        sector_results.sort(key=lambda x: x["change_1d"], reverse=True)
                    
                    # ── Volume spike map for leaders/laggards ──
                    if not vol_pivot.empty and len(vol_pivot) > 20:
                        vol_current = vol_pivot.iloc[-1]
                        vol_20d_avg = vol_pivot.tail(20).mean()
                        for s in valid:
                            vc = vol_current.get(s, 0)
                            va = vol_20d_avg.get(s, 1)
                            if va > 0 and vc > 0:
                                leader_vol_map[s] = round(vc / va, 1)

        # ── 3. Market Regime ──
        regime = "Neutral"
        trend = "Neutral"
        if nifty_50_df is not None and not nifty_50_df.empty and len(nifty_50_df) > 1:
            last_nifty = float(nifty_50_df["close"].iloc[-1])
            nifty_ma200 = float(nifty_50_df["close"].rolling(200).mean().iloc[-1]) if len(nifty_50_df) >= 200 else last_nifty
            nifty_ret_1d = (last_nifty / float(nifty_50_df["close"].iloc[-2])) - 1
            
            trend = "Bullish" if last_nifty > nifty_ma200 else "Bearish"
            pct50 = breadth_stats.get("pct_above_50", 0)
            
            if nifty_ret_1d > 0 and pct50 > 60: regime = "Risk-On"
            elif nifty_ret_1d < 0 and pct50 < 40: regime = "Risk-Off"

        # ── 4. Volatility Regime ──
        vol_status = "Normal"
        vol_value = 0.0
        if nifty_50_df is not None and len(nifty_50_df) > 20:
            log_rets = np.log(nifty_50_df["close"] / nifty_50_df["close"].shift(1))
            vol_20d = float(log_rets.tail(20).std() * np.sqrt(252))
            vol_200d = float(log_rets.tail(200).std() * np.sqrt(252)) if len(log_rets) > 200 else vol_20d
            vol_value = round(vol_20d * 100, 1)
            
            if vol_20d > vol_200d * 1.2: vol_status = "High"
            elif vol_20d < vol_200d * 0.8: vol_status = "Low"

        # ── 5. Leaders & Laggards with volume context ──
        leaders_raw = get_leaders_laggards(engine)
        gainers = leaders_raw.get("gainers", [])
        losers = leaders_raw.get("losers", [])
        
        for g in gainers:
            g["vol_ratio"] = leader_vol_map.get(g["symbol"], None)
        for l in losers:
            l["vol_ratio"] = leader_vol_map.get(l["symbol"], None)

        
        return {
            "as_of": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "regime": regime,
            "trend": trend,
            "universe_count": len(universe_symbols),
            "indices": index_stats,
            "breadth": {
                "advancers": advancers,
                "decliners": decliners,
                "stats": breadth_stats
            },
            "momentum": momentum_breadth,
            "sectors": sector_results,
            "volatility": {
                "status": vol_status,
                "value": vol_value
            },
            "leaders": gainers,
            "laggards": losers
        }
    except Exception as e:
        logger.error(f"Error in advanced monitor: {e}", exc_info=True)
        return {"error": str(e)}
