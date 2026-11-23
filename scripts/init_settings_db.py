import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.mysql_client import get_mysql_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_settings_db():
    client = get_mysql_client()
    
    sql_create_table = """
    CREATE TABLE IF NOT EXISTS system_config (
        `key` VARCHAR(100) NOT NULL,
        `value` TEXT,
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (`key`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    # Default settings to insert if not exists
    default_settings = [
        ('llm_provider', 'gemini'),
        ('llm_api_key', ''),
        ('daily_collection_limit', '1000'),
        ('auto_collect', 'true')
    ]
    
    sql_insert_default = """
    INSERT IGNORE INTO system_config (`key`, `value`) VALUES (%s, %s)
    """
    
    try:
        with client.get_connection() as conn:
            with conn.cursor() as cursor:
                # Create table
                logger.info("Creating system_config table...")
                cursor.execute(sql_create_table)
                
                # Insert defaults
                logger.info("Inserting default settings...")
                cursor.executemany(sql_insert_default, default_settings)
                
            conn.commit()
            logger.info("Settings DB initialized successfully.")
            
    except Exception as e:
        logger.error(f"Failed to initialize settings DB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_settings_db()
