import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.core.mysql_client import get_mysql_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_sync_column():
    """Add synced_to_opensearch column to reviews table."""
    try:
        mysql = get_mysql_client()
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                # Check if column exists
                cursor.execute("""
                    SELECT count(*) 
                    FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'reviews' 
                    AND COLUMN_NAME = 'synced_to_opensearch'
                """)
                if cursor.fetchone()[0] == 0:
                    logger.info("Adding synced_to_opensearch column...")
                    cursor.execute("""
                        ALTER TABLE reviews 
                        ADD COLUMN synced_to_opensearch BOOLEAN DEFAULT FALSE,
                        ADD INDEX idx_synced (synced_to_opensearch)
                    """)
                    conn.commit()
                    logger.info("Column added successfully")
                else:
                    logger.info("Column already exists")
                    
    except Exception as e:
        logger.error(f"Failed to add column: {e}")

if __name__ == "__main__":
    add_sync_column()
