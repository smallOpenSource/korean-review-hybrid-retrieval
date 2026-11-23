import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.core.mysql_client import get_mysql_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect_mart_status():
    mysql = get_mysql_client()
    
    print("\n[Inspection] Comparing Raw Reviews vs Mart Stats (2010-2025)")
    print(f"{'Year':<6} | {'Month':<6} | {'Raw Count':<12} | {'Mart Rows':<12} | {'Status':<10}")
    print("-" * 60)
    
    for year in range(2010, 2026):
        # Get raw counts by month for this year
        sql_raw = """
            SELECT MONTH(at) as month, COUNT(*) as count 
            FROM reviews 
            WHERE YEAR(at) = %s 
            GROUP BY MONTH(at)
        """
        raw_rows = mysql.execute_all(sql_raw, (year,))
        raw_map = {r['month']: r['count'] for r in raw_rows}
        
        # Get mart counts by month for this year (number of app entries)
        sql_mart = """
            SELECT month, COUNT(*) as count 
            FROM mart_app_stats_monthly 
            WHERE year = %s 
            GROUP BY month
        """
        mart_rows = mysql.execute_all(sql_mart, (year,))
        mart_map = {r['month']: r['count'] for r in mart_rows}
        
        # Check each month
        months_with_data = sorted(list(set(list(raw_map.keys()) + list(mart_map.keys()))))
        
        if not months_with_data:
            continue
            
        for month in months_with_data:
            raw_count = raw_map.get(month, 0)
            mart_count = mart_map.get(month, 0)
            
            status = "OK"
            if raw_count > 0 and mart_count == 0:
                status = "MISSING"
            elif raw_count == 0 and mart_count > 0:
                status = "ORPHAN"
            
            if status != "OK":
                print(f"{year:<6} | {month:<6} | {raw_count:<12} | {mart_count:<12} | {status:<10}")

if __name__ == "__main__":
    inspect_mart_status()
