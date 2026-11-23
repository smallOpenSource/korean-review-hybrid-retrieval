import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.core.mysql_client import get_mysql_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App Data (Source of Truth)
APPS = [
    {'package_id': 'com.example.pay_e', 'name': 'E페이', 'code': 'pay_e', 'group': 'fintech', 'priority': 'high'},
    {'package_id': 'com.example.bank_l', 'name': 'L은행', 'code': 'bank_l', 'group': 'fintech', 'priority': 'high'},
    {'package_id': 'com.example.bank_k', 'name': 'K은행', 'code': 'bank_k', 'group': 'internet_bank', 'priority': 'high'},
    {'package_id': 'com.example.bank_m', 'name': 'M은행', 'code': 'bank_m', 'group': 'internet_bank', 'priority': 'high'},
    {'package_id': 'com.example.bank_c', 'name': 'C은행', 'code': 'bank_c', 'group': 'bank', 'priority': 'high'},
    {'package_id': 'com.example.bank_b', 'name': 'B은행', 'code': 'bank_b', 'group': 'bank', 'priority': 'high'},
    {'package_id': 'com.example.bank_a', 'name': 'A은행', 'code': 'bank_a', 'group': 'bank', 'priority': 'high'},
    {'package_id': 'com.example.bank_d', 'name': 'D은행', 'code': 'bank_d', 'group': 'bank', 'priority': 'high'},
]

def seed_app_metadata():
    logger.info("Seeding app_metadata table...")
    mysql = get_mysql_client()
    
    with mysql.get_connection() as conn:
        with conn.cursor() as cursor:
            # Check if table exists
            cursor.execute("SHOW TABLES LIKE 'app_metadata'")
            if not cursor.fetchone():
                logger.error("Table 'app_metadata' does not exist. Run init_database.py first.")
                return

            for app in APPS:
                logger.info(f"Inserting/Updating {app['name']}...")
                cursor.execute("""
                    INSERT INTO app_metadata (
                        package_id, company_code, company_name, group_code, priority, 
                        title, developer, genre, score, ratings, reviews, version, updated, last_collected
                    ) VALUES (
                        %s, %s, %s, %s, %s, 
                        %s, %s, 'Finance', 0, 0, 0, '0.0.0', NOW(), NULL
                    ) ON DUPLICATE KEY UPDATE
                        company_name = VALUES(company_name),
                        group_code = VALUES(group_code),
                        priority = VALUES(priority)
                """, (
                    app['package_id'], app['code'], app['name'], app['group'], app['priority'],
                    app['name'], 'Developer'
                ))
        conn.commit()
    logger.info("Seeding completed.")

if __name__ == "__main__":
    seed_app_metadata()
