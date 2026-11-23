import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

def main():
    print("Getting ReviewService...")
    service = get_review_service()
    
    print("Testing aggregate_sentiment_sync...")
    try:
        stats = service.aggregate_sentiment_sync(days=30)
        print(f"Stats: {stats.keys()}")
        print(f"Total Reviews: {stats.get('total_reviews')}")
        print(f"Reviews Change: {stats.get('reviews_change')}")
    except Exception as e:
        print(f"Error in aggregate_sentiment_sync: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
