import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.mysql_client import get_mysql_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_schema():
    client = get_mysql_client()
    
    # Check if system_config table exists
    sql = """
    SELECT count(*) as count
    FROM information_schema.tables 
    WHERE table_schema = DATABASE() 
    AND table_name = 'system_config'
    """
    
    with client.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            result = cursor.fetchone()
            
    if result and result['count'] > 0:
        logger.info("Table 'system_config' exists.")
        
        # Show columns
        with client.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DESCRIBE system_config")
                columns = cursor.fetchall()
                for col in columns:
                    logger.info(f"Column: {col['Field']} ({col['Type']})")
    else:
        logger.info("Table 'system_config' does NOT exist.")

if __name__ == "__main__":
    check_schema()
