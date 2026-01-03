
import os
import sys
import logging
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def fix_nifty():
    symbol = "^NSEI"
    logger.info(f"Fetching latest data for {symbol}...")
    
    # Fetch last 5 days
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="1d")
    
    if df.empty:
        logger.error("No data fetched from Yahoo!")
        return

    print("--- Yahoo Data (Latest) ---")
    print(df[["Close", "Volume"]].tail())
    
    # Store in DB
    records = []
    for index, row in df.iterrows():
        records.append({
            "symbol": symbol,
            "date": index.date(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"])
        })
        
    query = text("""
        INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
        VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
        ON CONFLICT (symbol, date) DO UPDATE 
        SET close = EXCLUDED.close, 
            high = EXCLUDED.high, 
            low = EXCLUDED.low,
            open = EXCLUDED.open,
            volume = EXCLUDED.volume
    """)
    
    with engine.begin() as conn:
        for r in records:
            conn.execute(query, r)
            
    logger.info(f"Updated {len(records)} records for {symbol}")

if __name__ == "__main__":
    fix_nifty()
