import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_mart_and_priority():
    service = get_review_service()
    
    print("\n[Test 1] Verify Mart Data for 2025")
    mart_data = service._get_from_mart(2025, None)
    if mart_data:
        print(f"  Dates count: {len(mart_data.get('dates', []))}")
        print(f"  First Date: {mart_data['dates'][0] if mart_data['dates'] else 'None'}")
        print(f"  Last Date: {mart_data['dates'][-1] if mart_data['dates'] else 'None'}")
        if len(mart_data.get('dates', [])) >= 11: # Should be 11 or 12 depending on data
             print("  ✅ Mart data populated (Count >= 11)")
        else:
             print(f"  ⚠️ Mart data count low: {len(mart_data.get('dates', []))}")
    else:
        print("  ❌ Mart data is None")

    print("\n[Test 2] Verify Priority (OpenSearch -> Mart)")
    dashboard_data = service.get_dashboard_stats_layered(year=2025)
    source = dashboard_data.get('meta', {}).get('source')
    print(f"  Source: {source}")
    
    if source == 'raw':
        print("  ✅ Priority is correct (Raw/OpenSearch)")
    else:
        print(f"  ❌ Priority incorrect or OpenSearch failed (Source: {source})")

if __name__ == "__main__":
    verify_mart_and_priority()
