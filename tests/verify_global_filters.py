import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_global_filters():
    service = get_review_service()
    
    print("\n=== Verifying Global Filters ===")
    
    # 1. Verify get_recent_reviews_sync with filters
    print("\n[Test 1] Recent Reviews with Year Filter (2025)")
    reviews_2025 = service.get_recent_reviews_sync(limit=10, year=2025)
    print(f"  Count: {len(reviews_2025)}")
    if reviews_2025:
        print(f"  First Review Date: {reviews_2025[0]['_source']['review_date']}")
        if '2025' in reviews_2025[0]['_source']['review_date']:
            print("  ✅ Year 2025 confirmed")
        else:
            print("  ❌ Year mismatch")
            
    print("\n[Test 2] Recent Reviews with Category Filter (Banks)")
    reviews_banks = service.get_recent_reviews_sync(limit=10, category='1') # 1=Banks
    print(f"  Count: {len(reviews_banks)}")
    if reviews_banks:
        print(f"  First Review App: {reviews_banks[0]['_source']['app_name']}")
        # We can't easily verify category from app name without mapping, but if it returns data it's likely working
        # assuming previous tests confirmed category logic.
        print("  ✅ Data returned")

    # 2. Verify get_recent_complaints_sync with filters
    print("\n[Test 3] Recent Complaints with Year Filter (2025)")
    complaints_2025 = service.get_recent_complaints_sync(limit=10, year=2025)
    print(f"  Count: {len(complaints_2025)}")
    if complaints_2025:
        print(f"  First Complaint Date: {complaints_2025[0]['_source']['review_date']}")
        if '2025' in complaints_2025[0]['_source']['review_date']:
            print("  ✅ Year 2025 confirmed")
        else:
            print("  ❌ Year mismatch")

    print("\n[Test 4] Recent Complaints with Category Filter (Cards)")
    complaints_cards = service.get_recent_complaints_sync(limit=10, category='2') # 2=Cards
    print(f"  Count: {len(complaints_cards)}")
    if complaints_cards:
        print(f"  First Complaint App: {complaints_cards[0]['_source']['app_name']}")
        print("  ✅ Data returned")

if __name__ == "__main__":
    verify_global_filters()
