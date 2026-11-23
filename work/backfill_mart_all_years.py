import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from scheduler.jobs.aggregate_mart import AggregateMartJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_all_years():
    job = AggregateMartJob()
    
    print("\n[Backfill] Starting backfill for 2010-2025...")
    
    for year in range(2010, 2026):
        print(f"\nProcessing Year {year}...")
        for month in range(1, 13):
            target_date = datetime(year, month, 1)
            try:
                result = job.run(target_date)
                # Only print if something happened or failed
                if result['status'] != 'success' or result['app_stats_updated'] > 0:
                    print(f"  {year}-{month:02d}: {result['status']} (Updated: {result['app_stats_updated']})")
            except Exception as e:
                print(f"  {year}-{month:02d}: Error - {e}")
            
    print("\n[Backfill] Completed.")

if __name__ == "__main__":
    backfill_all_years()
