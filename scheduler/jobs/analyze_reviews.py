"""
Review Analysis Job.
Sends collected reviews to the main app for analysis.
"""

import asyncio
import logging
import time
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy import text

from scheduler.utils import get_scheduler_config
from scheduler.utils.database import get_db_session
from scheduler.utils.batch_manager import DynamicBatchSizeManager
from app.services.review_service import get_review_service
from app.agents.unified_agent import get_unified_agent
from app.constants import ReviewAnalysisStatus
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class AnalyzeReviewsJob:
    """
    Job for analyzing collected reviews.

    Fetches unanalyzed reviews from OpenSearch and sends them
    to the main Flask app's API for analysis.
    """

    def __init__(
        self,
        db_session_factory=None,
        api_base_url: Optional[str] = None
    ):
        """
        Initialize the job.

        Args:
            db_session_factory: Not used for OpenSearch implementation but kept for interface compatibility
            api_base_url: Base URL for the analysis API
        """
        self._scheduler_config = get_scheduler_config()

        job_config = self._scheduler_config.get_job_config('analyze_reviews') or {}
        settings = job_config.get('settings', {})
        
        # The API endpoint is no longer used as we're calling the agent directly
        # self._api_endpoint = api_base_url or settings.get('api_endpoint', default_endpoint)

        # Dynamic batch sizing with Redis-backed state
        self._redis = get_redis_client()
        self._batch_manager = DynamicBatchSizeManager(self._redis)

        # Keep _batch_size for backward compatibility (used in fetch limit calculation)
        self._batch_size = settings.get('batch_size', 10)
        self._timeout = settings.get('timeout', 60) # Timeout is less relevant for direct agent calls, but kept for consistency

        # Parallel processing control
        import os
        self._max_concurrency = int(os.getenv('ANALYSIS_CONCURRENCY', '5'))  # Default: 5 parallel tasks
        self._semaphore = asyncio.Semaphore(self._max_concurrency)

        # Agent selection based on feature flag
        self._use_two_stage = os.getenv('ENABLE_TWO_STAGE_PIPELINE', 'false').lower() == 'true'
        if self._use_two_stage:
            logger.info("Two-stage pipeline enabled")
            from app.agents.two_stage_agent import get_two_stage_agent
            self._unified_agent = get_two_stage_agent()
        else:
            logger.info("Using unified agent (default)")
            self._unified_agent = get_unified_agent()

    async def run(self, all_batches: bool = False) -> Dict[str, Any]:
        """
        Run the analysis job.

        Args:
            all_batches: If True, process all available unanalyzed reviews

        Returns:
            Job result summary
        """
        start_time = datetime.now()
        logger.info(f"Starting review analysis job (all_batches={all_batches})")

        results = {
            'status': 'completed',
            'reviews_processed': 0,
            'reviews_analyzed': 0,
            'reviews_failed': 0,
            'errors': [],
            'duration_seconds': 0
        }

        while True:
            # Fetch unanalyzed reviews
            unanalyzed_reviews = await self._fetch_unanalyzed_reviews()

            if not unanalyzed_reviews:
                logger.info("No unanalyzed reviews found")
                break

            logger.info(f"Found {len(unanalyzed_reviews)} unanalyzed reviews")

            # Process batches with dynamic batch sizing
            i = 0
            while i < len(unanalyzed_reviews):
                # Get current dynamic batch size
                current_batch_size = self._batch_manager.get_current_batch_size()
                logger.info(f"Processing batch with size={current_batch_size}")

                batch = unanalyzed_reviews[i:i + current_batch_size]
                batch_results = await self._analyze_batch_parallel(batch)

                # Update counters
                results['reviews_processed'] += len(batch)
                results['reviews_analyzed'] += batch_results['success']
                results['reviews_failed'] += batch_results['failed']

                if batch_results['errors']:
                    results['errors'].extend(batch_results['errors'])

                # Record batch result for dynamic sizing
                self._batch_manager.record_batch_result(
                    success_count=batch_results['success'],
                    failure_count=batch_results['failed']
                )

                i += current_batch_size

            if not all_batches:
                break
            
            # If all_batches is True, loop again to check for more
            # Add a small delay to prevent tight loops if something is wrong
            await asyncio.sleep(1)

        end_time = datetime.now()
        results['duration_seconds'] = (end_time - start_time).total_seconds()

        logger.info(
            f"Analysis completed: "
            f"{results['reviews_analyzed']} analyzed, "
            f"{results['reviews_failed']} failed"
        )

        return results

    async def _fetch_unanalyzed_reviews(self) -> List[Dict[str, Any]]:
        """
        Fetch reviews that haven't been analyzed yet from MariaDB.

        Returns:
            List of review dictionaries
        """
        try:
            # Run blocking MariaDB call in thread
            return await asyncio.to_thread(self._fetch_from_mariadb)
        except Exception as e:
            logger.error(f"Failed to fetch unanalyzed reviews: {e}")
            return []

    def _fetch_from_mariadb(self) -> List[Dict[str, Any]]:
        """Fetch unanalyzed reviews from MariaDB."""
        with get_db_session() as session:
            result = session.execute(text(f"""
                SELECT review_id, package_id, content, score, at, created_at
                FROM reviews
                WHERE analyzed = {ReviewAnalysisStatus.PENDING.value}
                AND content IS NOT NULL
                AND content != ''
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": self._batch_size * 5})
            
            rows = []
            for row in result:
                row_dict = dict(row._mapping)
                # Map fields to expected format
                rows.append({
                    'review_id': row_dict['review_id'],
                    'app_id': row_dict['package_id'],
                    'content': row_dict['content'],
                    'original_content': row_dict['content'],
                    'rating': row_dict['score'],
                    'review_date': row_dict['at'],
                    'collected_at': row_dict['created_at']
                })
            
            logger.info(f"Fetched {len(rows)} reviews from MariaDB for analysis")
            return rows

    async def _analyze_batch(self, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Send a batch of reviews for analysis.

        Args:
            reviews: List of review dictionaries

        Returns:
            Batch analysis results
        """
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }

        for review in reviews:
            try:
                # Prepare input data
                input_data = {
                    'content': review.get('content') or review.get('original_content'),
                    'app_name': review.get('app_name'),
                    'rating': review.get('rating'),
                    'review_id': review.get('review_id')
                }
                
                if not input_data['content']:
                    logger.warning(f"Skipping empty review {review.get('review_id')} - marking as analyzed")
                    # Mark empty review as analyzed to prevent infinite loop
                    await self._mark_empty_review_analyzed(review)
                    results['failed'] += 1
                    continue

                # Run unified analysis
                # agent.analyze is async
                unified_response = await self._unified_agent.analyze(input_data)
                
                if not unified_response or not unified_response.result:
                    raise ValueError("Unified analysis failed (empty response)")
                
                # Extract results
                unified_result = unified_response.result
                
                # Format result to match what _save_analysis_result expects
                # Handle both Pydantic v2 (model_dump) and legacy objects (to_dict)
                sentiment_data = unified_result.sentiment.model_dump() if hasattr(unified_result.sentiment, 'model_dump') else unified_result.sentiment.to_dict()
                complaint_data = unified_result.complaint.model_dump() if hasattr(unified_result.complaint, 'model_dump') else unified_result.complaint.to_dict()
                category_data = unified_result.category.model_dump() if hasattr(unified_result.category, 'model_dump') else unified_result.category.to_dict()
                
                reasoning_data = {}
                if unified_response.reasoning:
                    r_data = unified_response.reasoning.model_dump() if hasattr(unified_response.reasoning, 'model_dump') else unified_response.reasoning.to_dict()
                    reasoning_data['unified'] = r_data

                analysis_result = {
                    'sentiment': sentiment_data,
                    'complaint': complaint_data,
                    'category': category_data,
                    'reasoning': reasoning_data
                }
                
                logger.info(f"Analyzed review {review.get('review_id')}: Sentiment={unified_result.sentiment.sentiment_label.value}, Complaint={unified_result.complaint.is_complaint}, Category={unified_result.category.primary_category}")
                
                await self._save_analysis_result(review, analysis_result)
                results['success'] += 1

            except Exception as e:
                error_msg = f"Error analyzing review {review.get('review_id')}: {e}"
                logger.error(error_msg)
                results['failed'] += 1
                results['errors'].append(error_msg)

        return results

    async def _analyze_single_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single review with semaphore control."""
        async with self._semaphore:
            try:
                # Prepare input data
                input_data = {
                    'content': review.get('content') or review.get('original_content'),
                    'app_name': review.get('app_name'),
                    'rating': review.get('rating'),
                    'review_id': review.get('review_id')
                }
                
                if not input_data['content']:
                    logger.warning(f"Skipping empty review {review.get('review_id')} - marking as analyzed")
                    # Mark empty review as analyzed to prevent infinite loop
                    await self._mark_empty_review_analyzed(review)
                    return {'success': False, 'error': 'Empty content'}

                # Run unified analysis
                unified_response = await self._unified_agent.analyze(input_data)
                
                if not unified_response or not unified_response.result:
                    raise ValueError("Unified analysis failed (empty response)")
                
                # Extract and save results
                unified_result = unified_response.result
                
                sentiment_data = unified_result.sentiment.model_dump() if hasattr(unified_result.sentiment, 'model_dump') else unified_result.sentiment.to_dict()
                complaint_data = unified_result.complaint.model_dump() if hasattr(unified_result.complaint, 'model_dump') else unified_result.complaint.to_dict()
                category_data = unified_result.category.model_dump() if hasattr(unified_result.category, 'model_dump') else unified_result.category.to_dict()
                
                reasoning_data = {}
                if unified_response.reasoning:
                    r_data = unified_response.reasoning.model_dump() if hasattr(unified_response.reasoning, 'model_dump') else unified_response.reasoning.to_dict()
                    reasoning_data['unified'] = r_data

                analysis_result = {
                    'sentiment': sentiment_data,
                    'complaint': complaint_data,
                    'category': category_data,
                    'reasoning': reasoning_data
                }
                
                logger.info(f"Analyzed review {review.get('review_id')}: Sentiment={unified_result.sentiment.sentiment_label.value}, Complaint={unified_result.complaint.is_complaint}")
                
                await self._save_analysis_result(review, analysis_result)
                return {'success': True, 'error': None}

            except Exception as e:
                error_msg = str(e)
                review_id = review.get('review_id')

                # Content filter 오류 감지: 분석 완료로 처리
                if 'content_filter' in error_msg or 'ResponsibleAIPolicyViolation' in error_msg:
                    logger.warning(f"Content filtered review {review_id}: {error_msg[:200]}")
                    await self._mark_content_filtered_review(review, error_msg)
                    return {'success': True, 'error': None}  # 성공으로 처리

                # 기타 오류: 기존 동작 유지 (재시도 대상)
                logger.error(f"Error analyzing review {review_id}: {error_msg}")
                return {'success': False, 'error': error_msg}

    async def _analyze_batch_parallel(self, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze batch of reviews in parallel with concurrency control."""
        logger.info(f"Processing batch of {len(reviews)} reviews (max concurrency: {self._max_concurrency})")
        
        # Create tasks for all reviews
        tasks = [self._analyze_single_review(review) for review in reviews]
        
        # Execute in parallel with semaphore control
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        success_count = 0
        failed_count = 0
        errors = []
        
        for result in task_results:
            if isinstance(result, Exception):
                failed_count += 1
                errors.append(str(result))
            elif isinstance(result, dict):
                if result.get('success'):
                    success_count += 1
                else:
                    failed_count += 1
                    if result.get('error'):
                        errors.append(result['error'])
        
        return {
            'success': success_count,
            'failed': failed_count,
            'errors': errors
        }

    async def _save_analysis_result(
        self,
        review: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> None:
        """
        Save analysis result to MariaDB only.
        OpenSearch sync is handled by sync_to_opensearch job.

        Args:
            review: Original review data
            analysis: Analysis result from API
        """
        try:
            # Update MariaDB only (Source of Truth)
            # OpenSearch will be updated by sync_to_opensearch job
            await asyncio.to_thread(self._update_mariadb, review, analysis)
        except Exception as e:
            logger.error(f"Failed to save analysis result: {e}")

    async def _mark_empty_review_analyzed(self, review: Dict[str, Any]) -> None:
        """
        Mark an empty review as analyzed to prevent infinite loop.
        Sets minimal analysis data so it won't be fetched again.
        OpenSearch sync is handled by sync_to_opensearch job.
        """
        try:
            review_id = review.get('review_id')
            logger.info(f"Marking empty review {review_id} as analyzed")
            
            # Update MariaDB only (OpenSearch handled by sync job)
            await asyncio.to_thread(self._mark_empty_in_mariadb, review_id)
            
        except Exception as e:
            logger.error(f"Failed to mark empty review as analyzed: {e}")

    def _mark_empty_in_mariadb(self, review_id: str) -> None:
        """Mark empty review as analyzed in MariaDB."""
        with get_db_session() as session:
            query = text(f"""
                UPDATE reviews SET
                    analyzed = {ReviewAnalysisStatus.COMPLETED.value},
                    sentiment_label = 'unknown',
                    sentiment_score = 0,
                    updated_at = NOW()
                WHERE review_id = :review_id
            """)
            session.execute(query, {'review_id': review_id})
            session.commit()
            logger.info(f"Marked empty review {review_id} as analyzed in MariaDB")

    async def _mark_content_filtered_review(self, review: Dict[str, Any], error_msg: str) -> None:
        """
        콘텐츠 필터로 차단된 리뷰를 분석 완료로 마킹.
        """
        try:
            review_id = review.get('review_id')
            logger.warning(f"Content filtered review {review_id} - marking as analyzed with default values")

            await asyncio.to_thread(self._mark_content_filtered_in_mariadb, review_id, error_msg)

        except Exception as e:
            logger.error(f"Failed to mark content filtered review as analyzed: {e}")

    def _mark_content_filtered_in_mariadb(self, review_id: str, error_msg: str) -> None:
        """MariaDB에 콘텐츠 필터 리뷰 업데이트."""
        with get_db_session() as session:
            query = text(f"""
                UPDATE reviews SET
                    analyzed = {ReviewAnalysisStatus.COMPLETED.value},
                    sentiment_label = 'content_filtered',
                    sentiment_score = 0,
                    sentiment_confidence = 0,
                    category_primary = 'content_filtered',
                    category_confidence = 0,
                    is_complaint = 0,
                    reasoning = :reasoning,
                    updated_at = NOW()
                WHERE review_id = :review_id
            """)
            session.execute(query, {
                'review_id': review_id,
                'reasoning': json.dumps({'error': 'Azure content filter blocked', 'detail': error_msg[:500]}, ensure_ascii=False)
            })
            session.commit()
            logger.info(f"Marked content filtered review {review_id} as analyzed in MariaDB")

    def _mark_empty_in_opensearch(self, review: Dict[str, Any]) -> None:
        """Mark empty review as analyzed in OpenSearch."""
        service = get_review_service()
        doc_id = review.get('review_id')
        
        update_body = {
            "doc": {
                "sentiment": {
                    "sentiment_label": "unknown",
                    "sentiment_score": 0,
                    "confidence": 0
                },
                "category": {
                    "primary_category": "unknown",
                    "confidence": 0
                }
            }
        }
        
        try:
            service._os.sync_client.update(
                index=service._index,
                id=doc_id,
                body=update_body
            )
            logger.info(f"Marked empty review {doc_id} as analyzed in OpenSearch")
        except Exception as e:
            logger.error(f"Failed to update OpenSearch for empty review: {e}")


    def _update_mariadb(self, review: Dict[str, Any], analysis: Dict[str, Any]):
        """Update analysis results in MariaDB."""
        sentiment_data = analysis.get('sentiment') or {}
        complaint_data = analysis.get('complaint') or {}
        category_data = analysis.get('category') or {}
        reasoning_data = analysis.get('reasoning') or {}

        # Prepare reasoning JSON
        reasoning_json = json.dumps(reasoning_data, ensure_ascii=False)

        with get_db_session() as session:
            query = text(f"""
                UPDATE reviews SET
                    analyzed = {ReviewAnalysisStatus.COMPLETED.value},
                    sentiment_label = :sentiment_label,
                    sentiment_score = :sentiment_score,
                    sentiment_emotions = :sentiment_emotions,
                    sentiment_confidence = :sentiment_confidence,

                    category_primary = :category_primary,
                    category_secondary = :category_secondary,
                    category_confidence = :category_confidence,

                    is_complaint = :is_complaint,
                    complaint_type = :complaint_type,
                    complaint_sub_type = :complaint_sub_type,
                    complaint_urgency = :complaint_urgency,
                    complaint_severity = :complaint_severity,
                    complaint_primary_dept = :complaint_primary_dept,
                    complaint_secondary_depts = :complaint_secondary_depts,
                    complaint_escalation_required = :complaint_escalation_required,
                    complaint_escalation_level = :complaint_escalation_level,
                    complaint_escalated_to = :complaint_escalated_to,
                    complaint_status = :complaint_status,
                    complaint_sla_deadline = :complaint_sla_deadline,

                    reasoning = :reasoning,
                    updated_at = NOW()
                WHERE review_id = :review_id
            """)
            
            # Helper to join list
            def join_list(lst):
                return ','.join(lst) if isinstance(lst, list) else str(lst) if lst else None

            # Calculate SLA deadline based on urgency
            def calculate_sla_deadline(urgency_score):
                if not urgency_score or not complaint_data.get('is_complaint'):
                    return None
                from datetime import timedelta
                created_at = review.get('created_at') or review.get('at')
                if not created_at:
                    return None

                # Map urgency score to hours
                urgency_map = {
                    'critical': 4,
                    'high': 24,
                    'medium': 72,
                    'low': 168
                }
                hours = urgency_map.get(urgency_score, 168)
                return created_at + timedelta(hours=hours)

            # Extract primary dept
            primary_dept = complaint_data.get('primary_dept', {}).get('code') if isinstance(complaint_data.get('primary_dept'), dict) else complaint_data.get('primary_dept')

            params = {
                'review_id': review['review_id'],

                # Sentiment
                'sentiment_label': sentiment_data.get('sentiment_label'),
                'sentiment_score': sentiment_data.get('sentiment_score'),
                'sentiment_emotions': join_list(sentiment_data.get('emotions')),
                'sentiment_confidence': sentiment_data.get('confidence'),

                # Category
                'category_primary': category_data.get('primary_category'),
                'category_secondary': join_list(category_data.get('secondary_categories')),
                'category_confidence': category_data.get('confidence'),

                # Complaint
                'is_complaint': 1 if complaint_data.get('is_complaint') else 0,
                'complaint_type': complaint_data.get('complaint_type'),
                'complaint_sub_type': complaint_data.get('complaint_sub_type'),
                'complaint_urgency': complaint_data.get('urgency_score'),
                'complaint_severity': complaint_data.get('severity_score'),
                'complaint_primary_dept': primary_dept,
                'complaint_secondary_depts': ','.join([d.get('code') if isinstance(d, dict) else str(d) for d in complaint_data.get('secondary_depts', [])]) if complaint_data.get('secondary_depts') else None,
                'complaint_escalation_required': 1 if complaint_data.get('escalation_required') else 0,
                'complaint_escalation_level': complaint_data.get('escalation_level'),
                'complaint_escalated_to': primary_dept,  # Initially same as primary_dept
                'complaint_status': 'new' if complaint_data.get('is_complaint') else None,
                'complaint_sla_deadline': calculate_sla_deadline(complaint_data.get('urgency_score')),

                # Reasoning
                'reasoning': reasoning_json
            }
            
            session.execute(query, params)
            session.commit()
            logger.info(f"Updated MariaDB for review {review['review_id']}")

    def _update_opensearch(self, review: Dict[str, Any], analysis: Dict[str, Any]):
        """Internal synchronous update."""
        service = get_review_service()
        
        sentiment_data = analysis.get('sentiment') or {}
        complaint_data = analysis.get('complaint') or {}
        category_data = analysis.get('category') or {}
        reasoning_data = analysis.get('reasoning') or {}
        
        update_body = {
            "doc": {
                "sentiment": {
                    "label": sentiment_data.get('sentiment_label'),
                    "score": sentiment_data.get('sentiment_score'),
                    "emotions": sentiment_data.get('emotions'),
                    "confidence": sentiment_data.get('confidence')
                },
                "complaint": {
                    "is_complaint": complaint_data.get('is_complaint', False),
                    "type": complaint_data.get('complaint_type'),
                    "sub_type": complaint_data.get('complaint_sub_type'),
                    "urgency": complaint_data.get('urgency_score'),
                    "severity": complaint_data.get('severity_score'),
                    "primary_dept": complaint_data.get('primary_dept', {}).get('code') if isinstance(complaint_data.get('primary_dept'), dict) else complaint_data.get('primary_dept'),
                    "secondary_depts": [d.get('code') if isinstance(d, dict) else d for d in complaint_data.get('secondary_depts', [])] if complaint_data.get('secondary_depts') else [],
                    "escalation_required": complaint_data.get('escalation_required', False),
                    "escalation_level": complaint_data.get('escalation_level'),
                    "status": "new"  # Default status for new complaints
                },
                "category": {
                    "primary": category_data.get('primary_category'),
                    "secondary": category_data.get('secondary_categories', []),
                    "confidence": category_data.get('confidence')
                },
                "analysis_metadata": {
                    "reasoning": reasoning_data
                },
                "analyzed": True,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
        
        service._os.sync_client.update(
            index=service._index,
            id=review['review_id'],
            body=update_body
        )


def run_analyze_reviews_job(db_session_factory=None, all_batches: bool = False) -> Dict[str, Any]:
    """
    Synchronous wrapper for running the analysis job.

    Args:
        db_session_factory: Database session factory (unused but kept for signature)
        all_batches: If True, process all available unanalyzed reviews

    Returns:
        Job result summary
    """
    job = AnalyzeReviewsJob(db_session_factory=db_session_factory)
    return asyncio.run(job.run(all_batches=all_batches))
