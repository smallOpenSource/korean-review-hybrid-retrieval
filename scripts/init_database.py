import asyncio
import logging
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.config.settings import get_settings
from app.core.mysql_client import get_mysql_client
from app.services.review_service import get_review_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def init_database():
    """Initialize database tables and OpenSearch indices."""
    logger.info("Starting database initialization...")
    
    # 1. Initialize MySQL Tables
    try:
        logger.info("Initializing MySQL tables...")
        mysql = get_mysql_client()
        
        # Check connection first
        with mysql.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                logger.info("MySQL connection successful")
                
                # Create tables
                # Reviews table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    review_id VARCHAR(255) NOT NULL UNIQUE,
                    app_id VARCHAR(255) NOT NULL,
                    content TEXT,
                    rating INT,
                    review_date DATETIME,
                    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    content_hash VARCHAR(64),
                    is_duplicate BOOLEAN DEFAULT FALSE,
                    INDEX idx_app_id (app_id),
                    INDEX idx_review_date (review_date),
                    INDEX idx_content_hash (content_hash)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)
                logger.info("Created 'reviews' table")
                
                # Job runs table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_runs (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    job_name VARCHAR(255) NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    status VARCHAR(50),
                    result JSON,
                    error_message TEXT,
                    INDEX idx_job_name (job_name),
                    INDEX idx_start_time (start_time)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)
                logger.info("Created 'job_runs' table")

                # App Metadata table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_metadata (
                    package_id VARCHAR(255) PRIMARY KEY,
                    company_code VARCHAR(50),
                    group_code VARCHAR(50),
                    company_name VARCHAR(255),
                    priority VARCHAR(20),
                    title VARCHAR(255),
                    developer VARCHAR(255),
                    genre VARCHAR(100),
                    score FLOAT,
                    ratings INT,
                    reviews INT,
                    version VARCHAR(255),
                    updated DATETIME,
                    last_collected DATETIME
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                """)
                logger.info("Created 'app_metadata' table")
                
            conn.commit()
            
    except Exception as e:
        logger.error(f"Failed to initialize MySQL: {e}")
        # We don't raise here to allow OpenSearch init to proceed if DB fails
        # depending on requirements. But for now let's log and continue.
    
    # 2. Initialize OpenSearch Indices
    try:
        logger.info("Initializing OpenSearch indices...")
        review_service = get_review_service()
        
        # This will create the index if it doesn't exist, using the mapping defined in the service
        await review_service.ensure_index()
        logger.info(f"Verified index '{review_service._index}'")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenSearch: {e}")
        raise

    logger.info("Initialization completed")

if __name__ == "__main__":
    asyncio.run(init_database())
