"""Async wrapper functions for scheduler jobs."""

async def run_collect_reviews_job_async(priority=None, db_session_factory=None, init_mode=False):
    """Async wrapper for collect reviews job."""
    from scheduler.jobs.collect_reviews import async_run_collect_reviews_job
    return await async_run_collect_reviews_job(priority, db_session_factory, init_mode)


async def run_analyze_reviews_job_async(db_session_factory=None):
    """Async wrapper for analyze reviews job."""
    from scheduler.jobs.analyze_reviews import async_run_analyze_reviews_job
    return await async_run_analyze_reviews_job(db_session_factory)


async def run_generate_wordcloud_job_async(db_session_factory=None, output_dir='./app/static/wc'):
    """Async wrapper for wordcloud generation job."""
    from scheduler.jobs.generate_wordcloud import async_run_generate_wordcloud_job
    return await async_run_generate_wordcloud_job(db_session_factory, output_dir)


async def run_sync_to_opensearch_job_async(db_session_factory=None):
    """Async wrapper for opensearch sync job."""
    from scheduler.jobs.sync_to_opensearch import async_run_sync_to_opensearch_job
    return await async_run_sync_to_opensearch_job(db_session_factory)
