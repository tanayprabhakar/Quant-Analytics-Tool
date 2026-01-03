
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- Price Daily Range ---")
    res = conn.execute(text("SELECT MIN(date), MAX(date), COUNT(DISTINCT symbol) FROM price_daily")).fetchone()
    print(f"Start: {res[0]}")
    print(f"End:   {res[1]}")
    print(f"Symbols: {res[2]}")
    
    print("\n--- Fundamentals Range ---")
    try:
        res_fund = conn.execute(text("SELECT MIN(as_of_date), MAX(as_of_date), COUNT(*) FROM fundamentals_snapshot")).fetchone()
        print(f"Start: {res_fund[0]}")
        print(f"End:   {res_fund[1]}")
        print(f"Rows:  {res_fund[2]}")
    except:
        print("Fundamentals table query failed or empty.")
