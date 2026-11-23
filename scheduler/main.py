#!/usr/bin/env python3
"""
Main entry point for the Scheduler Service.

This is a separated scheduler that runs independently from the main Flask app.
It handles periodic collection and analysis of Google Play Store reviews.

Usage:
    python -m scheduler.main [--config CONFIG_PATH]
    python scheduler/main.py

Environment Variables:
    SCHEDULER_CONFIG: Path to scheduler_config.yaml
    APPS_CONFIG: Path to apps_config.yaml
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD: Database settings
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD: Redis settings
"""

import argparse
import asyncio
import logging
import logging.config
import signal
import sys
import warnings

# Suppress Google API Core FutureWarning about Python 3.10 support
warnings.filterwarnings("ignore", category=FutureWarning, module="google.api_core._python_version_support")
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.utils import get_scheduler_config, get_app_config_loader, Priority
from scheduler.jobs import (
    run_collect_reviews_job,
    run_analyze_reviews_job,
    run_analyze_reviews_job,
    run_generate_wordcloud_job,
    run_aggregate_mart_job
)
from scheduler.jobs.sync_to_opensearch import run_sync_to_opensearch_job

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Main scheduler service for review collection and analysis.

    Manages APScheduler instance and job registration.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the scheduler service.

        Args:
            config_path: Path to scheduler_config.yaml
        """
        self._config = get_scheduler_config(config_path)
        self._app_config = get_app_config_loader()
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging from config."""
        log_config = self._config.logging
        if log_config:
            try:
                logging.config.dictConfig(log_config)
            except Exception as e:
                # Fall back to basic config
                logging.basicConfig(
                    level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                logger.warning(f"Failed to configure logging from config: {e}")

    def _create_scheduler(self) -> AsyncIOScheduler:
        """Create and configure APScheduler instance."""
        scheduler_config = self._config.scheduler

        # Job stores
        jobstores = {
            'default': MemoryJobStore()
        }

        # Executors
        executor_config = scheduler_config.get('executor', {})
        executors = {
            'default': ThreadPoolExecutor(
                max_workers=executor_config.get('max_workers', 10)
            ),
            'processpool': ProcessPoolExecutor(
                max_workers=scheduler_config.get('max_workers', 4)
            )
        }

        # Job defaults
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 60 * 60  # 1 hour
        }

        return AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=scheduler_config.get('timezone', 'Asia/Seoul')
        )

    def _register_jobs(self):
        """Register all scheduled jobs."""
        jobs_config = self._config.jobs

        # 1. Review Collection Jobs (per priority)
        if self._config.is_job_enabled('collect_reviews'):
            collect_config = jobs_config.get('collect_reviews', {})
            schedule_config = collect_config.get('schedule', {})

            # High priority apps - every 4 hours
            high_schedule = schedule_config.get('high_priority', {})
            if high_schedule.get('trigger') == 'interval':
                self._scheduler.add_job(
                    run_collect_reviews_job,
                    IntervalTrigger(hours=high_schedule.get('hours', 4)),
                    id='collect_reviews_high',
                    name='Collect Reviews (High Priority)',
                    kwargs={
                        'priority': 'high'
                    }
                )

            # Medium priority apps - every 8 hours
            medium_schedule = schedule_config.get('medium_priority', {})
            if medium_schedule.get('trigger') == 'interval':
                self._scheduler.add_job(
                    run_collect_reviews_job,
                    IntervalTrigger(hours=medium_schedule.get('hours', 8)),
                    id='collect_reviews_medium',
                    name='Collect Reviews (Medium Priority)',
                    kwargs={
                        'priority': 'medium'
                    }
                )

            # Low priority apps - daily at 2 AM
            low_schedule = schedule_config.get('low_priority', {})
            if low_schedule.get('trigger') == 'cron':
                self._scheduler.add_job(
                    run_collect_reviews_job,
                    CronTrigger(
                        hour=low_schedule.get('hour', 2),
                        minute=low_schedule.get('minute', 0)
                    ),
                    id='collect_reviews_low',
                    name='Collect Reviews (Low Priority)',
                    kwargs={
                        'priority': 'low'
                    }
                )

            logger.info("Registered review collection jobs")

        # 2. Review Analysis Job
        if self._config.is_job_enabled('analyze_reviews'):
            analyze_config = jobs_config.get('analyze_reviews', {})
            schedule_config = analyze_config.get('schedule', {})

            if schedule_config.get('trigger') == 'interval':
                self._scheduler.add_job(
                    run_analyze_reviews_job,
                    IntervalTrigger(hours=schedule_config.get('hours', 1)),
                    id='analyze_reviews',
                    name='Analyze Reviews'
                )
                logger.info("Registered review analysis job")

        # 3. Word Cloud Generation Job
        if self._config.is_job_enabled('generate_wordcloud'):
            wordcloud_config = jobs_config.get('generate_wordcloud', {})
            schedule_config = wordcloud_config.get('schedule', {})
            settings = wordcloud_config.get('settings', {})

            if schedule_config.get('trigger') == 'cron':
                self._scheduler.add_job(
                    run_generate_wordcloud_job,
                    CronTrigger(
                        hour=schedule_config.get('hour', 3),
                        minute=schedule_config.get('minute', 0)
                    ),
                    id='generate_wordcloud',
                    name='Generate Word Clouds',
                    kwargs={
                        'output_dir': settings.get('output_dir')
                    }
                )
                logger.info("Registered word cloud generation job")

        # 4. Sync to OpenSearch Job
        if self._config.is_job_enabled('sync_to_opensearch'):
            sync_config = jobs_config.get('sync_to_opensearch', {})
            schedule_config = sync_config.get('schedule', {})
            
            if schedule_config.get('trigger') == 'interval':
                self._scheduler.add_job(
                    run_sync_to_opensearch_job,
                    IntervalTrigger(minutes=schedule_config.get('minutes', 5)),
                    id='sync_to_opensearch',
                    name='Sync to OpenSearch'
                )
                logger.info("Registered sync to OpenSearch job")

        # 5. Mart Aggregation Job
        if self._config.is_job_enabled('aggregate_mart'):
            mart_config = jobs_config.get('aggregate_mart', {})
            schedule_config = mart_config.get('schedule', {})
            
            if schedule_config.get('trigger') == 'cron':
                self._scheduler.add_job(
                    run_aggregate_mart_job,
                    CronTrigger(
                        hour=schedule_config.get('hour', 4),
                        minute=schedule_config.get('minute', 0)
                    ),
                    id='aggregate_mart',
                    name='Aggregate Mart Stats'
                )
                logger.info("Registered Mart aggregation job")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _sync_app_config(self):
        """Sync app config from YAML to database on startup."""
        try:
            from scheduler.utils.config_sync import sync_legacy_ids_to_db
            synced = sync_legacy_ids_to_db()
            logger.info(f"App config synced: {synced} apps with legacy IDs updated")
        except Exception as e:
            # Don't fail startup, just warn
            logger.warning(f"Failed to sync app config from YAML to DB: {e}")

    def start(self):
        """Start the scheduler service."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting scheduler service...")

        # Sync app config from YAML to database (single source of truth)
        self._sync_app_config()

        # Create scheduler
        self._scheduler = self._create_scheduler()

        # Register jobs
        self._register_jobs()

        # Setup signal handlers
        self._setup_signal_handlers()

        # Start scheduler
        self._scheduler.start()
        self._running = True

        # Log registered jobs
        jobs = self._scheduler.get_jobs()
        logger.info(f"Scheduler started with {len(jobs)} jobs:")
        for job in jobs:
            logger.info(f"  - {job.name} ({job.id}): next run at {job.next_run_time}")

    def stop(self):
        """Stop the scheduler service."""
        if not self._running:
            return

        logger.info("Stopping scheduler service...")

        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None

        self._running = False
        logger.info("Scheduler service stopped")

    async def run_forever(self):
        """Run the scheduler until stopped."""
        self.start()

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            self.stop()

    def run_job_now(self, job_id: str):
        """
        Run a specific job immediately.

        Args:
            job_id: Job ID to run
        """
        if not self._scheduler:
            logger.error("Scheduler is not running")
            return

        job = self._scheduler.get_job(job_id)
        if job:
            logger.info(f"Running job {job_id} immediately")
            job.modify(next_run_time=datetime.now())
        else:
            logger.error(f"Job not found: {job_id}")

    def get_job_status(self) -> dict:
        """
        Get status of all registered jobs.

        Returns:
            Dictionary with job status information
        """
        if not self._scheduler:
            return {'running': False, 'jobs': []}

        jobs = self._scheduler.get_jobs()
        return {
            'running': self._running,
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                    'pending': job.pending
                }
                for job in jobs
            ]
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Korean Financial App Review Scheduler'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to scheduler_config.yaml'
    )
    parser.add_argument(
        '--run-once',
        help='Run a specific job once and exit (collect, collect_high, collect_medium, collect_low, analyze, wordcloud, sync)'
    )
    parser.add_argument(
        '--list-apps',
        action='store_true',
        help='List configured apps and exit'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate configuration and exit'
    )

    parser.add_argument(
        '--run-pipeline',
        action='store_true',
        help='Run full pipeline (Collect High -> Sync -> Analyze -> Wordcloud)'
    )

    parser.add_argument(
        '--fetch-all',
        action='store_true',
        help='Fetch ALL historical reviews (ignores limit)'
    )

    args = parser.parse_args()

    # Configure basic logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Handle list-apps
    if args.list_apps:
        app_config = get_app_config_loader()
        print(f"\nConfigured Apps ({app_config.get_app_count()} total):")
        print(f"Config version: {app_config.get_config_version()}\n")

        counts = app_config.get_app_count_by_priority()
        print(f"By priority: High={counts['high']}, Medium={counts['medium']}, Low={counts['low']}\n")

        for category in app_config.get_categories():
            print(f"\n{category.display_name} ({len(category.apps)} apps):")
            for app in category.apps:
                print(f"  - {app.name} ({app.package_id}) [{app.priority.value}]")

        return

    # Handle validate
    if args.validate:
        try:
            scheduler_config = get_scheduler_config(args.config)
            app_config = get_app_config_loader()

            print("Configuration validation:")
            print(f"  Scheduler config: OK")
            print(f"  Apps configured: {app_config.get_app_count()}")
            print(f"  Jobs enabled:")

            for job_name in ['collect_reviews', 'analyze_reviews', 'generate_wordcloud']:
                enabled = scheduler_config.is_job_enabled(job_name)
                print(f"    - {job_name}: {'enabled' if enabled else 'disabled'}")

            print("\nConfiguration is valid!")
            return

        except Exception as e:
            print(f"Configuration validation failed: {e}")
            sys.exit(1)

    # Handle run-once
    if args.run_once:
        job_name = args.run_once
        print(f"Running job: {job_name}")
        
        result = None
        if job_name == 'collect':
            # Collect all priorities
            result = run_collect_reviews_job(priority=None, fetch_all=args.fetch_all)
        elif job_name == 'collect_high':
            result = run_collect_reviews_job(priority=Priority.HIGH, fetch_all=args.fetch_all)
        elif job_name == 'collect_medium':
            result = run_collect_reviews_job(priority=Priority.MEDIUM, fetch_all=args.fetch_all)
        elif job_name == 'collect_low':
            result = run_collect_reviews_job(priority=Priority.LOW, fetch_all=args.fetch_all)
        elif job_name == 'analyze':
            result = run_analyze_reviews_job(all_batches=args.fetch_all)
        elif job_name == 'wordcloud':
            result = run_generate_wordcloud_job()
        elif job_name == 'sync' or job_name == 'sync_to_opensearch':
            result = asyncio.run(run_sync_to_opensearch_job(all_batches=args.fetch_all))
        elif job_name == 'aggregate_mart':
            result = run_aggregate_mart_job()
        else:
            print(f"Error: Invalid job name '{job_name}'")
            print("Available jobs: collect, collect_high, collect_medium, collect_low, analyze, wordcloud, sync, aggregate_mart")
            sys.exit(1)

        print(f"Result: {result}")
        return

    # Handle run-pipeline
    if args.run_pipeline:
        print("Starting Full Pipeline Execution...")
        
        # 1. Collect Reviews (All Priorities)
        print("\n[1/4] Running Collection (All Priorities)...")
        res = run_collect_reviews_job(priority=None, fetch_all=args.fetch_all)
        print(f"Result: {res}")
        
        # 2. Analyze Reviews
        print("\n[2/4] Analyzing Reviews...")
        res = run_analyze_reviews_job()
        print(f"Result: {res}")

        # 3. Sync to OpenSearch
        print("\n[3/4] Syncing to OpenSearch...")
        res = asyncio.run(run_sync_to_opensearch_job())
        print(f"Result: {res}")
        
        # 4. Generate Word Cloud
        print("\n[4/4] Generating Word Clouds...")
        res = run_generate_wordcloud_job()
        print(f"Result: {res}")
        
        print("\nPipeline Completed!")
        return

    # Start scheduler service
    service = SchedulerService(config_path=args.config)

    try:
        asyncio.run(service.run_forever())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
