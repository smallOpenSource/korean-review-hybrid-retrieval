#!/usr/bin/env python
"""
Verify escalated_to field works for aggregation.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service

rs = get_review_service()

# Test escalated_to aggregation
query = {
    "size": 0,
    "query": {
        "bool": {
            "must": [
                {"exists": {"field": "sentiment"}},
                {"term": {"complaint.is_complaint": True}}
            ]
        }
    },
    "aggs": {
        "escalated_to_check": {
            "terms": {"field": "complaint.escalated_to", "size": 10}
        }
    }
}

resp = rs._os.sync_client.search(index=rs._index, body=query)
buckets = resp['aggregations']['escalated_to_check']['buckets']

print(f"escalated_to aggregation: {len(buckets)} buckets")
if buckets:
    print("\nSample departments:")
    for b in buckets[:5]:
        print(f"  {b['key']}: {b['doc_count']} reviews")
else:
    print("ERROR: Still no buckets!")
