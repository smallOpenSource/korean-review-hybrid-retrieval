import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

async def main():
    print("Getting ReviewService...")
    service = get_review_service()
    
    print("Testing aggregate_sentiment...")
    try:
        stats = await service.aggregate_sentiment(days=30)
        print(f"Stats: {stats.keys()}")
        print(f"Total Reviews: {stats.get('total_reviews')}")
    except Exception as e:
        print(f"Error in aggregate_sentiment: {e}")
        import traceback
        traceback.print_exc()

    print("Testing get_complaint_stats...")
    try:
        stats = await service.get_complaint_stats(days=30)
        print(f"Complaint Stats: {stats.keys()}")
        print(f"Total Complaints: {stats.get('total_complaints')}")
    except Exception as e:
        print(f"Error in get_complaint_stats: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
