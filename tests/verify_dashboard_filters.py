import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_filters():
    service = get_review_service()
    
    print("\n=== Verifying Dashboard Filters ===")
    
    # 1. Verify Year Filter (2025)
    print("\n[Test 1] Year Filter (2025)")
    stats_2025 = service.aggregate_sentiment_sync(year=2025)
    # Check if we got data and if it looks reasonable (not empty if data exists)
    print(f"  Total Reviews (2025): {stats_2025.get('total_reviews')}")
    print(f"  Avg Rating (2025): {stats_2025.get('average_rating')}")
    
    # Compare with 2024 (should be different or empty)
    stats_2024 = service.aggregate_sentiment_sync(year=2024)
    print(f"  Total Reviews (2024): {stats_2024.get('total_reviews')}")
    
    # 2. Verify Category Filter (Banks='1')
    print("\n[Test 2] Category Filter (Banks)")
    # We need to know which apps are banks to verify, but for now we check if numbers change
    stats_all = service.aggregate_sentiment_sync(days=30)
    stats_banks = service.aggregate_sentiment_sync(days=30, category='1')
    
    print(f"  Total Reviews (All, 30d): {stats_all.get('total_reviews')}")
    print(f"  Total Reviews (Banks, 30d): {stats_banks.get('total_reviews')}")
    
    if stats_all.get('total_reviews', 0) >= stats_banks.get('total_reviews', 0):
        print("  ✅ Banks count <= All count")
    else:
        print("  ❌ Logic Error: Banks count > All count")

    # 3. Verify Combined Filter (Year 2025 + Banks)
    print("\n[Test 3] Combined Filter (2025 + Banks)")
    stats_combined = service.aggregate_sentiment_sync(year=2025, category='1')
    print(f"  Total Reviews (2025 + Banks): {stats_combined.get('total_reviews')}")
    
    # 4. Verify Complaint Stats Filter
    print("\n[Test 4] Complaint Stats Filter (2025)")
    complaints_2025 = service.get_complaint_stats_sync(year=2025)
    print(f"  Total Complaints (2025): {complaints_2025.get('total_complaints')}")
    
    # 5. Verify App Rankings Filter
    print("\n[Test 5] App Rankings Filter (2025)")
    rankings_2025 = service.get_app_rankings_sync(year=2025)
    print(f"  Top Apps (2025): {len(rankings_2025.get('top', []))}")
    if rankings_2025.get('top'):
        print(f"  Top 1: {rankings_2025['top'][0]}")

if __name__ == "__main__":
    verify_filters()
