#!/usr/bin/env python
"""
Reset complaints for re-analysis by removing sentiment/category fields.
This makes them appear as 'unanalyzed' so they will be re-analyzed with correct dept mapping.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service

def reset_complaints():
    """Remove sentiment and category fields from complaints in OpenSearch."""
    rs = get_review_service()
    
    print("Resetting complaints for re-analysis...")
    print(f"Index: {rs._index}")
    
    # Update query to remove sentiment and category fields
    query = {
        'query': {
            'term': {'complaint.is_complaint': True}
        },
        'script': {
            'source': 'ctx._source.remove("sentiment"); ctx._source.remove("category");'
        }
    }
    
    try:
        result = rs._os.sync_client.update_by_query(
            index=rs._index,
            body=query,
            conflicts='proceed',
            wait_for_completion=True
        )
        
        print(f"\n✅ Reset complete!")
        print(f"  Updated: {result['updated']} documents")
        print(f"  Version conflicts: {result.get('version_conflicts', 0)}")
        print(f"  Failures: {len(result.get('failures', []))}")
        
        if result.get('failures'):
            print(f"\n⚠️  Failures:")
            for failure in result['failures'][:5]:
                print(f"  - {failure}")
        
        return result['updated']
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

if __name__ == "__main__":
    reset_complaints()
