"""
Google Play Store Review Collector.
Collects app reviews using google-play-scraper library.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import hashlib

from google_play_scraper import app, reviews, Sort, reviews_all

logger = logging.getLogger(__name__)


@dataclass
class ReviewData:
    """Single review data structure."""
    review_id: str
    package_id: str
    user_name: str
    user_image: Optional[str]
    content: str
    score: int
    thumbs_up_count: int
    review_created_version: Optional[str]
    at: datetime
    reply_content: Optional[str]
    replied_at: Optional[datetime]
    app_version: Optional[str]

    # Computed fields
    content_hash: str = field(init=False)

    def __post_init__(self):
        """Compute content hash for deduplication."""
        hash_input = f"{self.package_id}:{self.review_id}:{self.content}"
        self.content_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'review_id': self.review_id,
            'package_id': self.package_id,
            'user_name': self.user_name,
            'user_image': self.user_image,
            'content': self.content,
            'score': self.score,
            'thumbs_up_count': self.thumbs_up_count,
            'review_created_version': self.review_created_version,
            'at': self.at.isoformat() if self.at else None,
            'reply_content': self.reply_content,
            'replied_at': self.replied_at.isoformat() if self.replied_at else None,
            'app_version': self.app_version,
            'content_hash': self.content_hash,
        }

    @classmethod
    def from_scraper_result(cls, data: Dict[str, Any], package_id: str) -> 'ReviewData':
        """Create ReviewData from google-play-scraper result."""
        return cls(
            review_id=data.get('reviewId', ''),
            package_id=package_id,
            user_name=data.get('userName', ''),
            user_image=data.get('userImage'),
            content=data.get('content', ''),
            score=data.get('score', 0),
            thumbs_up_count=data.get('thumbsUpCount', 0),
            review_created_version=data.get('reviewCreatedVersion'),
            at=data.get('at'),
            reply_content=data.get('replyContent'),
            replied_at=data.get('repliedAt'),
            app_version=data.get('appVersion'),
        )


@dataclass
class AppMetadata:
    """App metadata from Play Store."""
    package_id: str
    title: str
    description: str
    summary: str
    installs: str
    min_installs: int
    score: float
    ratings: int
    reviews_count: int
    histogram: Dict[int, int]
    price: float
    free: bool
    currency: str
    developer: str
    developer_id: str
    developer_email: Optional[str]
    developer_website: Optional[str]
    developer_address: Optional[str]
    genre: str
    genre_id: str
    icon: str
    header_image: Optional[str]
    screenshots: List[str]
    video: Optional[str]
    video_image: Optional[str]
    content_rating: str
    ad_supported: bool
    contains_ads: bool
    released: Optional[str]
    updated: Optional[str]
    version: Optional[str]
    recent_changes: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'package_id': self.package_id,
            'title': self.title,
            'description': self.description,
            'summary': self.summary,
            'installs': self.installs,
            'min_installs': self.min_installs,
            'score': self.score,
            'ratings': self.ratings,
            'reviews_count': self.reviews_count,
            'histogram': self.histogram,
            'price': self.price,
            'free': self.free,
            'developer': self.developer,
            'genre': self.genre,
            'version': self.version,
            'updated': self.updated,
        }

    @classmethod
    def from_scraper_result(cls, data: Dict[str, Any], package_id: str) -> 'AppMetadata':
        """Create AppMetadata from google-play-scraper result."""
        return cls(
            package_id=package_id,
            title=data.get('title', ''),
            description=data.get('description', ''),
            summary=data.get('summary', ''),
            installs=data.get('installs', ''),
            min_installs=data.get('minInstalls', 0),
            score=data.get('score', 0.0),
            ratings=data.get('ratings', 0),
            reviews_count=data.get('reviews', 0),
            histogram=data.get('histogram', {}),
            price=data.get('price', 0.0),
            free=data.get('free', True),
            currency=data.get('currency', 'KRW'),
            developer=data.get('developer', ''),
            developer_id=data.get('developerId', ''),
            developer_email=data.get('developerEmail'),
            developer_website=data.get('developerWebsite'),
            developer_address=data.get('developerAddress'),
            genre=data.get('genre', ''),
            genre_id=data.get('genreId', ''),
            icon=data.get('icon', ''),
            header_image=data.get('headerImage'),
            screenshots=data.get('screenshots', []),
            video=data.get('video'),
            video_image=data.get('videoImage'),
            content_rating=data.get('contentRating', ''),
            ad_supported=data.get('adSupported', False),
            contains_ads=data.get('containsAds', False),
            released=data.get('released'),
            updated=data.get('updated'),
            version=data.get('version'),
            recent_changes=data.get('recentChanges'),
        )


class PlayStoreCollector:
    """
    Collects reviews and metadata from Google Play Store.

    Uses google-play-scraper library with rate limiting and retry logic.
    """

    def __init__(
        self,
        max_workers: int = 4,
        rate_limit_per_minute: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize the collector.

        Args:
            max_workers: Maximum concurrent workers for parallel collection
            rate_limit_per_minute: Maximum requests per minute
            max_retries: Maximum retry attempts on failure
            retry_delay: Base delay between retries (exponential backoff)
        """
        self._max_workers = max_workers
        self._rate_limit = rate_limit_per_minute
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._request_times: List[float] = []

    async def _rate_limit_wait(self) -> None:
        """Wait if necessary to respect rate limits."""
        import time
        now = time.time()

        # Remove timestamps older than 1 minute
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self._rate_limit:
            # Wait until oldest request is more than 1 minute old
            sleep_time = 60 - (now - self._request_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)

        self._request_times.append(time.time())

    async def _execute_with_retry(self, func, *args, **kwargs) -> Any:
        """Execute function with retry logic."""
        last_error = None

        for attempt in range(self._max_retries):
            try:
                await self._rate_limit_wait()
                # Run blocking function in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    lambda: func(*args, **kwargs)
                )
                return result

            except Exception as e:
                last_error = e
                delay = self._retry_delay * (2 ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{self._max_retries} failed: {e}. "
                    f"Retrying in {delay}s"
                )
                await asyncio.sleep(delay)

        logger.error(f"All {self._max_retries} attempts failed: {last_error}")
        raise last_error

    async def get_app_info(self, package_id: str, lang: str = 'ko', country: str = 'kr') -> AppMetadata:
        """
        Get app metadata from Play Store.

        Args:
            package_id: App package ID (e.g., 'com.example.bank_a')
            lang: Language code
            country: Country code

        Returns:
            AppMetadata object
        """
        logger.info(f"Fetching app info for {package_id}")

        result = await self._execute_with_retry(
            app,
            package_id,
            lang=lang,
            country=country
        )

        return AppMetadata.from_scraper_result(result, package_id)

    async def get_reviews(
        self,
        package_id: str,
        count: int = 200,
        lang: str = 'ko',
        country: str = 'kr',
        sort: Sort = Sort.NEWEST,
        filter_score: Optional[int] = None
    ) -> Tuple[List[ReviewData], Optional[str]]:
        """
        Get reviews for an app.

        Args:
            package_id: App package ID
            count: Number of reviews to fetch
            lang: Language code
            country: Country code
            sort: Sort order (NEWEST, MOST_RELEVANT)
            filter_score: Filter by score (1-5), None for all

        Returns:
            Tuple of (list of ReviewData, continuation token)
        """
        logger.info(f"Fetching {count} reviews for {package_id}")

        result, continuation_token = await self._execute_with_retry(
            reviews,
            package_id,
            lang=lang,
            country=country,
            sort=sort,
            count=count,
            filter_score_with=filter_score
        )

        review_data_list = [
            ReviewData.from_scraper_result(r, package_id)
            for r in result
        ]

        logger.info(f"Fetched {len(review_data_list)} reviews for {package_id}")
        return review_data_list, continuation_token

    async def get_all_reviews(
        self,
        package_id: str,
        lang: str = 'ko',
        country: str = 'kr',
        sort: Sort = Sort.NEWEST,
        sleep_milliseconds: int = 0
    ) -> List[ReviewData]:
        """
        Get all reviews for an app (use with caution - may be slow).

        Args:
            package_id: App package ID
            lang: Language code
            country: Country code
            sort: Sort order
            sleep_milliseconds: Sleep between requests

        Returns:
            List of all ReviewData
        """
        logger.warning(f"Fetching ALL reviews for {package_id} - this may take a while")

        result = await self._execute_with_retry(
            reviews_all,
            package_id,
            lang=lang,
            country=country,
            sort=sort,
            sleep_milliseconds=sleep_milliseconds
        )

        review_data_list = [
            ReviewData.from_scraper_result(r, package_id)
            for r in result
        ]

        logger.info(f"Fetched all {len(review_data_list)} reviews for {package_id}")
        return review_data_list

    async def collect_multiple_apps(
        self,
        package_ids: List[str],
        count_per_app: int = 200,
        lang: str = 'ko',
        country: str = 'kr'
    ) -> Dict[str, List[ReviewData]]:
        """
        Collect reviews for multiple apps concurrently.

        Args:
            package_ids: List of package IDs
            count_per_app: Reviews per app
            lang: Language code
            country: Country code

        Returns:
            Dictionary mapping package_id to list of reviews
        """
        logger.info(f"Collecting reviews for {len(package_ids)} apps")

        results = {}

        # Process in batches to respect rate limits
        batch_size = min(self._max_workers, len(package_ids))

        for i in range(0, len(package_ids), batch_size):
            batch = package_ids[i:i + batch_size]
            tasks = [
                self.get_reviews(pkg_id, count_per_app, lang, country)
                for pkg_id in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for pkg_id, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to collect reviews for {pkg_id}: {result}")
                    results[pkg_id] = []
                else:
                    reviews_list, _ = result
                    results[pkg_id] = reviews_list

        total_reviews = sum(len(r) for r in results.values())
        logger.info(f"Collected {total_reviews} reviews from {len(package_ids)} apps")

        return results

    def close(self) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=True)


# Singleton instance
_collector: Optional[PlayStoreCollector] = None


def get_play_store_collector(**kwargs) -> PlayStoreCollector:
    """Get singleton PlayStoreCollector instance."""
    global _collector
    if _collector is None:
        _collector = PlayStoreCollector(**kwargs)
    return _collector
