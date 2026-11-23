"""
Mart Aggregation Job.
Aggregates daily statistics into Mart tables.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import text

from scheduler.utils.database import get_db_session
from app.constants import ReviewAnalysisStatus

logger = logging.getLogger(__name__)


class AggregateMartJob:
    """
    Job for aggregating review statistics into Mart tables.
    """

    def run(self, target_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Run the aggregation job.

        Args:
            target_date: Date to aggregate for (default: now). 
                         Will aggregate for the month of this date.

        Returns:
            Job result summary
        """
        if target_date is None:
            target_date = datetime.now()
        
        year = target_date.year
        month = target_date.month
        
        logger.info(f"Starting Mart aggregation for {year}-{month:02d}")
        
        results = {
            'status': 'success',
            'app_stats_updated': 0,
            'dept_stats_updated': 0,
            'filter_counts_updated': 0,
            'errors': []
        }
        
        try:
            with get_db_session() as session:
                # 1. Aggregate App Stats
                self._aggregate_app_stats(session, year, month, results)
                
                # 2. Aggregate Dept Stats
                self._aggregate_dept_stats(session, year, month, results)
                
                # 3. Aggregate Dept Review Filter Counts
                self._aggregate_dept_review_filter_counts(session, results)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Mart aggregation failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['errors'].append(str(e))
            
        logger.info(f"Mart aggregation completed: {results}")
        return results

    def _aggregate_app_stats(self, session, year, month, results):
        """Aggregate app statistics."""
        query = text(f"""
            SELECT
                package_id as app_id,
                COUNT(*) as total_reviews,
                AVG(score) as avg_rating,
                AVG(sentiment_score) as avg_sentiment_score,
                SUM(CASE WHEN sentiment_label = 'POSITIVE' THEN 1 ELSE 0 END) as positive_count,
                SUM(CASE WHEN sentiment_label = 'NEGATIVE' THEN 1 ELSE 0 END) as negative_count,
                SUM(is_complaint) as complaint_count
            FROM reviews
            WHERE analyzed = {ReviewAnalysisStatus.COMPLETED.value}
              AND YEAR(at) = :year
              AND MONTH(at) = :month
            GROUP BY package_id
        """)
        
        rows = session.execute(query, {'year': year, 'month': month}).fetchall()
        
        upsert_query = text("""
            INSERT INTO mart_app_stats_monthly (
                app_id, year, month, 
                total_reviews, avg_rating, avg_sentiment_score, 
                positive_count, negative_count, complaint_count,
                updated_at
            ) VALUES (
                :app_id, :year, :month,
                :total_reviews, :avg_rating, :avg_sentiment_score,
                :positive_count, :negative_count, :complaint_count,
                NOW()
            )
            ON DUPLICATE KEY UPDATE
                total_reviews = VALUES(total_reviews),
                avg_rating = VALUES(avg_rating),
                avg_sentiment_score = VALUES(avg_sentiment_score),
                positive_count = VALUES(positive_count),
                negative_count = VALUES(negative_count),
                complaint_count = VALUES(complaint_count),
                updated_at = NOW()
        """)
        
        for row in rows:
            params = {
                'app_id': row.app_id,
                'year': year,
                'month': month,
                'total_reviews': row.total_reviews,
                'avg_rating': row.avg_rating or 0,
                'avg_sentiment_score': row.avg_sentiment_score or 0,
                'positive_count': int(row.positive_count or 0),
                'negative_count': int(row.negative_count or 0),
                'complaint_count': int(row.complaint_count or 0)
            }
            session.execute(upsert_query, params)
            results['app_stats_updated'] += 1

    def _aggregate_dept_stats(self, session, year, month, results):
        """Aggregate department statistics."""
        query = text(f"""
            SELECT
                complaint_primary_dept as dept_code,
                COUNT(*) as total_assigned,
                AVG(complaint_urgency) as avg_urgency,
                AVG(complaint_severity) as avg_severity,
                SUM(CASE WHEN complaint_status = 'new' THEN 1 ELSE 0 END) as status_new,
                SUM(CASE WHEN complaint_status = 'in_progress' THEN 1 ELSE 0 END) as status_in_progress,
                SUM(CASE WHEN complaint_status = 'resolved' THEN 1 ELSE 0 END) as status_resolved
            FROM reviews
            WHERE analyzed = {ReviewAnalysisStatus.COMPLETED.value}
              AND is_complaint = 1
              AND YEAR(at) = :year
              AND MONTH(at) = :month
              AND complaint_primary_dept IS NOT NULL
            GROUP BY complaint_primary_dept
        """)
        
        rows = session.execute(query, {'year': year, 'month': month}).fetchall()
        
        upsert_query = text("""
            INSERT INTO mart_dept_stats_monthly (
                dept_code, year, month,
                total_assigned, avg_urgency, avg_severity,
                status_new, status_in_progress, status_resolved,
                updated_at
            ) VALUES (
                :dept_code, :year, :month,
                :total_assigned, :avg_urgency, :avg_severity,
                :status_new, :status_in_progress, :status_resolved,
                NOW()
            )
            ON DUPLICATE KEY UPDATE
                total_assigned = VALUES(total_assigned),
                avg_urgency = VALUES(avg_urgency),
                avg_severity = VALUES(avg_severity),
                status_new = VALUES(status_new),
                status_in_progress = VALUES(status_in_progress),
                status_resolved = VALUES(status_resolved),
                updated_at = NOW()
        """)
        
        for row in rows:
            params = {
                'dept_code': row.dept_code,
                'year': year,
                'month': month,
                'total_assigned': row.total_assigned,
                'avg_urgency': row.avg_urgency or 0,
                'avg_severity': row.avg_severity or 0,
                'status_new': int(row.status_new or 0),
                'status_in_progress': int(row.status_in_progress or 0),
                'status_resolved': int(row.status_resolved or 0)
            }
            session.execute(upsert_query, params)
            results['dept_stats_updated'] += 1

    def _aggregate_dept_review_filter_counts(self, session, results):
        """Aggregate dept review filter counts from OpenSearch."""
        from app.services.review_service import get_review_service
        from datetime import timedelta
        
        logger.info("Aggregating dept review filter counts...")
        
        review_service = get_review_service()
        
        # Clear old data
        session.execute(text("TRUNCATE TABLE mart_dept_review_filter_counts"))
        
        # Define time ranges
        end_date = datetime.utcnow()
        start_date_30d = end_date - timedelta(days=30)
        
        # Query OpenSearch for aggregations
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
                                            "review_date": {
                                                "gte": start_date_30d.isoformat()
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        response = review_service._os.sync_client.search(
            index=review_service._index,
            body=query
        )
        
        # Insert aggregated data
        upsert_query = text("""
            INSERT INTO mart_dept_review_filter_counts
            (app_id, dept_code, review_count, last_30_days_count, last_updated)
            VALUES (:app_id, :dept_code, :review_count, :last_30_days_count, NOW())
            ON DUPLICATE KEY UPDATE
                review_count = VALUES(review_count),
                last_30_days_count = VALUES(last_30_days_count),
                last_updated = NOW()
        """)
        
        count = 0
        for app_bucket in response['aggregations']['apps']['buckets']:
            app_id = app_bucket['key']
            for dept_bucket in app_bucket['depts']['buckets']:
                dept_code = dept_bucket['key']
                total_count = dept_bucket['doc_count']
                last_30d_count = dept_bucket['last_30_days']['doc_count']
                
                session.execute(upsert_query, {
                    'app_id': app_id,
                    'dept_code': dept_code,
                    'review_count': total_count,
                    'last_30_days_count': last_30d_count
                })
                count += 1
        
        results['filter_counts_updated'] = count
        logger.info(f"Aggregated {count} app-dept combinations")


def run_aggregate_mart_job(target_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Wrapper for running the aggregation job.
    """
    job = AggregateMartJob()
    return job.run(target_date)
