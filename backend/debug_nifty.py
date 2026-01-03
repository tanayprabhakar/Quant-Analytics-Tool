
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- ^NSEI Last 10 Days ---")
    df = pd.read_sql(text("SELECT date, close, symbol FROM price_daily WHERE symbol = '^NSEI' ORDER BY date DESC LIMIT 10"), conn)
    print(df[["date", "close"]])
    
    if len(df) >= 2:
        curr = df.iloc[0]["close"]
        prev = df.iloc[1]["close"]
        price_ret = (curr - prev) / prev
        print(f"\nLatest: {curr} ({df.iloc[0]['date']})")
        print(f"Prev:   {prev} ({df.iloc[1]['date']})")
        print(f"Calculated 1D Return: {price_ret*100:.2f}%")
        
        # Check Dec 31 vs Dec 30 just in case
        if len(df) >= 3:
             prev2 = df.iloc[2]["close"]
             ret2 = (prev - prev2) / prev2
             print(f"Prev Return (T-1 vs T-2): {ret2*100:.2f}%")

