"""
Word Analysis Service.
Performs word count, ranking, and frequency analysis on reviews.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from pydantic import ValidationError
from app.schemas.service_models import (
    WordRankingResult as PydanticWordRankingResult,
    WordRankingItem as PydanticWordRankingItem
)
from app.core.opensearch_client import OpenSearchClient, get_opensearch_client
from app.core.redis_client import RedisClient, get_redis_client

logger = logging.getLogger(__name__)

# Redis key patterns
WORD_RANK_KEY = "word:rank:{sentiment}:{app_id}:{date}"
WORD_FREQ_KEY = "word:freq:{app_id}:{date}"

# Korean stopwords (common particles, connectors)
KOREAN_STOPWORDS = {
    '이', '가', '은', '는', '을', '를', '의', '에', '에서', '로', '으로',
    '와', '과', '하고', '이고', '인', '한', '할', '하는', '된', '되는',
    '것', '수', '등', '및', '또', '또한', '그', '저', '이런', '그런',
    '좀', '잘', '더', '매우', '정말', '너무', '아주', '참',
    '했', '했다', '합니다', '입니다', '있다', '없다', '있습니다', '없습니다',
    '해요', '해서', '하면', '되면', '같은', '같이', '위해', '대한',
    '앱', '어플', '앱이', '앱을', '앱은', '앱에서'
}

# Sentiment categories for word ranking
NEGATIVE_SENTIMENTS = {'very_negative', 'negative'}
POSITIVE_SENTIMENTS = {'very_positive', 'positive'}


@dataclass
class WordFrequency:
    """Word frequency data."""
    word: str
    count: int
    rank: int
    percentage: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'word': self.word,
            'count': self.count,
            'rank': self.rank,
            'percentage': round(self.percentage, 4)
        }


@dataclass
class WordRankingResult:
    """Result of word ranking analysis."""
    sentiment_type: str  # "negative", "positive", "all"
    period: str
    total_reviews: int
    total_words: int
    top_words: List[WordFrequency]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'sentiment_type': self.sentiment_type,
            'period': self.period,
            'total_reviews': self.total_reviews,
            'total_words': self.total_words,
            'top_words': [w.to_dict() for w in self.top_words],
            'generated_at': self.generated_at.isoformat()
        }


class WordAnalysisService:
    """
    Service for word frequency analysis and ranking.

    Features:
    - Word count by sentiment type
    - Word ranking (top N words)
    - Trend analysis over time
    - Caching with Redis
    """

    def __init__(
        self,
        os_client: Optional[OpenSearchClient] = None,
        redis_client: Optional[RedisClient] = None
    ):
        self._os = os_client or get_opensearch_client()
        self._redis = redis_client or get_redis_client()
        self._index = "app_reviews"
        self._stopwords = KOREAN_STOPWORDS

    def tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization for Korean text.

        Note: For production, consider using KoNLPy or similar.
        This is a basic implementation that splits on whitespace
        and removes punctuation.
        """
        # Remove special characters but keep Korean/English/numbers
        cleaned = re.sub(r'[^\w\s가-힣]', ' ', text)

        # Split on whitespace
        tokens = cleaned.split()

        # Filter out stopwords and short tokens
        filtered = [
            t.lower() for t in tokens
            if len(t) >= 2 and t.lower() not in self._stopwords
        ]

        return filtered

    async def count_words(
        self,
        reviews: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Count word frequencies from reviews."""
        counter = Counter()

        for review in reviews:
            content = review.get('cleansed_content', '')
            tokens = self.tokenize(content)
            counter.update(tokens)

        return dict(counter)

    async def get_word_ranking(
        self,
        app_id: Optional[str] = None,
        sentiment_type: str = "all",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        top_n: int = 50,
        use_cache: bool = True
    ) -> WordRankingResult:
        """
        Get word ranking for specified criteria.

        Args:
            app_id: Filter by app ID (None for all apps)
            sentiment_type: "negative", "positive", or "all"
            date_from: Start date filter
            date_to: End date filter
            top_n: Number of top words to return
            use_cache: Whether to use cached results

        Returns:
            WordRankingResult with top words
        """
        # Check cache first
        cache_key = self._build_cache_key(app_id, sentiment_type, date_from, date_to)
        if use_cache:
            cached = await self._get_from_cache(cache_key)
            if cached:
                return cached

        # Build query
        query = self._build_query(app_id, sentiment_type, date_from, date_to)

        # Fetch reviews
        reviews = await self._fetch_reviews(query)

        # Count words
        word_counts = await self.count_words(reviews)
        total_words = sum(word_counts.values())

        # Build ranking
        sorted_words = sorted(
            word_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        top_words = [
            WordFrequency(
                word=word,
                count=count,
                rank=i + 1,
                percentage=(count / total_words * 100) if total_words > 0 else 0
            )
            for i, (word, count) in enumerate(sorted_words)
        ]

        # Build period string
        period = self._build_period_string(date_from, date_to)

        result = WordRankingResult(
            sentiment_type=sentiment_type,
            period=period,
            total_reviews=len(reviews),
            total_words=total_words,
            top_words=top_words
        )

        # Cache result
        if use_cache:
            await self._set_cache(cache_key, result)

        return result

    def _build_query(
        self,
        app_id: Optional[str],
        sentiment_type: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime]
    ) -> Dict[str, Any]:
        """Build OpenSearch query."""
        filters = [{"term": {"is_duplicate": False}}]

        if app_id:
            filters.append({"term": {"app_id": app_id}})

        if sentiment_type == "negative":
            filters.append({"terms": {"sentiment.label": list(NEGATIVE_SENTIMENTS)}})
        elif sentiment_type == "positive":
            filters.append({"terms": {"sentiment.label": list(POSITIVE_SENTIMENTS)}})

        if date_from or date_to:
            date_filter = {"range": {"review_date": {}}}
            if date_from:
                date_filter["range"]["review_date"]["gte"] = date_from.isoformat()
            if date_to:
                date_filter["range"]["review_date"]["lte"] = date_to.isoformat()
            filters.append(date_filter)

        return {
            "query": {
                "bool": {"filter": filters}
            },
            "_source": ["cleansed_content", "sentiment.label"],
            "size": 10000  # Adjust based on data volume
        }

    async def _fetch_reviews(
        self,
        query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Fetch reviews from OpenSearch using scroll."""
        reviews = []

        try:
            # Initial search
            response = await self._os.async_client.search(
                index=self._index,
                body=query,
                scroll='2m'
            )

            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']

            while hits:
                reviews.extend([hit['_source'] for hit in hits])

                # Continue scrolling
                response = await self._os.async_client.scroll(
                    scroll_id=scroll_id,
                    scroll='2m'
                )
                scroll_id = response['_scroll_id']
                hits = response['hits']['hits']

            # Clear scroll
            await self._os.async_client.clear_scroll(scroll_id=scroll_id)

        except Exception as e:
            logger.error(f"Failed to fetch reviews: {e}")

        return reviews

    def _build_cache_key(
        self,
        app_id: Optional[str],
        sentiment_type: str,
        date_from: Optional[datetime],
        date_to: Optional[datetime]
    ) -> str:
        """Build cache key for word ranking."""
        app_part = app_id or "all"
        date_part = ""
        if date_from:
            date_part += date_from.strftime("%Y%m%d")
        if date_to:
            date_part += f"-{date_to.strftime('%Y%m%d')}"
        if not date_part:
            date_part = "all"

        return f"word:rank:{sentiment_type}:{app_part}:{date_part}"

    def _build_period_string(
        self,
        date_from: Optional[datetime],
        date_to: Optional[datetime]
    ) -> str:
        """Build human-readable period string."""
        if date_from and date_to:
            return f"{date_from.strftime('%Y-%m-%d')} ~ {date_to.strftime('%Y-%m-%d')}"
        elif date_from:
            return f"{date_from.strftime('%Y-%m-%d')} 이후"
        elif date_to:
            return f"{date_to.strftime('%Y-%m-%d')} 이전"
        return "전체 기간"

    async def _get_from_cache(
        self,
        cache_key: str
    ) -> Optional[WordRankingResult]:
        """Get cached result from Redis with Pydantic validation."""
        try:
            import json
            data = self._redis.master.get(cache_key)
            if data:
                # Decode if bytes
                if isinstance(data, bytes):
                    data = data.decode('utf-8')

                parsed = json.loads(data)

                # Validate with Pydantic (if data structure matches)
                # Note: Current cache may have different structure (sentiment_type, period, top_words)
                # vs Pydantic schema (unique_words, rankings). Handle both formats.
                try:
                    # Try to validate if data has Pydantic-compatible structure
                    if 'rankings' in parsed and 'unique_words' in parsed:
                        pydantic_result = PydanticWordRankingResult.model_validate(parsed)
                        logger.info(f"Pydantic validation successful for cache key: {cache_key}")
                        # Convert to dataclass for backward compatibility
                        return WordRankingResult(
                            sentiment_type=parsed.get('sentiment_type', 'all'),
                            period=parsed.get('period', '전체 기간'),
                            total_reviews=pydantic_result.total_reviews,
                            total_words=pydantic_result.total_words,
                            top_words=[
                                WordFrequency(
                                    word=item.word,
                                    count=item.count,
                                    rank=item.rank,
                                    percentage=item.percentage or 0.0
                                )
                                for item in pydantic_result.rankings
                            ],
                            generated_at=datetime.fromisoformat(pydantic_result.generated_at) if pydantic_result.generated_at else datetime.utcnow()
                        )
                except ValidationError as ve:
                    logger.warning(
                        f"Pydantic validation failed for {cache_key}: "
                        f"{ve.error_count()} errors. Using legacy format."
                    )

                # Fallback to legacy dataclass format
                return WordRankingResult(
                    sentiment_type=parsed['sentiment_type'],
                    period=parsed['period'],
                    total_reviews=parsed['total_reviews'],
                    total_words=parsed['total_words'],
                    top_words=[
                        WordFrequency(**w) for w in parsed['top_words']
                    ],
                    generated_at=datetime.fromisoformat(parsed['generated_at'])
                )
            return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def _set_cache(
        self,
        cache_key: str,
        result: WordRankingResult,
        ttl_hours: int = 1
    ) -> bool:
        """Cache result in Redis."""
        try:
            import json
            data = json.dumps(result.to_dict())
            self._redis.master.setex(
                cache_key,
                ttl_hours * 3600,
                data
            )
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False

    async def get_word_trend(
        self,
        word: str,
        app_id: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get trend of a specific word over time.

        Returns daily count of the word.
        """
        date_to = datetime.utcnow()
        from datetime import timedelta
        date_from = date_to - timedelta(days=days)

        filters = [
            {"term": {"is_duplicate": False}},
            {"match": {"cleansed_content": word}},
            {"range": {
                "review_date": {
                    "gte": date_from.isoformat(),
                    "lte": date_to.isoformat()
                }
            }}
        ]

        if app_id:
            filters.append({"term": {"app_id": app_id}})

        query = {
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggs": {
                "daily_count": {
                    "date_histogram": {
                        "field": "review_date",
                        "calendar_interval": "day",
                        "format": "yyyy-MM-dd"
                    }
                }
            }
        }

        try:
            response = await self._os.async_client.search(index=self._index, body=query)
            buckets = response['aggregations']['daily_count']['buckets']

            return [
                {
                    'date': bucket['key_as_string'],
                    'count': bucket['doc_count']
                }
                for bucket in buckets
            ]
        except Exception as e:
            logger.error(f"Failed to get word trend: {e}")
            return []

    async def compare_word_rankings(
        self,
        app_ids: List[str],
        sentiment_type: str = "negative",
        top_n: int = 20
    ) -> Dict[str, WordRankingResult]:
        """
        Compare word rankings across multiple apps.

        Useful for competitor analysis.
        """
        results = {}

        for app_id in app_ids:
            result = await self.get_word_ranking(
                app_id=app_id,
                sentiment_type=sentiment_type,
                top_n=top_n,
                use_cache=True
            )
            results[app_id] = result

        return results


# Singleton instance
_word_analysis_service: Optional[WordAnalysisService] = None


def get_word_analysis_service() -> WordAnalysisService:
    """Get singleton WordAnalysisService instance."""
    global _word_analysis_service
    if _word_analysis_service is None:
        _word_analysis_service = WordAnalysisService()
    return _word_analysis_service
