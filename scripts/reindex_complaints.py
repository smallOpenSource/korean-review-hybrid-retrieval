#!/usr/bin/env python
"""
Reindex complaint documents in OpenSearch with updated field names.
Updates MySQL complaint_dept → complaint_primary_dept mapping to OpenSearch.
Adds new fields: escalated_to, sla_deadline, assigned_to.

Usage:
    python scripts/reindex_complaints.py [--dry-run] [--batch-size 1000]

This script should be run AFTER applying migrations:
- migrations/006_fix_complaint_fields.sql
- migrations/007_add_composite_indexes.sql
"""
import os
import sys
import argparse
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service
from app.core.mysql_client import get_mysql_client


def reindex_complaints(dry_run: bool = False, batch_size: int = 1000):
    """
    Reindex all complaint documents in OpenSearch with updated fields.

    Args:
        dry_run: If True, only print what would be updated without actually updating
        batch_size: Number of documents to process in each batch
    """
    rs = get_review_service()
    mysql = get_mysql_client()

    print("=" * 80)
    print("Complaint Reindexing Script")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    print(f"Batch size: {batch_size}")
    print()

    # Fetch complaint data from MySQL (source of truth)
    print("📊 Fetching complaint data from MySQL...")
    query = """
        SELECT
            review_id,
            complaint_primary_dept,
            complaint_escalated_to,
            complaint_sla_deadline,
            complaint_assigned_to,
            complaint_type,
            complaint_sub_type,
            complaint_urgency,
            complaint_severity,
            complaint_secondary_depts,
            complaint_escalation_required,
            complaint_escalation_level,
            complaint_status
        FROM reviews
        WHERE is_complaint = 1
        ORDER BY created_at DESC
    """

    rows = mysql.execute_all(query)
    total_complaints = len(rows)

    print(f"✅ Found {total_complaints} complaints in MySQL")
    print()

    if total_complaints == 0:
        print("⚠️  No complaints found. Exiting.")
        return

    # Statistics
    stats = {
        'total': total_complaints,
        'updated': 0,
        'failed': 0,
        'skipped': 0,
        'with_escalation': 0,
        'with_sla': 0,
        'with_assigned': 0
    }

    # Process in batches
    print(f"🔄 Processing {total_complaints} complaints...")
    print()

    for i, row in enumerate(rows):
        review_id = row['review_id']

        # Track field usage
        if row.get('complaint_escalated_to'):
            stats['with_escalation'] += 1
        if row.get('complaint_sla_deadline'):
            stats['with_sla'] += 1
        if row.get('complaint_assigned_to'):
            stats['with_assigned'] += 1

        # Build update document
        complaint_update = {
            'primary_dept': row.get('complaint_primary_dept'),
            'type': row.get('complaint_type'),
            'sub_type': row.get('complaint_sub_type'),
            'urgency': row.get('complaint_urgency'),
            'severity': row.get('complaint_severity'),
            'secondary_depts': row.get('complaint_secondary_depts', '').split(',') if row.get('complaint_secondary_depts') else [],
            'escalation_required': bool(row.get('complaint_escalation_required')),
            'escalation_level': row.get('complaint_escalation_level'),
            'escalated_to': row.get('complaint_escalated_to'),
            'status': row.get('complaint_status'),
            'sla_deadline': row.get('complaint_sla_deadline').isoformat() if row.get('complaint_sla_deadline') else None,
            'assigned_to': row.get('complaint_assigned_to')
        }

        if dry_run:
            if i < 5:  # Print first 5 for verification
                print(f"[DRY RUN] Would update {review_id}:")
                print(f"  primary_dept: {complaint_update['primary_dept']}")
                print(f"  escalated_to: {complaint_update['escalated_to']}")
                print(f"  sla_deadline: {complaint_update['sla_deadline']}")
                print(f"  assigned_to: {complaint_update['assigned_to']}")
                print()
            stats['updated'] += 1
            continue

        # Perform actual update
        try:
            update_body = {
                "doc": {
                    "complaint": complaint_update
                }
            }

            rs._os.sync_client.update(
                index=rs._index,
                id=review_id,
                body=update_body,
                retry_on_conflict=3
            )
            stats['updated'] += 1

            # Progress reporting
            if (i + 1) % batch_size == 0:
                progress = ((i + 1) / total_complaints) * 100
                print(f"  Progress: {i + 1}/{total_complaints} ({progress:.1f}%) - "
                      f"Updated: {stats['updated']}, Failed: {stats['failed']}")

        except Exception as e:
            print(f"❌ Failed to update {review_id}: {e}")
            stats['failed'] += 1

    # Final report
    print()
    print("=" * 80)
    print("Reindexing Complete")
    print("=" * 80)
    print(f"Total complaints:       {stats['total']:,}")
    print(f"Successfully updated:   {stats['updated']:,}")
    print(f"Failed:                 {stats['failed']:,}")
    print()
    print("Field Usage Statistics:")
    print(f"  With escalated_to:    {stats['with_escalation']:,} ({stats['with_escalation']/stats['total']*100:.1f}%)")
    print(f"  With SLA deadline:    {stats['with_sla']:,} ({stats['with_sla']/stats['total']*100:.1f}%)")
    print(f"  With assigned_to:     {stats['with_assigned']:,} ({stats['with_assigned']/stats['total']*100:.1f}%)")
    print()

    if stats['failed'] > 0:
        print("⚠️  Some updates failed. Check logs above for details.")
    elif dry_run:
        print("✅ Dry run completed successfully. Run without --dry-run to apply changes.")
    else:
        print("✅ All complaints reindexed successfully!")

    return stats


def verify_reindexing():
    """Verify that reindexing worked correctly."""
    rs = get_review_service()

    print()
    print("🔍 Verifying reindexed data...")

    # Check primary_dept aggregation
    query = {
        "size": 0,
        "query": {
            "term": {"complaint.is_complaint": True}
        },
        "aggs": {
            "by_primary_dept": {
                "terms": {"field": "complaint.primary_dept", "size": 10}
            },
            "by_escalated_to": {
                "terms": {"field": "complaint.escalated_to", "size": 10}
            }
        }
    }

    try:
        resp = rs._os.sync_client.search(index=rs._index, body=query)

        primary_buckets = resp['aggregations']['by_primary_dept']['buckets']
        escalated_buckets = resp['aggregations']['by_escalated_to']['buckets']

        print()
        print("Primary Department Distribution:")
        for bucket in primary_buckets[:5]:
            print(f"  {bucket['key']}: {bucket['doc_count']} complaints")

        print()
        print("Escalated To Distribution:")
        for bucket in escalated_buckets[:5]:
            print(f"  {bucket['key']}: {bucket['doc_count']} complaints")

        print()
        print("✅ Verification complete")

    except Exception as e:
        print(f"❌ Verification failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reindex complaint documents in OpenSearch')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual updates)')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for progress reporting')
    parser.add_argument('--verify', action='store_true', help='Verify reindexing after completion')

    args = parser.parse_args()

    try:
        stats = reindex_complaints(dry_run=args.dry_run, batch_size=args.batch_size)

        if args.verify and not args.dry_run:
            verify_reindexing()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
