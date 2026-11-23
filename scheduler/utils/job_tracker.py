"""
Job execution tracking and monitoring utilities.
Implements job_runs table management for observability.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager
from sqlalchemy import text

logger = logging.getLogger(__name__)


class JobRunTracker:
    """
    Track job execution in database for monitoring and debugging.
    Uses the job_runs table defined in scripts/scheduler/schema/reviews_table.sql.
    """
    
    def __init__(self, session_factory):
        """
        Initialize job run tracker.
        
        Args:
            session_factory: Callable that returns a SQLAlchemy session
        """
        self._session_factory = session_factory
    
    @contextmanager
    def track_job(
        self,
        job_name: str,
        package_id: Optional[str] = None
    ):
        """
        Context manager to track job execution.
        
        Usage:
            with tracker.track_job('collect_reviews', 'com.example.app') as run_id:
                # Do work
                pass
        
        Args:
            job_name: Name of the job being executed
            package_id: Optional package ID for app-specific jobs
        
        Yields:
            run_id: Unique identifier for this job run
        """
        run_id = str(uuid.uuid4())
        session = self._session_factory()
        
        try:
            # Insert job start record
            start_query = text("""
                INSERT INTO job_runs (
                    job_name, run_id, package_id, status, started_at
                ) VALUES (
                    :job_name, :run_id, :package_id, 'running', NOW()
                )
            """)
            
            session.execute(start_query, {
                'job_name': job_name,
                'run_id': run_id,
                'package_id': package_id
            })
            session.commit()
            
            logger.info(f"Job started: {job_name} (run_id={run_id})")
            
            yield run_id
            
            # Update to completed status
            complete_query = text("""
                UPDATE job_runs
                SET status = 'completed',
                    completed_at = NOW()
                WHERE run_id = :run_id
            """)
            
            session.execute(complete_query, {'run_id': run_id})
            session.commit()
            
            logger.info(f"Job completed: {job_name} (run_id={run_id})")
            
        except Exception as e:
            # Update to failed status
            try:
                fail_query = text("""
                    UPDATE job_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = :error_message
                    WHERE run_id = :run_id
                """)
                
                session.execute(fail_query, {
                    'run_id': run_id,
                    'error_message': str(e)[:1000]  # Truncate long errors
                })
                session.commit()
                
                logger.error(f"Job failed: {job_name} (run_id={run_id}): {e}")
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")
            
            raise
        finally:
            session.close()
    
    def update_stats(
        self,
        run_id: str,
        rows_inserted: int = 0,
        rows_duplicate: int = 0
    ):
        """
        Update job statistics.
        
        Args:
            run_id: Job run identifier
            rows_inserted: Number of rows inserted
            rows_duplicate: Number of duplicate rows skipped
        """
        session = self._session_factory()
        
        try:
            update_query = text("""
                UPDATE job_runs
                SET rows_inserted = :rows_inserted,
                    rows_duplicate = :rows_duplicate
                WHERE run_id = :run_id
            """)
            
            session.execute(update_query, {
                'run_id': run_id,
                'rows_inserted': rows_inserted,
                'rows_duplicate': rows_duplicate
            })
            session.commit()
            
            logger.debug(
                f"Updated job stats (run_id={run_id}): "
                f"{rows_inserted} inserted, {rows_duplicate} duplicates"
            )
        except Exception as e:
            logger.error(f"Failed to update job stats: {e}")
        finally:
            session.close()
    
    def get_recent_runs(
        self,
        job_name: Optional[str] = None,
        limit: int = 10
    ) -> list:
        """
        Get recent job runs.
        
        Args:
            job_name: Filter by job name (None for all jobs)
            limit: Maximum number of runs to return
        
        Returns:
            List of job run records
        """
        session = self._session_factory()
        
        try:
            if job_name:
                query = text("""
                    SELECT job_name, run_id, package_id, status,
                           started_at, completed_at, rows_inserted, rows_duplicate,
                           error_message
                    FROM job_runs
                    WHERE job_name = :job_name
                    ORDER BY started_at DESC
                    LIMIT :limit
                """)
                result = session.execute(query, {
                    'job_name': job_name,
                    'limit': limit
                })
            else:
                query = text("""
                    SELECT job_name, run_id, package_id, status,
                           started_at, completed_at, rows_inserted, rows_duplicate,
                           error_message
                    FROM job_runs
                    ORDER BY started_at DESC
                    LIMIT :limit
                """)
                result = session.execute(query, {'limit': limit})
            
            return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch recent runs: {e}")
            return []
        finally:
            session.close()
