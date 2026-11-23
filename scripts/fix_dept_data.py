#!/usr/bin/env python
"""
Update existing OpenSearch complaint data with correct primary_dept field.
This fixes the field mapping issue without re-analyzing everything.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service
from app.core.mysql_client import get_mysql_client

def fix_existing_dept_data():
    """Fix primary_dept in existing OpenSearch complaints using MariaDB data."""
    rs = get_review_service()
    mysql = get_mysql_client()
    
    print("Fetching complaint data from MariaDB...")
    # Get all complaints with department info from MariaDB (source of truth)
    query = """
        SELECT review_id, complaint_primary_dept
        FROM reviews
        WHERE is_complaint = 1 AND complaint_primary_dept IS NOT NULL
    """

    rows = mysql.execute_all(query)
    print(f"Found {len(rows)} complaints with dept info in MariaDB")
    
    if not rows:
        print("No department data in MariaDB either - need to re-analyze")
        return
    
    # Update OpenSearch documents
    updated = 0
    failed = 0
    
    for row in rows:
        review_id = row['review_id']
        dept_code = row['complaint_primary_dept']
        
        try:
            # Update only the primary_dept field in OpenSearch
            update_body = {
                "script": {
                    "source": "ctx._source.complaint.primary_dept = params.dept_code",
                    "params": {
                        "dept_code": dept_code
                    }
                }
            }
            
            rs._os.sync_client.update(
                index=rs._index,
                id=review_id,
                body=update_body
            )
            updated += 1
            
            if updated % 100 == 0:
                print(f"Updated {updated} documents...")
                
        except Exception as e:
            print(f"Failed to update {review_id}: {e}")
            failed += 1
    
    print(f"\n✅ Update complete!")
    print(f"  Updated: {updated}")
    print(f"  Failed: {failed}")
    return updated

if __name__ == "__main__":
    fix_existing_dept_data()
