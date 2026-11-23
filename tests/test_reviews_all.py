#!/usr/bin/env python3
"""
Test reviews_all function to identify crash cause.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_play_scraper import reviews_all

def test_reviews_all():
    """Test fetching all reviews."""
    package_id = 'com.example.bank_a'
    
    print(f"Starting reviews_all for {package_id}...")
    print(f"This may take a while and use significant memory.")
    
    try:
        result = reviews_all(
            package_id,
            lang='ko',
            country='kr',
            sort='NEWEST',
            sleep_milliseconds=100
        )
        
        print(f"✓ Success! Fetched {len(result)} reviews")
        return True
        
    except KeyboardInterrupt:
        print(f"\n✗ Interrupted by user")
        return False
    except MemoryError as e:
        print(f"\n✗ Memory Error: {e}")
        print("  - reviews_all() may be trying to load too many reviews into memory")
        return False
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    import resource
    
    # Print memory limits
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    print(f"Memory limit: soft={soft}, hard={hard}")
    
    test_reviews_all()
