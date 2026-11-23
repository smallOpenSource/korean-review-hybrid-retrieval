import logging
import asyncio
from typing import Dict, Any, List
from scheduler.utils.database import get_db_session
from sqlalchemy import text
from app.services.review_service import get_review_service, ReviewDocument
from app.services.app_service import get_app_service
from datetime import datetime
from app.constants import ReviewAnalysisStatus, ReviewSyncStatus

logger = logging.getLogger(__name__)

async def run_sync_to_opensearch_job(all_batches: bool = False) -> Dict[str, Any]:
    """
    Sync reviews from MySQL to OpenSearch.
    
    Args:
        all_batches: If True, sync all pending reviews
        
    Returns:
        Job result summary
    """
    start_time = datetime.utcnow()
    result = {
        'status': 'success',
        'synced_count': 0,
        'errors': 0,
        'start_time': start_time.isoformat()
    }
    
    try:
        review_service = get_review_service()
        app_service = get_app_service()
        
        # Cache app metadata
        app_map = {}
        try:
            all_apps = app_service.get_all_apps()
            for app in all_apps:
                app_map[app['package_id']] = app
            logger.info(f"Cached metadata for {len(app_map)} apps")
        except Exception as e:
            logger.error(f"Failed to cache app metadata: {e}")
        
        while True:
            # 1. Fetch unsynced reviews
            reviews_to_sync = []
            
            with get_db_session() as session:
                # Using raw SQL to fetch dict-like rows
                # Include analysis fields to prevent data loss during sync
                result_proxy = session.execute(text(f"""
                    SELECT
                        review_id, package_id, content, score, at,
                        created_at, content_hash,
                        -- Analysis fields
                        sentiment_label, sentiment_score, sentiment_emotions, sentiment_confidence,
                        category_primary, category_secondary, category_confidence,
                        is_complaint, complaint_type, complaint_sub_type,
                        complaint_urgency, complaint_severity, complaint_primary_dept,
                        complaint_secondary_depts, complaint_escalation_required,
                        complaint_escalation_level, complaint_status,
                        complaint_sla_deadline, complaint_assigned_to, complaint_escalated_to
                    FROM reviews
                    WHERE synced_to_opensearch = {ReviewSyncStatus.NOT_SYNCED.value}
                    AND analyzed = {ReviewAnalysisStatus.COMPLETED.value}
                    ORDER BY at DESC
                    LIMIT 100
                """))
                
                # Convert to list of dicts
                rows = [dict(row._mapping) for row in result_proxy]
                
                if not rows:
                    logger.info("No reviews to sync")
                    break
                
                logger.info(f"Found {len(rows)} reviews to sync")
                
                for row in rows:
                    # Get app metadata
                    app_info = app_map.get(row['package_id'], {})
                    if not app_info:
                        logger.warning(f"Metadata not found for package_id: {row['package_id']}")
                    
                    # Build sentiment dict if data exists
                    sentiment_data = None
                    if row.get('sentiment_label'):
                        sentiment_data = {
                            'label': row['sentiment_label'],
                            'score': row.get('sentiment_score'),
                            'emotions': row.get('sentiment_emotions', '').split(',') if row.get('sentiment_emotions') else [],
                            'confidence': row.get('sentiment_confidence')
                        }
                    
                    # Build category dict if data exists
                    category_data = None
                    if row.get('category_primary'):
                        category_data = {
                            'primary': row['category_primary'],
                            'secondary': row.get('category_secondary', '').split(',') if row.get('category_secondary') else [],
                            'confidence': row.get('category_confidence')
                        }
                    
                    # Build complaint dict if data exists
                    complaint_data = None
                    if row.get('is_complaint') is not None:
                        complaint_data = {
                            'is_complaint': bool(row['is_complaint']),
                            'type': row.get('complaint_type'),
                            'sub_type': row.get('complaint_sub_type'),
                            'urgency': row.get('complaint_urgency'),
                            'severity': row.get('complaint_severity'),
                            'primary_dept': row.get('complaint_primary_dept'),
                            'secondary_depts': row.get('complaint_secondary_depts', '').split(',') if row.get('complaint_secondary_depts') else [],
                            'escalation_required': bool(row.get('complaint_escalation_required')),
                            'escalation_level': row.get('complaint_escalation_level'),
                            'escalated_to': row.get('complaint_escalated_to'),
                            'status': row.get('complaint_status'),
                            'sla_deadline': row.get('complaint_sla_deadline').isoformat() if row.get('complaint_sla_deadline') else None,
                            'assigned_to': row.get('complaint_assigned_to')
                        }
                    
                    # Convert to ReviewDocument with analysis data
                    doc = ReviewDocument(
                        review_id=row['review_id'],
                        app_id=row['package_id'],
                        app_name=app_info.get('company_name', row['package_id']),
                        company_code=app_info.get('company_code', 'UNKNOWN'),
                        platform='google_play',
                        original_content=row['content'] or '',
                        cleansed_content=row['content'] or '',
                        rating=int(row['score']) if row['score'] is not None else 0,
                        review_date=row['at'],
                        collected_at=row['created_at'],
                        # Include analysis data
                        sentiment=sentiment_data,
                        category=category_data,
                        complaint=complaint_data
                    )
                    reviews_to_sync.append(doc)
    
            # 2. Index to OpenSearch
            if reviews_to_sync:
                # index_reviews_bulk is synchronous
                success_count, failure_count = review_service.index_reviews_bulk(reviews_to_sync)
                result['synced_count'] += success_count
                result['errors'] += failure_count
                
                # 3. Update MySQL status for successful ones
                if success_count > 0:
                    with get_db_session() as session:
                        review_ids = [doc.review_id for doc in reviews_to_sync]

                        # Chunking for safety if list is large (though limit is 100)
                        session.execute(
                            text(f"UPDATE reviews SET synced_to_opensearch = {ReviewSyncStatus.SYNCED.value}, synced_at = NOW() WHERE review_id IN :review_ids"),
                            {"review_ids": review_ids}
                        )
                        session.commit()
                        
                logger.info(f"Synced {success_count} reviews to OpenSearch (Failed: {failure_count})")
            
            if not all_batches:
                break
                
            # Small delay to prevent tight loops
            await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f"Sync job failed: {e}", exc_info=True)
        result['status'] = 'failed'
        result['error_message'] = str(e)
        
    result['end_time'] = datetime.utcnow().isoformat()
    return result
