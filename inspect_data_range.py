import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect_data_range():
    service = get_review_service()
    client = service._os.sync_client
    index = service._index
    
    query = {
        "size": 0,
        "aggs": {
            "min_date": { "min": { "field": "review_date" } },
            "max_date": { "max": { "field": "review_date" } }
        }
    }
    
    try:
        response = client.search(index=index, body=query)
        aggs = response.get('aggregations', {})
        min_ts = aggs.get('min_date', {}).get('value_as_string')
        max_ts = aggs.get('max_date', {}).get('value_as_string')
        
        print(f"\nData Range in OpenSearch:")
        print(f"  Min Date: {min_ts}")
        print(f"  Max Date: {max_ts}")
        
    except Exception as e:
        print(f"Error querying OpenSearch: {e}")

if __name__ == "__main__":
    inspect_data_range()
