"""
India Finance API - FastAPI Backend

Deployment Notes:
-----------------
Environment Variables:
- CACHE_TTL_SEC: TTL for in-memory cache in seconds (default: 120)
- UNIVERSE_PATH: Path to the universe CSV file (default: ./universe.csv)
- DATABASE_URL: Postgres Connection String

Security Note:
- Do not store database credentials in frontend — only server side.

Test Commands:
--------------
1. Health Check:
   curl http://localhost:8000/health

2. Historical Data:
   curl "http://localhost:8000/india/history/RELIANCE.NS?period=1mo"

3. Momentum Factors:
   curl "http://localhost:8000/india/factors/momentum?lookback_days=30&top_n=5"

"""

import os
import time
import logging
import threading
import uuid
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import numpy as np
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from backtest_logic import run_backtest_momentum
from market_analytics import get_market_summary, get_market_breadth, get_leaders_laggards, get_advanced_market_monitor
from security_analytics import get_security_overview, get_security_performance
from screener_analytics import get_momentum_screen, get_low_vol_screen, get_value_screen
from research_analytics import do_backtest
from portfolio_analytics import analyze_portfolio_request

# 1. Environment & Dependencies
load_dotenv()

CACHE_TTL_SEC = int(os.getenv("CACHE_TTL_SEC", 120))
UNIVERSE_PATH = os.getenv("UNIVERSE_PATH", "./universe.csv")
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 3. Database Engine
if not DATABASE_URL:
    logger.warning("DATABASE_URL not set. Persistence features might fail.")
    engine = None
else:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        logger.info("Database engine initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize database engine: {e}")
        engine = None

# 4. Cache Implementation
class TTLCache:
    """
    Simple in-memory TTL cache with thread-safe operations.
    For production, replace with an external cache like Redis (e.g., Upstash).
    """
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() < entry["expire_at"]:
                    logger.info(f"Cache HIT for key: {key}")
                    return entry["value"]
                else:
                    logger.info(f"Cache EXPIRED for key: {key}")
                    del self._cache[key]
            else:
                logger.info(f"Cache MISS for key: {key}")
        return None

    def set(self, key: str, value: Any, ttl: int):
        with self._lock:
            self._cache[key] = {
                "value": value,
                "expire_at": time.time() + ttl
            }

# Initialize Cache
cache = TTLCache()

# 5. App Setup
app = FastAPI(title="College OpenBB India API")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6. Pydantic Models for Documentation
class HealthResponse(BaseModel):
    status: str
    timestamp: float

class HistoryPoint(BaseModel):
    Date: str
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int
    Dividends: Optional[float] = 0.0

class FundamentalsResponse(BaseModel):
    symbol: str
    shortName: Optional[str]
    longName: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    marketCap: Optional[int]
    trailingPE: Optional[float]
    forwardPE: Optional[float]
    beta: Optional[float]
    dividendYield: Optional[float]
    
class MomentumResult(BaseModel):
    symbol: str
    momentum: float
    latest: float
    data_points: int

class MomentumResponse(BaseModel):
    lookback_days: int
    top_n: int
    results: List[MomentumResult]

class ScreenerResult(BaseModel):
    symbol: str
    score: float
    rank: int
    metrics: Dict[str, Any]

class ScreenerResponse(BaseModel):
    screener: str
    as_of: str
    universe: str
    results: List[ScreenerResult]

class BacktestRequest(BaseModel):
    factor: str
    lookback_days: int = 90
    top_n: int = 10
    rebalance: str = "monthly"
    start: str = "2023-01-01"
    end: str = "2023-12-31"

class SweepRequest(BaseModel):
    factor: str
    lookbacks: List[int]
    top_n: int = 10
    start: str = "2023-01-01"
    end: str = "2023-12-31"

class PortfolioRequest(BaseModel):
    symbols: List[str]
    weights: List[float]
    start: str = "2023-01-01"
    end: str = "2023-12-31"
    benchmark: str = "^NSEI"

# 7. Helper Functions (Persistence)

def fetch_prices_from_db(symbol: str, limit: int = 365) -> Optional[pd.DataFrame]:
    """
    Fetch historical prices from DB for a symbol. 
    Returns DataFrame matching yfinance structure or None if insufficient/empty.
    """
    if not engine:
        return None
    
    try:
        query = text("""
            SELECT date, open, high, low, close, volume 
            FROM price_daily 
            WHERE symbol = :symbol 
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": symbol})
        
        if df.empty:
            return None
        
        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])
        
        # Renaissance format to match what app expects: 
        # Rename columns to Title Case to match yfinance output expectations generally
        df = df.rename(columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })
        
        # DB doesn't store dividends yet for simplicity (schema didn't ask), but API needs it
        df["Dividends"] = 0.0
        
        return df

    except Exception as e:
        logger.error(f"Error fetching prices from DB for {symbol}: {e}")
        return None

def store_prices(df: pd.DataFrame, symbol: str):
    """
    Store DataFrame (yfinance format) into price_daily table using ON CONFLICT DO NOTHING.
    """
    if not engine or df.empty:
        return

    try:
        # Prepare data for insertion
        records = []
        for index, row in df.iterrows():
            # Handle index if it's the date
            date_val = index.date() if isinstance(index, (pd.Timestamp, datetime)) else row.get("Date")
            if not date_val: 
                # e.g. if reset_index was called before
                date_val = row.get("Date")
                
            # Safe extraction helper for possible Series/MultiIndex items
            def get_val(r, col):
                val = r.get(col)
                if hasattr(val, "ndim") and val.ndim > 0: # Series/Array
                    return val.iloc[0] if len(val) > 0 else None
                return val

            records.append({
                "symbol": symbol,
                "date": date_val,
                "open": float(get_val(row, "Open") or 0),
                "high": float(get_val(row, "High") or 0),
                "low": float(get_val(row, "Low") or 0),
                "close": float(get_val(row, "Close") or 0),
                "volume": int(get_val(row, "Volume") or 0)
            })

        if not records:
            return

        query = text("""
            INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
            VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
            ON CONFLICT (symbol, date) DO NOTHING
        """)

        with engine.begin() as conn: # engine.begin() manages transaction commit
            conn.execute(query, records)
            
        logger.info(f"Stored {len(records)} price records for {symbol}")

    except Exception as e:
        logger.error(f"Error storing prices for {symbol}: {e}")

def store_momentum(symbol: str, score: float, lookback: int):
    """
    Store computed momentum score.
    """
    if not engine:
        return

    try:
        query = text("""
            INSERT INTO factor_momentum (symbol, as_of_date, lookback_days, momentum_score)
            VALUES (:symbol, :date, :lookback, :score)
            ON CONFLICT (symbol, as_of_date, lookback_days) DO UPDATE 
            SET momentum_score = EXCLUDED.momentum_score, created_at = now()
        """)
        
        today = datetime.now().date()
        
        with engine.begin() as conn:
            conn.execute(query, {
                "symbol": symbol,
                "date": today,
                "lookback": lookback,
                "score": score
            })

    except Exception as e:
        logger.error(f"Error storing momentum for {symbol}: {e}")

def start_run(run_type: str) -> Optional[str]:
    """
    Create a new run entry and return its ID.
    """
    if not engine:
        return None
    
    run_id = str(uuid.uuid4())
    try:
        query = text("""
            INSERT INTO runs (run_id, run_type, status)
            VALUES (:run_id, :run_type, 'running')
        """)
        
        with engine.begin() as conn:
            conn.execute(query, {"run_id": run_id, "run_type": run_type})
            
        return run_id
    except Exception as e:
        logger.error(f"Error starting run: {e}")
        return None

def finish_run(run_id: str, status: str, error: Optional[str] = None):
    """
    Update run status.
    """
    if not engine or not run_id:
        return
    
    try:
        query = text("""
            UPDATE runs 
            SET status = :status, error = :error, finished_at = now()
            WHERE run_id = :run_id
        """)
        
        with engine.begin() as conn:
            conn.execute(query, {"run_id": run_id, "status": status, "error": error})
            
    except Exception as e:
        logger.error(f"Error finishing run {run_id}: {e}")


# 8. Endpoints

@app.get("/health", response_model=HealthResponse)
def health_check():
    """
    Simple health check endpoint.
    Returns status and current timestamp.
    """
    logger.info("Endpoint accessed: /health")
    return {"status": "ok", "timestamp": time.time()}

@app.get("/india/history/{symbol}", response_model=List[HistoryPoint])
def get_history(
    symbol: str = Path(..., description="Stock symbol, e.g., RELIANCE.NS"),
    period: str = Query("1y", description="Data period to download"),
    interval: str = Query("1d", description="Data interval")
):
    """
    Fetch historical data for a given symbol.
    """
    logger.info(f"Endpoint accessed: /india/history/{symbol} params: period={period}, interval={interval}")
    
    cache_key = f"hist:{symbol}:{period}:{interval}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    try:
        # A) Try DB First
        df = fetch_prices_from_db(symbol)
        
        # Basic check: if we asked for 1mo (~20 days) and DB has < 20, maybe fetch
        # For simplicity, if DB returns ANY data, we prefer it, 
        # unless it is obviously too stale or empty.
        # Impl constraint: "If missing -> fetch from Yahoo"
        
        data_source = "db"
        
        if df is None or df.empty:
            data_source = "yahoo"
            # B) Fetch from Yahoo
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                logger.warning(f"No data found for symbol: {symbol}")
                raise HTTPException(status_code=404, detail=f"No data for symbol {symbol} with period {period} interval {interval}")

            # Store in DB
            store_prices(df, symbol)
            
            # Formatting for response
            df = df.reset_index()
        else:
            # CHECK STALENESS
            last_date_in_db = pd.to_datetime(df["Date"]).max().date()
            today = datetime.now().date()
            # If older than 2 days (to be safe for weekends/holidays, though 1 day is ideal for active market)
            # Let's say: if last_date < (today - 1 day), we consider it stale and fetch update.
            # Example: Today is Monday. Last date in DB is Friday. Delta = 3 days. We need fresh? No, market closed.
            # But simplistic check: if delta > 1, fetch just in case. yfinance handles market holidays (returns empty for closed days).
            if (today - last_date_in_db).days > 1:
                logger.info(f"Data for {symbol} is stale (Last: {last_date_in_db}). Fetching fresh from Yahoo.")
                data_source = "yahoo (update)"
                ticker = yf.Ticker(symbol)
                # Fetch only recent data to append? Or overwrite? 
                # Simplest is robust fetch of period again.
                df_new = ticker.history(period=period, interval=interval)
                
                if not df_new.empty:
                    store_prices(df_new, symbol)
                    # Merge new data with old to ensure we have full set, or just use new if it covers period.
                    # Since we requested 'period', df_new should have what we want.
                    df = df_new.reset_index()

        # Formatting (applies to both DB and Yahoo data sources)
        # Ensure Date is string YYYY-MM-DD
        if not pd.api.types.is_string_dtype(df["Date"]):
             df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # Handle missing Dividends if not present
        if "Dividends" not in df.columns:
            df["Dividends"] = 0.0
        
        df = df.replace({np.nan: None})
        
        result = df[["Date", "Open", "High", "Low", "Close", "Volume", "Dividends"]].to_dict(orient="records")
        
        cache.set(cache_key, result, CACHE_TTL_SEC)
        logger.info(f"Served history for {symbol} from {data_source}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching history for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"internal error: {str(e)}")

@app.get("/india/fundamentals/{symbol}", response_model=FundamentalsResponse)
def get_fundamentals(symbol: str = Path(..., description="Stock symbol")):
    """
    Fetch fundamental data for a given symbol.
    """
    logger.info(f"Endpoint accessed: /india/fundamentals/{symbol}")

    cache_key = f"fund:{symbol}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or "shortName" not in info:
            logger.warning(f"Fundamentals not found for symbol: {symbol}")
            raise HTTPException(status_code=404, detail=f"Fundamentals not found for {symbol}")

        # Extract safe keys
        safe_keys = [
            "symbol", "shortName", "longName", "sector", "industry",
            "marketCap", "trailingPE", "forwardPE", "beta", "dividendYield"
        ]
        
        result = {k: info.get(k) for k in safe_keys}
        # Ensure symbol is present in result if not in info
        if not result.get("symbol"):
            result["symbol"] = symbol

        cache.set(cache_key, result, CACHE_TTL_SEC)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"internal error: {str(e)}")

@app.get("/india/factors/momentum", response_model=MomentumResponse)
def get_momentum(
    lookback_days: int = Query(90, description="Lookback period in days"),
    top_n: int = Query(10, description="Number of top stocks to return")
):
    """
    Calculate momentum for stocks in the universe.
    Momentum = (last_close / first_close) - 1
    """
    logger.info(f"Endpoint accessed: /india/factors/momentum params: lookback_days={lookback_days}, top_n={top_n}")

    # Persistence: Start Run
    run_id = start_run("momentum_calc")
    run_error = None

    cache_key = f"mom:{lookback_days}:{top_n}"
    cached_data = cache.get(cache_key)
    if cached_data:
        finish_run(run_id, "success (cached)")
        return cached_data

    try:
        if not os.path.exists(UNIVERSE_PATH):
            raise HTTPException(status_code=500, detail="Universe configuration error")

        # Read universe
        try:
            universe_df = pd.read_csv(UNIVERSE_PATH)
            if universe_df.empty or "Symbol" not in universe_df.columns:
                 raise ValueError("Empty or invalid universe file")
            # Deduplicate while preserving order
            tickers = list(dict.fromkeys(universe_df["Symbol"].tolist()))
        except Exception as e:
            raise HTTPException(status_code=400, detail="universe is empty or invalid")

        if not tickers:
             raise HTTPException(status_code=400, detail="universe is empty")

        results = []
        
        download_period = f"{lookback_days + 5}d"

        for ticker in tickers:
            try:
                # 1. Try DB first
                df = fetch_prices_from_db(ticker)
                
                # If insufficient data in DB (simple check: is it empty or very short?), fetch Yahoo
                # Also check STALENESS
                is_stale = False
                if df is not None and not df.empty:
                    last_date = pd.to_datetime(df["Date"]).max().date()
                    if (datetime.now().date() - last_date).days > 1:
                        is_stale = True

                if df is None or len(df) < lookback_days or is_stale:
                     # Fetch from Yahoo
                     # If it was stale, we might want just the update, but simpler to fetch period logic
                     # We use download_period (lookback + 5) which is short enough to be fast
                     df_yahoo = yf.download(ticker, period=download_period, interval="1d", progress=False, threads=False)
                     if not df_yahoo.empty:
                         # Store for next time
                         store_prices(df_yahoo, ticker)
                         # Use this dataframe
                         df = df_yahoo
                         # Normalize columns if needed (yfinance MultiIndex handled below) looks like we rely on below logic
                         df = df.reset_index() # yf.download returns Date index usually

                
                if df is None or df.empty or len(df) < lookback_days:
                    continue
                
                # Logic to extract closes (handles clean DF or MultiIndex)
                if isinstance(df.columns, pd.MultiIndex):
                    try:
                        closes = df["Close"][ticker]
                    except KeyError:
                        closes = df["Close"].iloc[:, 0]
                else:
                    closes = df["Close"]

                # Take tail based on lookback
                closes = closes.tail(lookback_days)
                
                if len(closes) < 2:
                    continue

                first_close = float(closes.iloc[0])
                last_close = float(closes.iloc[-1])
                
                if first_close == 0:
                    continue

                momentum = (last_close / first_close) - 1
                
                # Persistence: Store Momentum Score
                store_momentum(ticker, momentum, lookback_days)

                if pd.isna(momentum) or pd.isna(last_close):
                    logger.warning(f"NaN computed for {ticker}: mom={momentum} close={last_close}")
                    continue

                results.append({
                    "symbol": ticker,
                    "momentum": float(momentum),
                    "latest": float(last_close),
                    "data_points": len(closes)
                })
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                continue

        # Sort descending by momentum
        results.sort(key=lambda x: x["momentum"], reverse=True)
        
        top_results = results[:top_n]
        
        response_data = {
            "lookback_days": lookback_days,
            "top_n": top_n,
            "results": top_results
        }
        
        cache.set(cache_key, response_data, CACHE_TTL_SEC)
        
        finish_run(run_id, "success")
        return response_data

    except HTTPException:
        finish_run(run_id, "failed", "HTTPException")
        raise
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Error in momentum endpoint: {e}", exc_info=True)
        finish_run(run_id, "failed", err_msg)
        raise HTTPException(status_code=500, detail=f"internal error: {err_msg}")

@app.get("/india/backtest/momentum")
def backtest_momentum(
    lookback_days: int = Query(90, description="Lookback window for momentum"),
    top_n: int = Query(10, description="Number of top stocks to select"),
    start_date: Optional[str] = Query("2021-01-01", description="Backtest start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Backtest end date YYYY-MM-DD")
):
    """
    Run a reproducible momentum backtest using ONLY database data.
    """
    logger.info(f"Endpoint accessed: /india/backtest/momentum")
    
    run_id = start_run("backtest_momentum")
    
    try:
        if not engine:
            raise ValueError("Database engine not connected")
            
        result = run_backtest_momentum(
            engine=engine,
            lookback_days=lookback_days,
            top_n=top_n,
            start_date=start_date,
            end_date=end_date
        )
        
        finish_run(run_id, "success")
        return result
        
    except ValueError as ve:
        err_msg = str(ve)
        logger.error(f"Backtest validation error: {ve}")
        finish_run(run_id, "failed", err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
        
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Backtest internal error: {e}", exc_info=True)
        finish_run(run_id, "failed", err_msg)
        raise HTTPException(status_code=500, detail=f"Backtest error: {err_msg}")



@app.get("/screeners/{screener_type}", response_model=ScreenerResponse)
def get_screener(
    screener_type: str = Path(..., description="Type: momentum, low-vol, value"),
    lookback_days: int = Query(30, description="Lookback days (for momentum)"),
    top_n: int = Query(20, description="Top N results")
):
    """
    Get stocks matching specific quantitative criteria.
    Types:
    - momentum: High momentum (returns)
    - low-vol: Low volatility
    - value: Low P/E (Requires fundamentals ingestion)
    """
    logger.info(f"Endpoint accessed: /screeners/{screener_type}")
    
    if not engine:
        raise HTTPException(status_code=503, detail="DB unavailable")
        
    run_id = start_run(f"screener_{screener_type}")
    
    try:
        if screener_type == "momentum":
            result = get_momentum_screen(engine, lookback_days, top_n)
        elif screener_type == "low-vol":
            result = get_low_vol_screen(engine, top_n)
        elif screener_type == "value":
            result = get_value_screen(engine, top_n)
        else:
            raise HTTPException(status_code=400, detail="Invalid screener type")
            
        if "error" in result:
             raise Exception(result["error"])
             
        finish_run(run_id, "success")
        return result
        
    except Exception as e:
        logger.error(f"Screener failed: {e}")
        finish_run(run_id, "failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/research/backtest")
def run_research_backtest(req: BacktestRequest):
    """
    Run a full factor backtest simulation.
    """
    # Convert request to dict
    params = req.dict()
    
    run_id = start_run(f"backtest_{req.factor}")
    
    try:
        if not engine:
             raise HTTPException(status_code=503, detail="DB unavailable")
             
        result = do_backtest(engine, params)
        if "error" in result:
             finish_run(run_id, "failed", result["error"])
             raise HTTPException(status_code=400, detail=result["error"])
             
        result["run_id"] = run_id
        finish_run(run_id, "success")
        return result
    except Exception as e:
        finish_run(run_id, "failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/research/sweep")
def run_research_sweep(req: SweepRequest):
    """
    Run parameter sweep for robustness check.
    """
    run_id = start_run(f"sweep_{req.factor}")
    results = []
    
    try:
        if not engine: raise HTTPException(status_code=503, detail="DB unavailable")
        
        for lb in req.lookbacks:
            params = req.dict()
            params["lookback_days"] = lb
            # Remove list param
            del params["lookbacks"]
            
            res = do_backtest(engine, params)
            if "error" not in res:
                results.append({
                    "lookback": lb,
                    "sharpe": res["summary"]["sharpe"],
                    "cagr": res["summary"]["cagr"],
                    "volatility": res["summary"]["volatility"]
                })
        
        finish_run(run_id, "success")
        return {"results": results}
    except Exception as e:
        finish_run(run_id, "failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/portfolio/analyze")
def run_portfolio_analysis(req: PortfolioRequest):
    """
    Run institutional-grade portfolio analytics.
    """
    params = req.dict()
    run_id = start_run("portfolio_analysis")
    
    try:
        if not engine: raise HTTPException(status_code=503, detail="DB unavailable")
        
        result = analyze_portfolio_request(engine, params)
        if "error" in result:
             finish_run(run_id, "failed", result["error"])
             raise HTTPException(status_code=400, detail=result["error"])
             
        # Log details to runs? (Optional, maybe input payload)
        # We just finish run
        finish_run(run_id, "success")
        return result
    except Exception as e:
        finish_run(run_id, "failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# 9. Market Monitor Endpoints

@app.get("/market/summary")
def market_summary(as_of: Optional[str] = None):
    """
    Market Summary: Returns, Volatility for Benchmark (^NSEI)
    """
    if not engine:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return get_market_summary(engine)

@app.get("/market/breadth")
def market_breadth(as_of: Optional[str] = None):
    """
    Market Breadth: Advancers, Decliners, DMA stats.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return get_market_breadth(engine)

@app.get("/market/leaders")
def market_leaders(as_of: Optional[str] = None):
    """
    Leaders & Laggards: Top 5 gainers/losers.
    """
    if not engine:
         raise HTTPException(status_code=503, detail="DB unavailable")
    return get_leaders_laggards(engine)

@app.get("/market/advanced_monitor")
def get_advanced_monitor():
    """
    Get professional-grade market situational awareness data.
    """
    logger.info("Endpoint accessed: /market/advanced_monitor")
    
    cache_key = "market:advanced:v1"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
        
    if not engine:
        raise HTTPException(status_code=503, detail="Database engine not available")
    
    try:
        result = get_advanced_market_monitor(engine)
        if "error" in result:
             raise Exception(result["error"])
             
        cache.set(cache_key, result, CACHE_TTL_SEC)
        return result
    except Exception as e:
        logger.error(f"Advanced Monitor Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 10. Security Workbench Endpoints

# ... Existing code ...

@app.get("/market/tickers")
def get_tickers():
    """
    Get list of tickers for the search dropdown.
    """
    try:
        if not os.path.exists(UNIVERSE_PATH):
            return []
        
        df = pd.read_csv(UNIVERSE_PATH)
        # Ensure Symbol column exists
        if "Symbol" not in df.columns:
            return []
            
        tickers = []
        for _, row in df.iterrows():
            sym = row["Symbol"]
            if pd.isna(sym): continue
            
            # Simple cleanup
            clean_sym = str(sym).strip()
            # Try to create a nice label (requires fundamental name which we might not have in CSV)
            # For now, just return the symbol. The Frontend can pretty it up if needed, or we fetch names later.
            # Actually, user wants "Actual Name". 
            # We don't have names in universe.csv, only symbols. 
            # We can't fetch 50 names from Yahoo in real-time.
            # We will return just the symbol for now, but formatted nicely.
            
            tickers.append({
                "value": clean_sym,
                "label": clean_sym.replace(".NS", "")
            })
            
        return tickers
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        return []

@app.get("/security/overview/{symbol}")
def security_overview(symbol: str):
    """
    Get comprehensive security overview (Fundamentals, Risk, Factors).
    """
    if not engine:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return get_security_overview(symbol, engine)

@app.get("/security/performance/{symbol}")
def security_performance(symbol: str):
    """
    Get price history and overlays for charting.
    """
    if not engine:
         raise HTTPException(status_code=503, detail="DB unavailable")
    return get_security_performance(symbol, engine)


if __name__ == "__main__":
    test_health_endpoint()
