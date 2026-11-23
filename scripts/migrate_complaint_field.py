#!/usr/bin/env python3
"""
Migrate is_complaint field from root to complaint.is_complaint.

This script fixes legacy data where is_complaint was stored at root level
instead of inside the complaint object.

Target: 6,632 documents with root-level is_complaint field
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.opensearch_client import get_opensearch_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_complaint_field():
    """Migrate is_complaint from root to complaint.is_complaint."""
    os_client = get_opensearch_client()
    client = os_client.sync_client
    index = 'app_reviews'
    
    # Step 1: Find documents with root-level is_complaint
    logger.info("Step 1: Finding documents with root-level is_complaint...")
    
    query = {
        'size': 10000,  # Process in batches
        'query': {
            'exists': {'field': 'is_complaint'}
        },
        '_source': ['is_complaint', 'complaint']
    }
    
    result = client.search(index=index, body=query, scroll='2m')
    scroll_id = result['_scroll_id']
    hits = result['hits']['hits']
    
    total_found = result['hits']['total']['value']
    logger.info(f"Found {total_found:,} documents with root-level is_complaint")
    
    migrated = 0
    errors = 0
    
    while hits:
        logger.info(f"Processing batch of {len(hits)} documents...")
        
        for hit in hits:
            doc_id = hit['_id']
            source = hit['_source']
            
            try:
                # Get is_complaint value from root
                is_complaint = source.get('is_complaint', False)
                
                # Get or create complaint object
                complaint = source.get('complaint', {})
                
                # Add is_complaint to complaint object
                complaint['is_complaint'] = is_complaint
                
                # Update document
                client.update(
                    index=index,
                    id=doc_id,
                    body={
                        'doc': {
                            'complaint': complaint
                        }
                    }
                )
                
                migrated += 1
                
                if migrated % 100 == 0:
                    logger.info(f"Progress: {migrated:,} / {total_found:,} documents migrated")
                
            except Exception as e:
                logger.error(f"Error migrating document {doc_id}: {e}")
                errors += 1
        
        # Get next batch
        result = client.scroll(scroll_id=scroll_id, scroll='2m')
        scroll_id = result['_scroll_id']
        hits = result['hits']['hits']
    
    # Clear scroll
    client.clear_scroll(scroll_id=scroll_id)
    
    # Step 2: Verify migration
    logger.info("\nStep 2: Verifying migration...")
    
    # Count documents with complaint.is_complaint
    nested_count = client.count(
        index=index,
        body={'query': {'exists': {'field': 'complaint.is_complaint'}}}
    )['count']
    
    logger.info(f"Documents with complaint.is_complaint: {nested_count:,}")
    
    # Count complaint=True
    complaints_true = client.count(
        index=index,
        body={'query': {'term': {'complaint.is_complaint': True}}}
    )['count']
    
    logger.info(f"Documents with is_complaint=True: {complaints_true:,}")
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total found: {total_found:,}")
    logger.info(f"Migrated: {migrated:,}")
    logger.info(f"Errors: {errors}")
    logger.info(f"\nAfter migration:")
    logger.info(f"  complaint.is_complaint field: {nested_count:,} documents")
    logger.info(f"  Complaints (True): {complaints_true:,} documents")
    logger.info("=" * 80)
    
    return {
        'total': total_found,
        'migrated': migrated,
        'errors': errors,
        'nested_count': nested_count,
        'complaints_true': complaints_true
    }


if __name__ == '__main__':
    try:
        logger.info("Starting complaint field migration...")
        result = migrate_complaint_field()
        logger.info("\nMigration completed successfully!")
        sys.exit(0)
    except KeyboardInterrupt:
        logger.warning("\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\nMigration failed: {e}", exc_info=True)
        sys.exit(1)
