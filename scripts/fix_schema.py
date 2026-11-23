import logging
import sys
from pathlib import Path
from sqlalchemy import text

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scheduler.utils.database import get_db_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_schema():
    logger.info("Fixing database schema...")
    try:
        with get_db_session() as session:
            # Check current column type (optional, but good for debugging)
            # For now, just blindly alter it to be safe and correct
            
            logger.info("Altering reviews table to ensure content_hash is VARCHAR(64)...")
            session.execute(text("ALTER TABLE reviews MODIFY content_hash VARCHAR(64)"))
            session.commit()
            
            logger.info("Schema fix completed successfully.")
            
    except Exception as e:
        logger.error(f"Failed to fix schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fix_schema()
