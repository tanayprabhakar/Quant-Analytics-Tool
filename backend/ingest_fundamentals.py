
import os
import sys
import logging
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime
import uuid

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
UNIVERSE_PATH = os.getenv("UNIVERSE_PATH", "../universe.csv") # Adjust if needed relative to backend

if not DATABASE_URL:
    logger.error("DATABASE_URL not found")
    sys.exit(1)

# Create engine
engine = create_engine(DATABASE_URL)

def start_run(run_type: str):
    try:
        run_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO runs (run_id, run_type, status) VALUES (:run_id, :run_type, 'running')"),
                         {"run_id": run_id, "run_type": run_type})
        return run_id
    except Exception as e:
        logger.error(f"Failed to start run logging: {e}")
        return None

def finish_run(run_id, status, error=None):
    if not run_id: return
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE runs SET status = :status, error = :error, finished_at = now() WHERE run_id = :run_id"),
                         {"run_id": run_id, "status": status, "error": error})
    except Exception as e:
        logger.error(f"Failed to finish run logging: {e}")

def ingest_fundamentals():
    run_id = start_run("ingest_fundamentals")
    
    try:
        if not os.path.exists(UNIVERSE_PATH):
             # Try local directory if ../ fails
             if os.path.exists("universe.csv"):
                 u_path = "universe.csv"
             elif os.path.exists("../universe.csv"):
                 u_path = "../universe.csv"
             else:
                 raise FileNotFoundError(f"Universe file not found at {UNIVERSE_PATH}")
        else:
             u_path = UNIVERSE_PATH
             
        logger.info(f"Reading universe from {u_path}...")
        universe = pd.read_csv(u_path)
        if "Symbol" not in universe.columns:
            raise ValueError("Universe CSV missing 'Symbol' column")
        
        symbols = universe["Symbol"].dropna().unique().tolist()
        logger.info(f"Found {len(symbols)} symbols to process.")
        
        today = datetime.now().date()
        
        success_count = 0
        fail_count = 0
        
        for i, symbol in enumerate(symbols, 1):
            try:
                # logger.info(f"[{i}/{len(symbols)}] Fetching {symbol}...") # Reduced log spam
                
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                # Extract Data
                # Rules: Handle missing data gracefully (None)
                
                # Market Cap
                mcap = info.get("marketCap")
                
                # PE Ratio: Try trailing, then forward. 0 is valid? Usually PE > 0.
                # If None, store None.
                pe = info.get("trailingPE")
                
                # EPS
                eps = info.get("trailingEps")
                
                # Sector
                sector = info.get("sector")
                
                # Insert
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
                        "symbol": symbol,
                        "date": today,
                        "mcap": mcap,
                        "pe": pe,
                        "eps": eps,
                        "sector": sector
                    })
                
                success_count += 1
                if i % 5 == 0:
                    logger.info(f"Processed {i}/{len(symbols)} (Success: {success_count})")
                    
            except Exception as e:
                logger.warning(f"Failed {symbol}: {e}")
                fail_count += 1
                
        logger.info("="*40)
        logger.info(f"Ingestion Complete. Success: {success_count}, Failed: {fail_count}")
        finish_run(run_id, "success")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        finish_run(run_id, "failed", str(e))
        sys.exit(1)

if __name__ == "__main__":
    ingest_fundamentals()
