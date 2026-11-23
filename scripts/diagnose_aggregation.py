#!/usr/bin/env python
"""
Step 1: Check actual OpenSearch data structure.
"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service

rs = get_review_service()

# Get a sample document
query = {
    "size": 1,
    "query": {
        "bool": {
            "must": [
                {"exists": {"field": "sentiment"}},
                {"term": {"complaint.is_complaint": True}}
            ]
        }
    }
}

print("=== Step 1: Sample Document ===")
resp = rs._os.sync_client.search(index=rs._index, body=query)

if resp['hits']['hits']:
    doc = resp['hits']['hits'][0]['_source']
    print(f"app_id: {doc.get('app_id', 'NOT FOUND')}")
    print(f"complaint structure:")
    print(json.dumps(doc.get('complaint', {}), indent=2))
else:
    print("No documents found!")

print("\n=== Step 2: Check Field Mapping ===")
# Check if fields are keyword type
mapping_query = {
    "size": 0,
    "aggs": {
        "app_id_check": {
            "terms": {"field": "app_id", "size": 5}
        }
    }
}

try:
    resp2 = rs._os.sync_client.search(index=rs._index, body=mapping_query)
    print(f"app_id aggregation works: {len(resp2.get('aggregations', {}).get('app_id_check', {}).get('buckets', []))} buckets")
    if resp2['aggregations']['app_id_check']['buckets']:
        print(f"Sample app_ids: {[b['key'] for b in resp2['aggregations']['app_id_check']['buckets'][:3]]}")
except Exception as e:
    print(f"app_id aggregation error: {e}")

print("\n=== Step 3: Check complaint.primary_dept ===")
dept_query = {
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
        "dept_check": {
            "terms": {"field": "complaint.primary_dept", "size": 5}
        }
    }
}

try:
    resp3 = rs._os.sync_client.search(index=rs._index, body=dept_query)
    print(f"dept aggregation works: {len(resp3.get('aggregations', {}).get('dept_check', {}).get('buckets', []))} buckets")
    if resp3['aggregations']['dept_check']['buckets']:
        print(f"Sample depts: {[b['key'] for b in resp3['aggregations']['dept_check']['buckets'][:3]]}")
except Exception as e:
    print(f"dept aggregation error: {e}")
