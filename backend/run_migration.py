
import os
import logging
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Load env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set!")
        sys.exit(1)

    try:
        engine = create_engine(DATABASE_URL)
        
        migration_file = "migration_fundamentals.sql"
        if not os.path.exists(migration_file):
             logger.error(f"Migration file {migration_file} not found")
             sys.exit(1)
             
        with open(migration_file, "r") as f:
            sql_script = f.read()

        logger.info(f"Applying migration from {migration_file}...")
        
        # Split by ; to handle multiple statements if needed, though execute typically handles this or use text()
        # With sqlalchemy text(), we usually execute statement by statement or block depending on driver.
        # Simple split approach for safety:
        statements = sql_script.split(";")
        
        with engine.begin() as conn:
            for stmt in statements:
                if stmt.strip():
                    conn.execute(text(stmt))
                    
        logger.info("Migration applied successfully!")
        
        # Verify
        with engine.connect() as conn:
             exists = conn.execute(text("SELECT to_regclass('public.fundamentals_snapshot')")).scalar()
             logger.info(f"Verification - Table 'fundamentals_snapshot': {exists}")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
