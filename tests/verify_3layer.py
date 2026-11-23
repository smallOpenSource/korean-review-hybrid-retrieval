import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_layers():
    service = get_review_service()
    
    print("\n=== Verifying Layer 1: Mart (Year 2025) ===")
    try:
        # We know 2025 has data from backfill/aggregation
        data = service.get_dashboard_stats_layered(year=2025)
        if data and data.get('meta', {}).get('source') == 'mart':
            print("✅ Layer 1 Success: Source is 'mart'")
            print(f"   Series count: {len(data.get('series', []))}")
        else:
            print(f"❌ Layer 1 Failed: {data.get('meta') if data else 'No data'}")
    except Exception as e:
        print(f"❌ Layer 1 Error: {e}")

    print("\n=== Verifying Layer 2: Raw (Last 30 Days) ===")
    try:
        # Default behavior (no year)
        data = service.get_dashboard_stats_layered(days=30)
        if data and data.get('meta', {}).get('source') == 'raw':
            print("✅ Layer 2 Success: Source is 'raw'")
            print(f"   Series count: {len(data.get('series', []))}")
        else:
            print(f"❌ Layer 2 Failed: {data.get('meta') if data else 'No data'}")
    except Exception as e:
        print(f"❌ Layer 2 Error: {e}")

    print("\n=== Verifying Layer 3: Fallback (Year 2030) ===")
    try:
        # Future year with no data
        data = service.get_dashboard_stats_layered(year=2030)
        if data and data.get('meta', {}).get('source') == 'fallback':
            print("✅ Layer 3 Success: Source is 'fallback'")
            print(f"   Series count: {len(data.get('series', []))}")
        else:
            # Note: If get_dashboard_stats_layered returns None for Mart failure, 
            # it might try Raw. But Raw for 2030 will also be empty.
            # So it should hit fallback.
            print(f"❌ Layer 3 Failed: {data.get('meta') if data else 'No data'}")
    except Exception as e:
        print(f"❌ Layer 3 Error: {e}")

if __name__ == "__main__":
    verify_layers()
