#!/usr/bin/env python
"""Debug aggregation query."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service
from datetime import datetime, timedelta

rs = get_review_service()
end_date = datetime.utcnow()
start_30d = end_date - timedelta(days=30)

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
        "apps": {
            "terms": {"field": "app_id", "size": 100},
            "aggs": {
                "depts": {
                    "terms": {"field": "complaint.primary_dept", "size": 50},
                    "aggs": {
                        "last_30_days": {
                            "filter": {
                                "range": {
                                    "review_date": {"gte": start_30d.isoformat()}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

resp = rs._os.sync_client.search(index=rs._index, body=query)

print(f"Total hits: {resp['hits']['total']['value']}")
print(f"App buckets: {len(resp['aggregations']['apps']['buckets'])}")

if resp['aggregations']['apps']['buckets']:
    first_app = resp['aggregations']['apps']['buckets'][0]
    print(f"\nFirst app: {first_app['key']}, doc_count: {first_app['doc_count']}")
    print(f"Dept buckets: {len(first_app.get('depts', {}).get('buckets', []))}")
    
    if first_app.get('depts', {}).get('buckets'):
        first_dept = first_app['depts']['buckets'][0]
        print(f"First dept: {first_dept['key']}, count: {first_dept['doc_count']}")
        print(f"Last 30 days count: {first_dept.get('last_30_days', {}).get('doc_count', 'N/A')}")
