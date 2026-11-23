#!/usr/bin/env python
"""
Run migration using Python and PyMySQL instead of MySQL CLI.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import get_mysql_client

def run_migration():
    """Execute migration SQL."""
    mysql = get_mysql_client()
    
    with open('migrations/002_create_mart_dept_review_filter_counts.sql', 'r') as f:
        sql = f.read()
    
    print(f"Executing migration SQL...")
    print(f"SQL:\n{sql}\n")
    
    try:
        mysql.execute(sql)
        print("✅ Migration completed successfully!")
        
        # Verify
        result = mysql.execute_one("SHOW CREATE TABLE mart_dept_review_filter_counts")
        print(f"✅ Table created: {result is not None}")
        
    except Exception as e:
        if "already exists" in str(e):
            print("⚠️  Table already exists (OK)")
        else:
            print(f"❌ Error: {e}")
            raise

if __name__ == "__main__":
    run_migration()
