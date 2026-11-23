"""
Review Collection Job.
Periodically collects reviews from Google Play Store for configured apps.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from scheduler.collectors import PlayStoreCollector, ReviewData, get_play_store_collector
from scheduler.utils import (
    AppConfigLoader,
    AppInfo,
    Priority,
    get_app_config_loader,
    get_scheduler_config
)
from scheduler.utils.database import get_db_session
from sqlalchemy import text
import hashlib

logger = logging.getLogger(__name__)


class CollectReviewsJob:
    """
    Job for collecting reviews from Google Play Store.

    Collects reviews based on app priority:
    - High priority: Every 4 hours
    - Medium priority: Every 8 hours
    - Low priority: Daily
    """

    def __init__(
        self,
        collector: Optional[PlayStoreCollector] = None,
        app_config: Optional[AppConfigLoader] = None
    ):
        """
        Initialize the job.

        Args:
            db_session_factory: SQLAlchemy session factory for database operations
            collector: PlayStoreCollector instance
            app_config: AppConfigLoader instance
        """
        self._collector = collector or get_play_store_collector()
        self._app_config = app_config or get_app_config_loader()
        self._scheduler_config = get_scheduler_config()

    async def run(self, priority: Optional[Priority] = None, fetch_all: bool = False) -> Dict[str, Any]:
        """
        Run the review collection job.

        Args:
            priority: If specified, only collect for apps with this priority.
                     If None, collect for all apps.
            fetch_all: If True, fetch all historical reviews regardless of limits.

        Returns:
            Job result summary
        """
        start_time = datetime.now()
        logger.info(f"Starting review collection job (priority={priority})")

        # Get apps to collect
        if priority:
            apps = self._app_config.get_apps_by_priority(priority)
        else:
            apps = self._app_config.get_all_apps()

        if not apps:
            logger.warning("No apps found for collection")
            return {
                'status': 'completed',
                'apps_processed': 0,
                'reviews_collected': 0,
                'duration_seconds': 0
            }

        logger.info(f"Collecting reviews for {len(apps)} apps")

        results = {
            'status': 'completed',
            'apps_processed': 0,
            'reviews_collected': 0,
            'reviews_new': 0,
            'reviews_duplicate': 0,
            'errors': [],
            'app_results': {}
        }

        # Collect reviews for each app
        for app_info in apps:
            try:
                app_result = await self._collect_app_reviews(app_info, fetch_all=fetch_all)
                results['app_results'][app_info.package_id] = app_result
                results['apps_processed'] += 1
                results['reviews_collected'] += app_result['total']
                results['reviews_new'] += app_result['new']
                results['reviews_duplicate'] += app_result['duplicate']

            except Exception as e:
                error_msg = f"Failed to collect reviews for {app_info.package_id}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        end_time = datetime.now()
        results['duration_seconds'] = (end_time - start_time).total_seconds()

        logger.info(
            f"Review collection completed: "
            f"{results['apps_processed']} apps, "
            f"{results['reviews_collected']} reviews collected, "
            f"{results['reviews_new']} new, "
            f"{len(results['errors'])} errors"
        )

        return results

    async def _collect_app_reviews(self, app_info: AppInfo, fetch_all: bool = False) -> Dict[str, Any]:
        """
        Collect reviews for a single app.

        Args:
            app_info: App information
            fetch_all: Whether to fetch all historical reviews

        Returns:
            Collection result for this app
        """
        logger.debug(f"Collecting reviews for {app_info.name} ({app_info.package_id})")

        result = {
            'package_id': app_info.package_id,
            'app_name': app_info.name,
            'total': 0,
            'new': 0,
            'duplicate': 0,
            'legacy_results': {},
            'error': None
        }

        # Get job settings
        job_config = self._scheduler_config.get_job_config('collect_reviews') or {}
        settings = job_config.get('settings', {})
        reviews_count = settings.get('reviews_per_app', app_info.review_fetch_count)
        languages = settings.get('languages', app_info.review_languages)


        all_reviews: List[ReviewData] = []

        # When fetching ALL reviews, only use Korean to avoid massive duplicate calls
        # (English reviews are typically duplicates of Korean reviews in Korean apps)
        if fetch_all:
            # Override languages for fetch-all mode
            fetch_languages = ['ko']
            logger.info(f"Fetching ALL historical reviews for {app_info.package_id} (Korean only)")
        else:
            fetch_languages = languages

        # Build list of package IDs to collect (current + legacy)
        package_ids_to_collect = [app_info.package_id]
        if app_info.legacy_ids:
            package_ids_to_collect.extend(app_info.legacy_ids)
            logger.info(f"Will collect from {len(package_ids_to_collect)} package IDs "
                       f"(1 current + {len(app_info.legacy_ids)} legacy) for {app_info.name}")

        # Collect reviews for each package ID
        for pkg_id in package_ids_to_collect:
            pkg_reviews: List[ReviewData] = []
            is_legacy = pkg_id != app_info.package_id
            
            # Collect reviews for each language
            for lang in fetch_languages:
                try:
                    if fetch_all:
                        reviews_data = await self._collector.get_all_reviews(
                            package_id=pkg_id,
                            lang=lang,
                            country='kr'
                        )
                    else:
                        reviews_data, _ = await self._collector.get_reviews(
                            package_id=pkg_id,
                            count=reviews_count,
                            lang=lang,
                            country='kr'
                        )
                    
                    pkg_reviews.extend(reviews_data)

                except Exception as e:
                    # Legacy IDs may no longer exist on Play Store - just log and continue
                    if is_legacy:
                        logger.debug(f"Legacy ID {pkg_id} not found or failed: {e}")
                    else:
                        logger.warning(f"Failed to collect {lang} reviews for {pkg_id}: {e}")

            if is_legacy and pkg_reviews:
                result['legacy_results'][pkg_id] = len(pkg_reviews)
                logger.info(f"Collected {len(pkg_reviews)} reviews from legacy ID: {pkg_id}")
            
            all_reviews.extend(pkg_reviews)


        result['total'] = len(all_reviews)

        # Save to database
        if all_reviews:
            new_count, dup_count = await self._save_reviews(all_reviews, app_info)
            result['new'] = new_count
            result['duplicate'] = dup_count
        else:
            result['new'] = 0

        logger.debug(f"Collected {result['total']} reviews for {app_info.name}")
        return result

    async def _save_reviews(
        self,
        reviews: List[ReviewData],
        app_info: AppInfo
    ) -> tuple:
        """
        Save reviews to database.

        Args:
            reviews: List of ReviewData to save
            app_info: App information

        Returns:
            Tuple of (new_count, duplicate_count)
        """
        new_count = 0
        dup_count = 0

        new_count = 0
        dup_count = 0

        try:
            with get_db_session() as session:
                for review in reviews:
                    # Compute hash
                    content_str = review.content if review.content else ""
                    content_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()
                    
                    # Check duplicate
                    # Using raw SQL for performance and simplicity matching previous logic
                    result = session.execute(
                        text("SELECT id FROM reviews WHERE review_id = :review_id OR content_hash = :content_hash"),
                        {"review_id": review.review_id, "content_hash": content_hash}
                    )
                    if result.fetchone():
                        dup_count += 1
                        continue
                        
                    # Insert
                    # Schema: review_id, package_id, content, score, at, content_hash
                    session.execute(
                        text("""
                        INSERT INTO reviews (
                            review_id, package_id, content, score, at, 
                            content_hash, created_at, analyzed, synced_to_opensearch
                        ) VALUES (
                            :review_id, :package_id, :content, :score, :at, 
                            :content_hash, NOW(), 0, 0
                        )
                        """),
                        {
                            "review_id": review.review_id,
                            "package_id": app_info.package_id,
                            "content": review.content if review.content is not None else "",
                            "score": review.score,
                            "at": review.at,
                            "content_hash": content_hash
                        }
                    )
                    new_count += 1
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Failed to save reviews: {e}")
            # Don't raise, just log error and return what we have
            
        return new_count, dup_count

    async def run_for_priority(self, priority: Priority) -> Dict[str, Any]:
        """
        Run collection for a specific priority level.

        Args:
            priority: Priority level to collect

        Returns:
            Job result summary
        """
        return await self.run(priority=priority)


def run_collect_reviews_job(priority: Optional[str] = None, fetch_all: bool = False) -> Dict[str, Any]:
    """
    Synchronous wrapper for running the collect reviews job.

    Args:
        priority: Priority level ('high', 'medium', 'low') or None for all
        fetch_all: Whether to fetch all historical reviews

    Returns:
        Job result summary
    """
    job = CollectReviewsJob()

    priority_enum = None
    if priority:
        try:
            priority_enum = Priority(priority)
        except ValueError:
            logger.warning(f"Invalid priority '{priority}', collecting all")

    return asyncio.run(job.run(priority=priority_enum, fetch_all=fetch_all))
