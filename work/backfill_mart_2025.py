import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from scheduler.jobs.aggregate_mart import AggregateMartJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_2025():
    job = AggregateMartJob()
    
    print("\n[Backfill] Starting backfill for 2025...")
    
    for month in range(1, 13):
        target_date = datetime(2025, month, 1)
        print(f"  Processing 2025-{month:02d}...")
        try:
            result = job.run(target_date)
            print(f"    Result: {result['status']}")
        except Exception as e:
            print(f"    Error: {e}")
            
    print("\n[Backfill] Completed.")

if __name__ == "__main__":
    backfill_2025()
