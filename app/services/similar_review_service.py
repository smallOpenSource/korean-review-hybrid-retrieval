"""
Similar Review Search Service with Reranking.
Finds similar reviews using vector search + reranking for improved relevance.

RAG Pipeline:
1. Query → Embedding (bge-m3-ko)
2. Vector Search → Top-K candidates (e.g., k=100)
3. Rerank (bge-reranker-v2-m3) → Final Top-N results
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from pydantic import ValidationError
from app.schemas.service_models import (
    SimilarReviewItem as PydanticSimilarReviewItem,
    SimilarReviewResult as PydanticSimilarReviewResult,
    DailyCount as PydanticDailyCount
)
from app.core.opensearch_client import OpenSearchClient, get_opensearch_client
from app.agents.embedding_service import EmbeddingService, get_embedding_service
from app.agents.rerank_service import RerankService, get_rerank_service

logger = logging.getLogger(__name__)


@dataclass
class SimilarReview:
    """A similar review with similarity score."""
    review_id: str
    content: str
    similarity_score: float
    rerank_score: Optional[float]  # Score from reranker
    app_name: str
    rating: int
    review_date: datetime
    sentiment_label: str
    complaint_type: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'review_id': self.review_id,
            'content': self.content,
            'similarity_score': round(self.similarity_score, 4),
            'app_name': self.app_name,
            'rating': self.rating,
            'review_date': self.review_date.isoformat(),
            'sentiment_label': self.sentiment_label,
            'complaint_type': self.complaint_type
        }
        if self.rerank_score is not None:
            result['rerank_score'] = round(self.rerank_score, 4)
        return result


@dataclass
class DailyCount:
    """Daily count for trend analysis."""
    date: str
    count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {'date': self.date, 'count': self.count}


@dataclass
class SimilarReviewResult:
    """Result of similar review search."""
    query_review_id: Optional[str]
    query_content: str
    similar_reviews: List[SimilarReview]
    daily_trend: List[DailyCount]
    total_similar_count: int
    search_method: str  # "vector", "vector+rerank", "keyword"
    reranked: bool = False
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'query_review_id': self.query_review_id,
            'query_content': self.query_content[:100] + '...' if len(self.query_content) > 100 else self.query_content,
            'similar_reviews': [r.to_dict() for r in self.similar_reviews],
            'daily_trend': [d.to_dict() for d in self.daily_trend],
            'total_similar_count': self.total_similar_count,
            'search_method': self.search_method,
            'reranked': self.reranked,
            'generated_at': self.generated_at.isoformat()
        }


class SimilarReviewService:
    """
    Service for finding similar reviews with reranking support.

    RAG Pipeline:
    1. Vector Search: Get Top-K candidates using bge-m3-ko embeddings
    2. Rerank: Reorder candidates using bge-reranker-v2-m3
    3. Return: Final Top-N most relevant results

    Features:
    - Vector similarity search (primary)
    - Reranking for improved relevance
    - Keyword-based search (fallback)
    - Historical trend analysis
    """

    # Default settings
    DEFAULT_SIMILARITY_THRESHOLD = 0.5  # Lower threshold for initial retrieval
    DEFAULT_CANDIDATE_K = 100  # Number of candidates for reranking
    DEFAULT_FINAL_K = 20  # Final number of results after reranking

    def __init__(
        self,
        os_client: Optional[OpenSearchClient] = None,
        embedding_service: Optional[EmbeddingService] = None,
        rerank_service: Optional[RerankService] = None
    ):
        self._os = os_client or get_opensearch_client()
        self._embedding = embedding_service or get_embedding_service()
        self._rerank = rerank_service or get_rerank_service()
        self._index = "app_reviews"

    async def find_similar(
        self,
        content: str,
        review_id: Optional[str] = None,
        app_id: Optional[str] = None,
        k: int = DEFAULT_FINAL_K,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        min_similarity: float = DEFAULT_SIMILARITY_THRESHOLD,
        use_rerank: bool = True,
        include_trend: bool = True,
        trend_days: int = 30
    ) -> SimilarReviewResult:
        """
        Find reviews similar to the given content with reranking.

        Args:
            content: Review content to find similar reviews for
            review_id: Optional ID of the source review (to exclude from results)
            app_id: Optional app ID filter
            k: Final number of results to return
            candidate_k: Number of candidates for reranking (should be > k)
            min_similarity: Minimum similarity score for initial retrieval
            use_rerank: Whether to use reranking
            include_trend: Whether to include daily trend data
            trend_days: Number of days for trend analysis

        Returns:
            SimilarReviewResult with similar reviews and trends
        """
        search_method = "vector"
        reranked = False

        # Try vector search first
        try:
            embedding_result = await self._embedding.embed(content)

            # Get more candidates for reranking
            fetch_k = candidate_k if use_rerank else k
            candidates, search_method = await self._vector_search(
                embedding_result.embedding,
                review_id,
                app_id,
                fetch_k,
                min_similarity
            )

            # Apply reranking if enabled and we have candidates
            if use_rerank and candidates and len(candidates) > 1:
                try:
                    candidates = await self._rerank_results(content, candidates, k)
                    search_method = "vector+rerank"
                    reranked = True
                except Exception as e:
                    logger.warning(f"Reranking failed, using vector scores: {e}")
                    candidates = candidates[:k]
            else:
                candidates = candidates[:k]

            similar_reviews = candidates

        except Exception as e:
            logger.warning(f"Vector search failed, falling back to keyword: {e}")
            similar_reviews, search_method = await self._keyword_search(
                content,
                review_id,
                app_id,
                k
            )

        # Get daily trend if requested
        daily_trend = []
        total_similar_count = len(similar_reviews)

        if include_trend and similar_reviews:
            daily_trend = await self._get_daily_trend(
                content,
                app_id,
                trend_days,
                search_method.startswith("vector")
            )
            total_similar_count = sum(d.count for d in daily_trend)

        return SimilarReviewResult(
            query_review_id=review_id,
            query_content=content,
            similar_reviews=similar_reviews,
            daily_trend=daily_trend,
            total_similar_count=total_similar_count,
            search_method=search_method,
            reranked=reranked
        )

    async def _rerank_results(
        self,
        query: str,
        candidates: List[SimilarReview],
        top_n: int
    ) -> List[SimilarReview]:
        """Rerank candidates using bge-reranker-v2-m3."""
        if not candidates:
            return []

        # Extract texts for reranking
        texts = [c.content for c in candidates]

        # Rerank
        rerank_response = await self._rerank.rerank(query, texts, top_n)

        # Map reranked results back to SimilarReview objects
        reranked_reviews = []
        for result in rerank_response.results:
            original_review = candidates[result.index]
            reranked_reviews.append(SimilarReview(
                review_id=original_review.review_id,
                content=original_review.content,
                similarity_score=original_review.similarity_score,
                rerank_score=result.score,
                app_name=original_review.app_name,
                rating=original_review.rating,
                review_date=original_review.review_date,
                sentiment_label=original_review.sentiment_label,
                complaint_type=original_review.complaint_type
            ))

        return reranked_reviews

    async def _vector_search(
        self,
        query_vector: List[float],
        exclude_id: Optional[str],
        app_id: Optional[str],
        k: int,
        min_similarity: float
    ) -> Tuple[List[SimilarReview], str]:
        """Perform KNN vector search."""
        must_not = []
        filter_clauses = [{"term": {"is_duplicate": False}}]

        if exclude_id:
            must_not.append({"term": {"review_id": exclude_id}})
        if app_id:
            filter_clauses.append({"term": {"app_id": app_id}})

        query = {
            "size": k,
            "min_score": min_similarity,
            "query": {
                "bool": {
                    "must": {
                        "knn": {
                            "content_embedding": {
                                "vector": query_vector,
                                "k": k * 2
                            }
                        }
                    },
                    "filter": filter_clauses,
                    "must_not": must_not
                }
            },
            "_source": [
                "review_id", "cleansed_content", "app_name", "rating",
                "review_date", "sentiment.label", "complaint.type"
            ]
        }

        try:
            response = self._os.client.search(index=self._index, body=query)
            reviews = self._parse_search_results(response['hits']['hits'])
            return reviews, "vector"
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return [], "vector"

    async def _keyword_search(
        self,
        query_text: str,
        exclude_id: Optional[str],
        app_id: Optional[str],
        k: int
    ) -> Tuple[List[SimilarReview], str]:
        """Perform BM25 keyword search."""
        must_not = []
        filter_clauses = [{"term": {"is_duplicate": False}}]

        if exclude_id:
            must_not.append({"term": {"review_id": exclude_id}})
        if app_id:
            filter_clauses.append({"term": {"app_id": app_id}})

        query = {
            "size": k,
            "query": {
                "bool": {
                    "must": {
                        "more_like_this": {
                            "fields": ["cleansed_content"],
                            "like": query_text,
                            "min_term_freq": 1,
                            "max_query_terms": 30,
                            "min_doc_freq": 1,
                            "boost_terms": 1
                        }
                    },
                    "filter": filter_clauses,
                    "must_not": must_not
                }
            },
            "_source": [
                "review_id", "cleansed_content", "app_name", "rating",
                "review_date", "sentiment.label", "complaint.type"
            ]
        }

        try:
            response = self._os.client.search(index=self._index, body=query)
            reviews = self._parse_search_results(response['hits']['hits'])
            return reviews, "keyword"
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return [], "keyword"

    def _parse_search_results(
        self,
        hits: List[Dict[str, Any]]
    ) -> List[SimilarReview]:
        """Parse search results into SimilarReview objects with Pydantic validation."""
        reviews = []

        for hit in hits:
            source = hit['_source']
            score = hit.get('_score', 0)

            # Normalize score (KNN returns cosine similarity 0-1)
            # BM25 returns unbounded scores, normalize approximately
            if score > 1:
                score = min(1.0, score / 10.0)

            try:
                review_date = datetime.fromisoformat(
                    source['review_date'].replace('Z', '+00:00')
                )
            except (ValueError, KeyError):
                review_date = datetime.utcnow()

            # Prepare data for Pydantic validation
            review_data = {
                'review_id': source.get('review_id', ''),
                'content': source.get('cleansed_content', ''),
                'similarity_score': max(0.0, min(1.0, score)),  # Clamp to [0, 1]
                'rerank_score': None,
                'app_name': source.get('app_name', ''),
                'rating': max(1, min(5, source.get('rating', 3))),  # Clamp to [1, 5]
                'review_date': review_date.isoformat(),
                'sentiment_label': source.get('sentiment', {}).get('label', 'unknown'),
                'complaint_type': source.get('complaint', {}).get('type')
            }

            # Validate with Pydantic
            try:
                validated = PydanticSimilarReviewItem.model_validate(review_data)

                # Create dataclass with validated data
                reviews.append(SimilarReview(
                    review_id=validated.review_id,
                    content=validated.content,
                    similarity_score=validated.similarity_score,
                    rerank_score=validated.rerank_score,
                    app_name=validated.app_name,
                    rating=validated.rating,
                    review_date=datetime.fromisoformat(validated.review_date),
                    sentiment_label=validated.sentiment_label,
                    complaint_type=validated.complaint_type
                ))

            except ValidationError as ve:
                logger.warning(
                    f"Review validation failed for {source.get('review_id', 'unknown')}: "
                    f"{ve.error_count()} errors. Skipping."
                )
                logger.debug(f"Validation errors: {ve.errors()}")
                continue

        return reviews

    async def _get_daily_trend(
        self,
        query_content: str,
        app_id: Optional[str],
        days: int,
        use_vector: bool
    ) -> List[DailyCount]:
        """Get daily count of similar reviews."""
        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

        filter_clauses = [
            {"term": {"is_duplicate": False}},
            {"range": {
                "review_date": {
                    "gte": date_from.isoformat(),
                    "lte": date_to.isoformat()
                }
            }}
        ]

        if app_id:
            filter_clauses.append({"term": {"app_id": app_id}})

        query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": {
                        "more_like_this": {
                            "fields": ["cleansed_content"],
                            "like": query_content,
                            "min_term_freq": 1,
                            "max_query_terms": 20,
                            "min_doc_freq": 1
                        }
                    },
                    "filter": filter_clauses
                }
            },
            "aggs": {
                "daily_count": {
                    "date_histogram": {
                        "field": "review_date",
                        "calendar_interval": "day",
                        "format": "yyyy-MM-dd",
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": date_from.strftime("%Y-%m-%d"),
                            "max": date_to.strftime("%Y-%m-%d")
                        }
                    }
                }
            }
        }

        try:
            response = self._os.client.search(index=self._index, body=query)
            buckets = response['aggregations']['daily_count']['buckets']

            daily_counts = []
            for bucket in buckets:
                try:
                    # Validate with Pydantic
                    validated = PydanticDailyCount.model_validate({
                        'date': bucket['key_as_string'],
                        'count': bucket['doc_count']
                    })

                    # Create dataclass with validated data
                    daily_counts.append(DailyCount(
                        date=validated.date,
                        count=validated.count
                    ))

                except ValidationError as ve:
                    logger.warning(
                        f"Daily count validation failed for {bucket.get('key_as_string')}: "
                        f"{ve.error_count()} errors. Skipping."
                    )
                    continue

            return daily_counts

        except Exception as e:
            logger.error(f"Failed to get daily trend: {e}")
            return []

    async def find_similar_by_review_id(
        self,
        review_id: str,
        **kwargs
    ) -> SimilarReviewResult:
        """
        Find similar reviews using an existing review ID.

        Fetches the review content and embedding from OpenSearch.
        """
        try:
            response = self._os.client.get(
                index=self._index,
                id=review_id,
                _source=["cleansed_content", "content_embedding", "app_id"]
            )
            source = response['_source']
            content = source.get('cleansed_content', '')

            # Use content-based search with reranking
            return await self.find_similar(
                content=content,
                review_id=review_id,
                app_id=kwargs.get('app_id', source.get('app_id')),
                **{k: v for k, v in kwargs.items() if k not in ['app_id']}
            )

        except Exception as e:
            logger.error(f"Failed to find similar by review ID: {e}")
            raise ValueError(f"Review not found: {review_id}")

    async def get_similar_complaints(
        self,
        content: str,
        app_id: Optional[str] = None,
        k: int = 10,
        candidate_k: int = 50,
        use_rerank: bool = True
    ) -> SimilarReviewResult:
        """
        Find similar complaints specifically with reranking.

        Filters to only complaint reviews.
        """
        search_method = "vector"
        reranked = False

        try:
            embedding_result = await self._embedding.embed(content)

            fetch_k = candidate_k if use_rerank else k

            query = {
                "size": fetch_k,
                "query": {
                    "bool": {
                        "must": {
                            "knn": {
                                "content_embedding": {
                                    "vector": embedding_result.embedding,
                                    "k": fetch_k * 2
                                }
                            }
                        },
                        "filter": [
                            {"term": {"complaint.is_complaint": True}},
                            {"term": {"is_duplicate": False}}
                        ]
                    }
                },
                "_source": [
                    "review_id", "cleansed_content", "app_name", "rating",
                    "review_date", "sentiment.label", "complaint.type"
                ]
            }

            if app_id:
                query["query"]["bool"]["filter"].append({"term": {"app_id": app_id}})

            response = self._os.client.search(index=self._index, body=query)
            candidates = self._parse_search_results(response['hits']['hits'])

            # Apply reranking
            if use_rerank and candidates and len(candidates) > 1:
                try:
                    similar_reviews = await self._rerank_results(content, candidates, k)
                    search_method = "vector+rerank"
                    reranked = True
                except Exception as e:
                    logger.warning(f"Reranking failed: {e}")
                    similar_reviews = candidates[:k]
            else:
                similar_reviews = candidates[:k]

        except Exception as e:
            logger.warning(f"Vector search for complaints failed: {e}")
            similar_reviews = []
            search_method = "keyword"

        return SimilarReviewResult(
            query_review_id=None,
            query_content=content,
            similar_reviews=similar_reviews,
            daily_trend=[],
            total_similar_count=len(similar_reviews),
            search_method=search_method,
            reranked=reranked
        )


# Singleton instance
_similar_review_service: Optional[SimilarReviewService] = None


def get_similar_review_service() -> SimilarReviewService:
    """Get singleton SimilarReviewService instance."""
    global _similar_review_service
    if _similar_review_service is None:
        _similar_review_service = SimilarReviewService()
    return _similar_review_service
