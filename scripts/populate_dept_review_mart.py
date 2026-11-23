#!/usr/bin/env python
"""
Manual script to populate mart_dept_review_filter_counts table.
Run this when scheduler is unavailable.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service
from app.core.mysql_client import get_mysql_client
from datetime import datetime, timedelta

def populate_mart():
    """Populate mart table with aggregated data from OpenSearch."""
    rs = get_review_service()
    mysql = get_mysql_client()
    
    print("Starting mart population...")
    
    # Define time ranges
    end_date = datetime.utcnow()
    start_30d = end_date - timedelta(days=30)
    
    # Query OpenSearch for aggregations (app_id only, since primary_dept is null)
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
    
    print("Querying OpenSearch...")
    resp = rs._os.sync_client.search(index=rs._index, body=query)
    
    # Clear existing data
    print("Truncating old data...")
    mysql.execute("TRUNCATE TABLE mart_dept_review_filter_counts")
    
    # Insert aggregated data
    # Since primary_dept is null for all records, we use 'ALL' as dept_code
    print("Inserting new data...")
    count = 0
    for app_bucket in resp['aggregations']['apps']['buckets']:
        app_id = app_bucket['key']
        total_count = app_bucket['doc_count']
        last_30d_count = app_bucket['last_30_days']['doc_count']
        
        mysql.execute(
            """
            INSERT INTO mart_dept_review_filter_counts
            (app_id, dept_code, review_count, last_30_days_count, last_updated)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (app_id, 'ALL', total_count, last_30d_count)
        )
        count += 1
    
    print(f"✅ Mart populated successfully! {count} records inserted.")
    return count

if __name__ == "__main__":
    try:
        populate_mart()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
