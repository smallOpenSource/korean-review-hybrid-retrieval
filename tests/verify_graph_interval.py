import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_graph_interval():
    service = get_review_service()
    
    print("\n[Test 1] Year Filter (2024) -> Should use MONTH interval")
    result_year = service.aggregate_sentiment_sync(year=2024)
    buckets_year = result_year.get('sentiment_trend', [])
    print(f"  Buckets count: {len(buckets_year)}")
    if len(buckets_year) > 0:
        print(f"  First bucket: {buckets_year[0]['key_as_string']}")
        # Check if interval looks like month (approx 30 days diff or just count)
        # 2024 should have 12 buckets if data exists for all months, or at least < 366
        if len(buckets_year) <= 12:
             print("  ✅ Interval likely MONTH (Count <= 12)")
        else:
             print(f"  ❌ Interval likely DAY (Count {len(buckets_year)} > 12)")

    print("\n[Test 2] Days Filter (30) -> Should use DAY interval")
    result_day = service.aggregate_sentiment_sync(days=30)
    buckets_day = result_day.get('sentiment_trend', [])
    print(f"  Buckets count: {len(buckets_day)}")
    if 28 <= len(buckets_day) <= 31:
        print("  ✅ Interval likely DAY")
    else:
        print(f"  ⚠️ Unexpected count: {len(buckets_day)}")

    print("\n[Test 3] Days Filter (100) -> Should use WEEK interval")
    result_week = service.aggregate_sentiment_sync(days=100)
    buckets_week = result_week.get('sentiment_trend', [])
    print(f"  Buckets count: {len(buckets_week)}")
    # 100 days / 7 = approx 14-15 weeks
    if 12 <= len(buckets_week) <= 16:
        print("  ✅ Interval likely WEEK")
    else:
        print(f"  ⚠️ Unexpected count: {len(buckets_week)}")

if __name__ == "__main__":
    verify_graph_interval()
