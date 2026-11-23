#!/usr/bin/env python3
"""
Sync departments table with department_hierarchy.yaml.
Usage: python scripts/sync_departments.py
"""

import os
import sys
import yaml
import logging
import pymysql
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(PROJECT_ROOT / '.env')

def get_db_connection():
    """Get database connection."""
    return pymysql.connect(
        host=os.getenv('SCHEDULER_DB_HOST', '127.0.0.1'),
        port=int(os.getenv('SCHEDULER_DB_PORT', 3306)),
        user=os.getenv('SCHEDULER_DB_USER', 'root'),
        password=os.getenv('SCHEDULER_DB_PASSWORD', ''),
        database=os.getenv('SCHEDULER_DB_NAME', 'app_reviews_scheduler'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def load_hierarchy():
    """Load department hierarchy from YAML."""
    config_path = PROJECT_ROOT / "app/config/department_hierarchy.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def sync_departments():
    """Sync departments data."""
    try:
        # Load data
        hierarchy = load_hierarchy()
        divisions = hierarchy.get('divisions', {})
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. Truncate table
            logger.info("Truncating departments table...")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute("TRUNCATE TABLE departments")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            
            # 2. Insert Divisions
            logger.info("Inserting divisions...")
            display_order = 1
            for div_code, div_data in divisions.items():
                div_name = div_data.get('name', div_code)
                div_desc = div_data.get('description', '')
                
                sql = """
                INSERT INTO departments 
                (dept_code, dept_name, dept_name_en, parent_dept_code, display_order, created_at, updated_at)
                VALUES (%s, %s, %s, NULL, %s, NOW(), NOW())
                """
                cursor.execute(sql, (div_code, div_name, div_desc, display_order))
                display_order += 1
                
                # 3. Insert Teams
                teams = div_data.get('teams', {})
                team_order = 1
                for team_code, team_data in teams.items():
                    full_code = f"{div_code}.{team_code}"
                    team_name = team_data.get('name', team_code)
                    team_desc = team_data.get('description', '')
                    
                    sql = """
                    INSERT INTO departments 
                    (dept_code, dept_name, dept_name_en, parent_dept_code, display_order, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    """
                    cursor.execute(sql, (full_code, team_name, team_desc, div_code, team_order))
                    team_order += 1
            
            logger.info("Sync completed successfully.")
            
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    sync_departments()
