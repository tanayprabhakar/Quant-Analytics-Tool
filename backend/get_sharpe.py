import os
from sqlalchemy import create_engine
from backtest_logic import run_backtest_momentum
from dotenv import load_dotenv

load_dotenv("backend/.env")
engine = create_engine(os.getenv("DATABASE_URL"))
result = run_backtest_momentum(engine, lookback_days=90, top_n=10)
print(f"Sharpe Ratio: {result['metrics']['sharpe_ratio']}")
