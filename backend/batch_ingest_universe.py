#!/usr/bin/env python3
"""
Batch Ingestion Script for Universe Stocks

This script pre-downloads 5 years of historical data for all stocks
in universe.csv to avoid slow on-demand downloads during user sessions.

Run this script periodically (e.g., daily after market close) to keep data fresh.

Usage:
    python batch_ingest_universe.py                    # Ingest all (skips already-ingested)
    python batch_ingest_universe.py --start-from 196   # Resume from symbol #196
    python batch_ingest_universe.py --force             # Re-ingest everything
"""

import os
import sys
import time
import argparse
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
UNIVERSE_PATH = os.getenv("UNIVERSE_PATH", "../universe.csv")

if not DATABASE_URL:
    logger.error("DATABASE_URL not found in environment variables")
    sys.exit(1)

# Create engine
engine = create_engine(DATABASE_URL)


def get_ingested_symbols() -> set:
    """Get set of symbols that already have data in the database."""
    try:
        query = text("SELECT DISTINCT symbol FROM price_daily")
        with engine.connect() as conn:
            result = conn.execute(query)
            return {row[0] for row in result}
    except Exception as e:
        logger.error(f"Error checking existing symbols: {e}")
        return set()


def store_prices(df: pd.DataFrame, symbol: str):
    """
    Store DataFrame (yfinance format) into price_daily table.
    """
    if df.empty:
        return 0

    try:
        records = []
        for index, row in df.iterrows():
            date_val = index.date() if isinstance(index, pd.Timestamp) else row.get("Date")
            
            records.append({
                "symbol": symbol,
                "date": date_val,
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0))
            })

        if not records:
            return 0

        query = text("""
            INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
            VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
            ON CONFLICT (symbol, date) DO NOTHING
        """)

        with engine.begin() as conn:
            conn.execute(query, records)
            return len(records)

    except Exception as e:
        logger.error(f"Error storing prices for {symbol}: {e}")
        return 0


def ingest_symbol(symbol: str) -> bool:
    """
    Download and store 5 years of data for a single symbol.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"Fetching {symbol}...")
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5y")
        
        if hist.empty:
            logger.warning(f"No data returned for {symbol}")
            return False
        
        count = store_prices(hist, symbol)
        logger.info(f"✓ {symbol}: Stored {count} records")
        return True
        
    except Exception as e:
        logger.error(f"✗ {symbol}: Failed - {e}")
        return False


def main():
    """
    Main ingestion routine with resume support.
    """
    parser = argparse.ArgumentParser(description="Batch ingest universe stock data")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Start from symbol number N (1-indexed, matches CSV row)")
    parser.add_argument("--force", action="store_true",
                        help="Re-ingest all symbols even if already in DB")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay in seconds between Yahoo requests (default: 0.5)")
    args = parser.parse_args()

    start_time = datetime.now()
    
    # Read universe
    if not os.path.exists(UNIVERSE_PATH):
        logger.error(f"Universe file not found: {UNIVERSE_PATH}")
        sys.exit(1)
    
    universe = pd.read_csv(UNIVERSE_PATH)
    if "Symbol" not in universe.columns:
        logger.error("Universe CSV missing 'Symbol' column")
        sys.exit(1)
    
    # Deduplicate symbols while preserving order
    symbols = list(dict.fromkeys(universe["Symbol"].dropna().tolist()))
    
    # Add benchmark
    if "^NSEI" not in symbols:
        symbols.append("^NSEI")
    
    # Get already-ingested symbols to skip
    existing = set()
    if not args.force:
        existing = get_ingested_symbols()
        if existing:
            logger.info(f"Found {len(existing)} symbols already in DB (will skip)")

    # Slice from start_from (1-indexed → 0-indexed)
    start_idx = max(0, args.start_from - 1)
    symbols_to_process = symbols[start_idx:]

    logger.info(f"Processing symbols {args.start_from} to {len(symbols)} ({len(symbols_to_process)} total)")
    logger.info("=" * 60)
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for i, symbol in enumerate(symbols_to_process, args.start_from):
        # Skip if already ingested (unless --force)
        if symbol in existing:
            logger.info(f"[{i}/{len(symbols)}] ⏭ {symbol} (already in DB)")
            skip_count += 1
            continue

        logger.info(f"[{i}/{len(symbols)}] Processing {symbol}")
        
        if ingest_symbol(symbol):
            success_count += 1
        else:
            fail_count += 1
        
        # Small delay between requests to be nice to Yahoo
        if i < len(symbols):
            time.sleep(args.delay)
    
    # Summary
    duration = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info(f"Ingestion complete in {duration:.1f}s")
    logger.info(f"✓ Success: {success_count}")
    logger.info(f"⏭ Skipped: {skip_count}")
    logger.info(f"✗ Failed: {fail_count}")
    logger.info(f"Total processed: {success_count + skip_count + fail_count}")

if __name__ == "__main__":
    main()
