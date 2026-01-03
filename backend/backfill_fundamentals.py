
import os
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging
import uuid
import time
from datetime import timedelta

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
UNIVERSE_PATH = "../universe.csv"

def start_run(run_type):
    run_id = str(uuid.uuid4())
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO runs (run_id, run_type, status) VALUES (:id, :type, 'running')"),
                {"id": run_id, "type": run_type}
            )
        return run_id
    except Exception as e:
        logger.error(f"Failed to start run: {e}")
        return None

def finish_run(run_id, status, error=None):
    if not run_id: return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE runs SET status = :status, error = :error, finished_at = now() WHERE run_id = :id"),
                {"status": status, "error": error, "id": run_id}
            )
    except Exception:
        pass

def backfill_symbol(symbol):
    try:
        t = yf.Ticker(symbol)
        
        # 1. Get Financials (Income Statement for EPS/Net Income)
        # quarterly_income_stmt usually returns last 4-5 quarters.
        fin = t.quarterly_income_stmt
        if fin is None or fin.empty:
            logger.warning(f"{symbol}: No quarterly financials found.")
            return 0
            
        # Transpose so dates are index
        fin = fin.T
        fin.index = pd.to_datetime(fin.index)
        fin = fin.sort_index() # Ascending time
        
        # 2. Get Shares Outstanding
        # Using current as proxy because history is hard to get free.
        info = t.info
        shares = info.get("sharesOutstanding")
        if not shares:
            # Fallback: Try Basic Average Shares from financials if available
            if "Basic Average Shares" in fin.columns:
                shares = fin["Basic Average Shares"].iloc[-1]
            else:
                logger.warning(f"{symbol}: No shares count found.")
                return 0
                
        # 3. Process each available quarter
        # We need TTM EPS. If we have 4 quarters of data [Q1, Q2, Q3, Q4], we can compute TTM for Q4.
        # If we calculate "Net Income" TTM.
        
        # Map fields (yfinance naming varies)
        net_income_col = next((c for c in fin.columns if "Net Income" in c and "Continuous" not in c and "Common" in c), None) # Try "Net Income Common Stockholders"
        if not net_income_col:
             net_income_col = next((c for c in fin.columns if "Net Income" in c), None)

        if not net_income_col:
            logger.warning(f"{symbol}: Net Income column not found.")
            return 0
            
        # Get Price History covering these dates
        start_date = fin.index.min()
        end_date = fin.index.max() + timedelta(days=5) # Buffer
        
        # Existing prices in DB might be enough? check first
        # We construct snapshots at report date (or quarter end?)
        # Convention: Snapshot at Quarter End using data "As Of" that date? 
        # Actually accounting data is released later (Lookahead bias risk).
        # STRICT mode: Data for Q1 (Mar 31) is released ~May 15.
        # However, for this exercise, we often use "As Of" date = Date of Fundamental.
        # But for backtesting, we must know WHEN it was available. 
        # Simplification: We will store "as_of_date" as the Quarter End, but we should acknowledge this has lookahead if used immediately. 
        # BETTER: Use "as_of_date" = Quarter End + 45 days (approx release). 
        # User prompt check: "Inserts snapshot rows with as_of = quarter_end_date". 
        # OK, user requested "as_of = quarter_end_date". We will follow the prompt.
        
        count = 0
        records = []
        
        # Iterate quarters
        # Need 4 rolling quarters for TTM?
        # If we don't have enough history, we might just calculate annualized? 
        # yfinance often gives TTM PE in info, but not historical.
        # Let's try to calculate PE = Price / (Quarterly EPS * 4) as a rough proxy if TTM unavailable,
        # OR just sum last 4 quarters if available.
        
        for date in fin.index:
            # Date is likely quarter end (e.g. 2024-03-31)
            
            # Find TTM Net Income
            # Get window ending at date
            window = fin.loc[:date].tail(4)
            if len(window) < 1: continue # Need at least 1
            
            # If < 4, upscale? Or just use what we have? 
            # If we have 1 quarter, multiply by 4? dangerous but better than null.
            # Let's simple sum available in window (up to 4) * (4/len)
            
            recent_ni = window[net_income_col].sum()
            multiplier = 4.0 / len(window)
            ttm_ni = recent_ni * multiplier # Approximation if short history
            
            ttm_eps = ttm_ni / shares
            
            # Fetch Price at this date
            # Check DB first? Or just yfinance download small chunk
            # Using yfinance download for precision if DB gap
            try:
                # download single day?
                # range: date-3 to date+3 to find close
                p_df = yf.download(symbol, start=date - timedelta(days=5), end=date + timedelta(days=5), progress=False)
                if p_df.empty: 
                     # Try to use next day logic?
                     continue
                
                # Find closes <= date (or exact date?)
                # If as_of = quarter_end_date, we need price AT quarter_end_date.
                # If market closed, use most recent BEFORE.
                
                # Filter p_df <= date
                # Handle MultiIndex
                if isinstance(p_df.columns, pd.MultiIndex):
                     closes = p_df["Close"][symbol]
                else:
                     closes = p_df["Close"]
                     
                past_closes = closes[closes.index <= date]
                if past_closes.empty:
                    # Maybe it was a weekend, take nearest previous?
                    # or just take the very last one in p_df?
                    current_price = float(closes.iloc[0]) # fallback
                else:
                    current_price = float(past_closes.iloc[-1])
                    
            except Exception as e:
                logger.error(f"{symbol}: Price fetch failed: {e}")
                continue
                
            if ttm_eps <= 0:
                pe = None
            else:
                pe = current_price / ttm_eps
                
            mkt_cap = current_price * shares
            
            records.append({
                "symbol": symbol,
                "as_of_date": date.date(),
                "market_cap": int(mkt_cap),
                "pe_ratio": float(pe) if pe else None,
                "eps": float(ttm_eps),
                "sector": info.get("sector")
            })
            
        # Bulk Insert
        if records:
            stmt = text("""
                INSERT INTO fundamentals_snapshot (symbol, as_of_date, market_cap, pe_ratio, eps, sector, source)
                VALUES (:symbol, :as_of_date, :market_cap, :pe_ratio, :eps, :sector, 'backfill')
                ON CONFLICT (symbol, as_of_date) DO NOTHING
            """)
            with engine.begin() as conn:
                conn.execute(stmt, records)
            count = len(records)
            logger.info(f"{symbol}: Backfilled {count} snapshots.")
            
        return count

    except Exception as e:
        logger.error(f"{symbol}: Backfill failed: {e}")
        return 0

def run_backfill():
    run_id = start_run("backfill_fundamentals")
    try:
        df = pd.read_csv(UNIVERSE_PATH)
        symbols = df["Symbol"].tolist()
        
        total = 0
        for sym in symbols:
            total += backfill_symbol(sym)
            time.sleep(1) # Rate limit
            
        finish_run(run_id, "success", f"Backfilled {total} rows")
        print(f"COMPLETE: Backfilled {total} rows.")
        
    except Exception as e:
        logger.error(f"Run failed: {e}")
        finish_run(run_id, "failed", str(e))

if __name__ == "__main__":
    run_backfill()
