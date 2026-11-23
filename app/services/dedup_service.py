"""
Deduplication Service.
Detects and manages duplicate reviews using content hash and similarity.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

from app.core.opensearch_client import OpenSearchClient, get_opensearch_client
from app.core.redis_client import RedisClient, get_redis_client

logger = logging.getLogger(__name__)

# Redis key prefixes
HASH_KEY_PREFIX = "review:hash:"
SEEN_HASHES_SET = "review:seen_hashes"


@dataclass
class DedupResult:
    """Result of deduplication check."""
    is_duplicate: bool
    duplicate_of: Optional[str]  # Original review ID if duplicate
    similarity_score: Optional[float]
    method: str  # "exact_hash", "near_duplicate", "unique"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'is_duplicate': self.is_duplicate,
            'duplicate_of': self.duplicate_of,
            'similarity_score': self.similarity_score,
            'method': self.method
        }


class DedupService:
    """
    Service for detecting duplicate reviews.

    Uses two-tier approach:
    1. Exact hash matching for identical content
    2. Near-duplicate detection using similarity threshold
    """

    # Similarity threshold for near-duplicate detection
    SIMILARITY_THRESHOLD = 0.95

    def __init__(
        self,
        os_client: Optional[OpenSearchClient] = None,
        redis_client: Optional[RedisClient] = None
    ):
        self._os = os_client or get_opensearch_client()
        self._redis = redis_client or get_redis_client()
        self._index = "app_reviews"

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA256 hash of content."""
        normalized = content.strip().lower()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    async def check_duplicate(
        self,
        content: str,
        app_id: str,
        check_near_duplicate: bool = True
    ) -> DedupResult:
        """
        Check if content is a duplicate.

        Args:
            content: Review content to check
            app_id: App ID to scope the check
            check_near_duplicate: Whether to check for near-duplicates

        Returns:
            DedupResult with duplicate information
        """
        content_hash = self.compute_hash(content)

        # 1. Check exact hash match in Redis (fast path)
        existing_id = await self._check_hash_redis(content_hash, app_id)
        if existing_id:
            return DedupResult(
                is_duplicate=True,
                duplicate_of=existing_id,
                similarity_score=1.0,
                method="exact_hash"
            )

        # 2. Check exact hash match in OpenSearch (for persistence)
        existing_id = await self._check_hash_opensearch(content_hash, app_id)
        if existing_id:
            # Cache in Redis for future fast lookups
            await self._store_hash_redis(content_hash, app_id, existing_id)
            return DedupResult(
                is_duplicate=True,
                duplicate_of=existing_id,
                similarity_score=1.0,
                method="exact_hash"
            )

        # 3. Check near-duplicate if enabled
        if check_near_duplicate:
            near_dup = await self._check_near_duplicate(content, app_id)
            if near_dup:
                return near_dup

        return DedupResult(
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
            method="unique"
        )

    async def _check_hash_redis(
        self,
        content_hash: str,
        app_id: str
    ) -> Optional[str]:
        """Check for exact hash match in Redis."""
        key = f"{HASH_KEY_PREFIX}{app_id}:{content_hash}"
        try:
            result = self._redis.master.get(key)
            return result.decode('utf-8') if result else None
        except Exception as e:
            logger.warning(f"Redis hash check failed: {e}")
            return None

    async def _store_hash_redis(
        self,
        content_hash: str,
        app_id: str,
        review_id: str,
        ttl_days: int = 90
    ) -> bool:
        """Store hash in Redis for fast lookup."""
        key = f"{HASH_KEY_PREFIX}{app_id}:{content_hash}"
        try:
            self._redis.master.setex(
                key,
                ttl_days * 24 * 60 * 60,
                review_id
            )
            return True
        except Exception as e:
            logger.warning(f"Redis hash store failed: {e}")
            return False

    async def _check_hash_opensearch(
        self,
        content_hash: str,
        app_id: str
    ) -> Optional[str]:
        """Check for exact hash match in OpenSearch."""
        query = {
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"content_hash": content_hash}},
                        {"term": {"app_id": app_id}},
                        {"term": {"is_duplicate": False}}
                    ]
                }
            },
            "_source": ["review_id"]
        }

        try:
            response = self._os.client.search(index=self._index, body=query)
            hits = response['hits']['hits']
            if hits:
                return hits[0]['_source']['review_id']
            return None
        except Exception as e:
            logger.warning(f"OpenSearch hash check failed: {e}")
            return None

    async def _check_near_duplicate(
        self,
        content: str,
        app_id: str
    ) -> Optional[DedupResult]:
        """Check for near-duplicate using text similarity."""
        # Use more_like_this query for near-duplicate detection
        query = {
            "size": 1,
            "min_score": 0.9,  # High threshold for near-duplicate
            "query": {
                "bool": {
                    "must": [
                        {
                            "more_like_this": {
                                "fields": ["cleansed_content"],
                                "like": content,
                                "min_term_freq": 1,
                                "max_query_terms": 25,
                                "min_doc_freq": 1
                            }
                        }
                    ],
                    "filter": [
                        {"term": {"app_id": app_id}},
                        {"term": {"is_duplicate": False}}
                    ]
                }
            },
            "_source": ["review_id", "cleansed_content"]
        }

        try:
            response = self._os.client.search(index=self._index, body=query)
            hits = response['hits']['hits']

            if hits:
                hit = hits[0]
                score = hit['_score']

                # Normalize score to 0-1 range (approximate)
                normalized_score = min(1.0, score / 10.0)

                if normalized_score >= self.SIMILARITY_THRESHOLD:
                    return DedupResult(
                        is_duplicate=True,
                        duplicate_of=hit['_source']['review_id'],
                        similarity_score=normalized_score,
                        method="near_duplicate"
                    )

            return None
        except Exception as e:
            logger.warning(f"Near-duplicate check failed: {e}")
            return None

    async def check_batch(
        self,
        items: List[Tuple[str, str, str]],  # (review_id, content, app_id)
        check_near_duplicate: bool = False
    ) -> Dict[str, DedupResult]:
        """
        Check multiple items for duplicates.

        Near-duplicate check is disabled by default for batch operations
        due to performance considerations.

        Args:
            items: List of (review_id, content, app_id) tuples
            check_near_duplicate: Whether to check near-duplicates

        Returns:
            Dict mapping review_id to DedupResult
        """
        results = {}
        seen_in_batch: Dict[str, str] = {}  # hash -> first review_id in batch

        for review_id, content, app_id in items:
            content_hash = self.compute_hash(content)
            batch_key = f"{app_id}:{content_hash}"

            # Check if already seen in this batch
            if batch_key in seen_in_batch:
                results[review_id] = DedupResult(
                    is_duplicate=True,
                    duplicate_of=seen_in_batch[batch_key],
                    similarity_score=1.0,
                    method="exact_hash"
                )
                continue

            # Check against existing data
            result = await self.check_duplicate(
                content, app_id, check_near_duplicate
            )
            results[review_id] = result

            # Track unique items for batch dedup
            if not result.is_duplicate:
                seen_in_batch[batch_key] = review_id

        return results

    async def mark_as_duplicate(
        self,
        review_id: str,
        duplicate_of: str
    ) -> bool:
        """Mark a review as duplicate in OpenSearch."""
        try:
            self._os.client.update(
                index=self._index,
                id=review_id,
                body={
                    "doc": {
                        "is_duplicate": True,
                        "duplicate_of": duplicate_of,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                refresh=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to mark duplicate: {e}")
            return False

    async def get_duplicate_stats(
        self,
        app_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get statistics about duplicates."""
        query = {"bool": {"filter": []}}

        if app_id:
            query["bool"]["filter"].append({"term": {"app_id": app_id}})

        agg_query = {
            "size": 0,
            "query": query if query["bool"]["filter"] else {"match_all": {}},
            "aggs": {
                "total_reviews": {"value_count": {"field": "review_id"}},
                "duplicate_count": {
                    "filter": {"term": {"is_duplicate": True}}
                },
                "unique_count": {
                    "filter": {"term": {"is_duplicate": False}}
                },
                "duplicates_by_app": {
                    "filter": {"term": {"is_duplicate": True}},
                    "aggs": {
                        "by_app": {
                            "terms": {"field": "app_id", "size": 50}
                        }
                    }
                }
            }
        }

        try:
            response = self._os.client.search(index=self._index, body=agg_query)
            aggs = response['aggregations']

            total = aggs['total_reviews']['value']
            duplicates = aggs['duplicate_count']['doc_count']
            unique = aggs['unique_count']['doc_count']

            return {
                'total_reviews': total,
                'duplicate_count': duplicates,
                'unique_count': unique,
                'duplicate_rate': duplicates / total if total > 0 else 0,
                'by_app': aggs['duplicates_by_app']['by_app']['buckets']
            }
        except Exception as e:
            logger.error(f"Failed to get duplicate stats: {e}")
            return {}


# Singleton instance
_dedup_service: Optional[DedupService] = None


def get_dedup_service() -> DedupService:
    """Get singleton DedupService instance."""
    global _dedup_service
    if _dedup_service is None:
        _dedup_service = DedupService()
    return _dedup_service
