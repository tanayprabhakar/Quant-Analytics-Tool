import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Load env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def verify_db():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set!")
        return

    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            # 1. Price Daily Count
            res_price = conn.execute(text("SELECT count(*) FROM price_daily")).scalar()
            logger.info(f"price_daily count: {res_price}")
            
            # 2. Factor Momentum Count
            res_mom = conn.execute(text("SELECT count(*) FROM factor_momentum")).scalar()
            logger.info(f"factor_momentum count: {res_mom}")
            
            # 3. Runs
            res_runs = conn.execute(text("SELECT run_id, run_type, status, started_at, finished_at FROM runs ORDER BY started_at DESC LIMIT 5")).fetchall()
            logger.info("Recent Runs:")
            for row in res_runs:
                logger.info(f" - {row}")

    except Exception as e:
        logger.error(f"Verification failed: {e}")

if __name__ == "__main__":
    verify_db()
