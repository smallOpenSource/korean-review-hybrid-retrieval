"""
Review Service for OpenSearch operations.
Handles review storage, search, and aggregations.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from app.core.opensearch_client import OpenSearchClient, get_opensearch_client
from app.agents.embedding_service import EmbeddingService, get_embedding_service
from app.core.mysql_client import get_mysql_client
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# OpenSearch index name
REVIEW_INDEX = "app_reviews"

# Index mapping with Korean Nori analyzer and KNN for vector search
REVIEW_INDEX_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 3,
            "number_of_replicas": 1,
            "knn": True,
            "knn.algo_param.ef_search": 100
        },
        "analysis": {
            "tokenizer": {
                "nori_tokenizer": {
                    "type": "nori_tokenizer",
                    "decompound_mode": "mixed"
                }
            },
            "analyzer": {
                "korean": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": [
                        "nori_readingform",
                        "lowercase",
                        "nori_part_of_speech"
                    ]
                },
                "korean_search": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": [
                        "nori_readingform",
                        "lowercase"
                    ]
                }
            },
            "filter": {
                "nori_part_of_speech": {
                    "type": "nori_part_of_speech",
                    "stoptags": [
                        "E", "IC", "J", "MAG", "MAJ", "MM",
                        "SP", "SSC", "SSO", "SC", "SE",
                        "XPN", "XSA", "XSN", "XSV"
                    ]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            # === Identification ===
            "review_id": {"type": "keyword"},
            "content_hash": {"type": "keyword"},

            # === Source Information ===
            "app_id": {"type": "keyword"},
            "app_name": {"type": "keyword"},
            "company_code": {"type": "keyword"},
            "platform": {"type": "keyword"},

            # === Review Content ===
            "original_content": {
                "type": "text",
                "analyzer": "korean",
                "search_analyzer": "korean_search"
            },
            "cleansed_content": {
                "type": "text",
                "analyzer": "korean",
                "search_analyzer": "korean_search"
            },
            "rating": {"type": "integer"},

            # === Embedding Vector (1024 dims for bge-m3-ko) ===
            "content_embedding": {
                "type": "knn_vector",
                "dimension": get_settings().bge.embedding_dimensions,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 16
                    }
                }
            },

            # === Sentiment Analysis ===
            "sentiment": {
                "properties": {
                    "label": {"type": "keyword"},
                    "score": {"type": "integer"},
                    "emotions": {"type": "keyword"},
                    "confidence": {"type": "float"}
                }
            },

            # === Category Classification ===
            "category": {
                "properties": {
                    "primary": {"type": "keyword"},
                    "secondary": {"type": "keyword"},
                    "confidence": {"type": "float"}
                }
            },

            # === Complaint Analysis ===
            "complaint": {
                "properties": {
                    "is_complaint": {"type": "boolean"},
                    "type": {"type": "keyword"},
                    "sub_type": {"type": "keyword"},
                    "urgency": {"type": "integer"},
                    "severity": {"type": "integer"},
                    "primary_dept": {"type": "keyword"},
                    "secondary_depts": {"type": "keyword"},
                    "escalation_required": {"type": "boolean"},
                    "escalation_level": {"type": "keyword"},
                    "status": {"type": "keyword"}
                }
            },

            # === Metrics ===
            "metrics": {
                "properties": {
                    "feature": {
                        "properties": {
                            "detected": {"type": "boolean"},
                            "keywords": {"type": "keyword"},
                            "sub_categories": {"type": "keyword"}
                        }
                    },
                    "service": {
                        "properties": {
                            "detected": {"type": "boolean"},
                            "keywords": {"type": "keyword"},
                            "sub_categories": {"type": "keyword"}
                        }
                    },
                    "performance": {
                        "properties": {
                            "detected": {"type": "boolean"},
                            "keywords": {"type": "keyword"},
                            "issues": {"type": "keyword"}
                        }
                    },
                    "related_screen": {
                        "properties": {
                            "detected": {"type": "boolean"},
                            "screens": {"type": "keyword"},
                            "services": {"type": "keyword"}
                        }
                    }
                }
            },

            # === Complaint Information ===
            "complaint": {
                "properties": {
                    "is_complaint": {"type": "boolean"},
                    "type": {"type": "keyword"},
                    "sub_type": {"type": "keyword"},
                    "urgency": {"type": "integer"},
                    "severity": {"type": "integer"},
                    "primary_dept": {"type": "keyword"},
                    "secondary_depts": {"type": "keyword"},
                    "escalation_required": {"type": "boolean"},
                    "escalation_level": {"type": "keyword"},
                    "sla_deadline": {"type": "date"},
                    "status": {"type": "keyword"},
                    "assigned_to": {"type": "keyword"}
                }
            },

            # === LLM Analysis Metadata (for prompt improvement) ===
            "analysis_metadata": {
                "properties": {
                    "analysis_id": {"type": "keyword"},
                    "analyzed_at": {"type": "date"},
                    "model_name": {"type": "keyword"},
                    "is_secondary_model": {"type": "boolean"},
                    "input_tokens": {"type": "integer"},
                    "output_tokens": {"type": "integer"},
                    "latency_ms": {"type": "integer"},
                    "confidence_score": {"type": "float"},
                    "is_low_confidence": {"type": "boolean"},
                    "needs_review": {"type": "boolean"},
                    "prompt_template_id": {"type": "keyword"},
                    "prompt_version": {"type": "keyword"},
                    "reasoning": {
                        "type": "object",
                        "enabled": True
                    },
                    "feedback": {
                        "properties": {
                            "reviewed_by": {"type": "keyword"},
                            "reviewed_at": {"type": "date"},
                            "is_correct": {"type": "boolean"},
                            "corrected_values": {"type": "object"},
                            "notes": {"type": "text"}
                        }
                    }
                }
            },

            # === Timestamps ===
            "review_date": {"type": "date"},
            "collected_at": {"type": "date"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},

            # === Duplicate Tracking ===
            "is_duplicate": {"type": "boolean"},
            "duplicate_of": {"type": "keyword"},

            # === Word Analysis Cache ===
            "word_counts": {
                "type": "object",
                "enabled": False
            }
        }
    }
}


@dataclass
class ReviewDocument:
    """Review document for storage."""
    review_id: str
    app_id: str
    app_name: str
    company_code: str
    platform: str
    original_content: str
    cleansed_content: str
    rating: int
    review_date: datetime
    collected_at: datetime = field(default_factory=datetime.utcnow)

    # To be filled by analysis
    content_embedding: Optional[List[float]] = None
    sentiment: Optional[Dict[str, Any]] = None
    category: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    complaint: Optional[Dict[str, Any]] = None
    analysis_metadata: Optional[Dict[str, Any]] = None
    word_counts: Optional[Dict[str, int]] = None

    # Computed fields
    content_hash: str = ""
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None

    def __post_init__(self):
        """Compute content hash after initialization."""
        if not self.content_hash and self.cleansed_content:
            self.content_hash = self._compute_hash(self.cleansed_content)

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for OpenSearch."""
        doc = {
            'review_id': self.review_id,
            'content_hash': self.content_hash,
            'app_id': self.app_id,
            'app_name': self.app_name,
            'company_code': self.company_code,
            'platform': self.platform,
            'original_content': self.original_content,
            'cleansed_content': self.cleansed_content,
            'rating': self.rating,
            'review_date': self.review_date.isoformat(),
            'collected_at': self.collected_at.isoformat(),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'is_duplicate': self.is_duplicate,
            'duplicate_of': self.duplicate_of
        }

        if self.content_embedding:
            doc['content_embedding'] = self.content_embedding
        if self.sentiment:
            doc['sentiment'] = self.sentiment
        if self.category:
            doc['category'] = self.category
        if self.metrics:
            doc['metrics'] = self.metrics
        if self.complaint:
            doc['complaint'] = self.complaint
        if self.analysis_metadata:
            doc['analysis_metadata'] = self.analysis_metadata
        if self.word_counts:
            doc['word_counts'] = self.word_counts

        return doc


class ReviewService:
    """
    Service for managing reviews in OpenSearch.

    Features:
    - Index management
    - CRUD operations
    - Vector search
    - Aggregations
    - BM25 keyword search (when embedding unavailable)
    """

    def __init__(
        self,
        os_client: Optional[OpenSearchClient] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self._os = os_client or get_opensearch_client()
        self._embedding = embedding_service or get_embedding_service()
        self._index = REVIEW_INDEX

    async def _get_client(self) -> Any:
        """Get async OpenSearch client."""
        return self._os.async_client

    def ensure_index(self) -> bool:
        """Create index if it doesn't exist."""
        client = self._os.sync_client
        if not client.indices.exists(index=self._index):
            logger.info(f"Creating index: {self._index}")
            client.indices.create(
                index=self._index,
                body=REVIEW_INDEX_MAPPING
            )
            return True
        return False

    def index_review(
        self,
        review: ReviewDocument,
        generate_embedding: bool = True
    ) -> str:
        """
        Index a single review.

        Args:
            review: Review document to index
            generate_embedding: Whether to generate embedding for content

        Returns:
            Document ID
        """
        # Generate embedding if requested and not present
        if generate_embedding and not review.content_embedding:
            try:
                result = self._embedding.embed_sync(review.cleansed_content)
                review.content_embedding = result.embedding
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")
                # Continue without embedding - BM25 search will still work

        doc = review.to_dict()
        response = self._os.sync_client.index(
            index=self._index,
            id=review.review_id,
            body=doc,
            refresh=True
        )

        return response['_id']

    def index_reviews_bulk(
        self,
        reviews: List[ReviewDocument],
        generate_embeddings: bool = True
    ) -> Tuple[int, int]:
        """
        Bulk index reviews.

        Args:
            reviews: List of review documents
            generate_embeddings: Whether to generate embeddings

        Returns:
            Tuple of (success_count, failure_count)
        """
        if not reviews:
            return 0, 0

        # Generate embeddings in batch if requested
        if generate_embeddings:
            texts = [r.cleansed_content for r in reviews if not r.content_embedding]
            if texts:
                try:
                    results = self._embedding.embed_sync(texts)
                    text_idx = 0
                    for review in reviews:
                        if not review.content_embedding:
                            review.content_embedding = results[text_idx].embedding
                            text_idx += 1
                except Exception as e:
                    logger.warning(f"Failed to generate embeddings: {e}")

        # Prepare bulk operations
        operations = []
        for review in reviews:
            operations.append({
                "index": {
                    "_index": self._index,
                    "_id": review.review_id
                }
            })
            operations.append(review.to_dict())

        response = self._os.sync_client.bulk(body=operations, refresh=True)

        success = sum(1 for item in response['items'] if item['index'].get('status') in (200, 201))
        failure = len(reviews) - success

        return success, failure

    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get review by ID."""
        try:
            response = self._os.sync_client.get(index=self._index, id=review_id)
            return response['_source']
        except Exception:
            return None

    def update_review(
        self,
        review_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update review fields."""
        updates['updated_at'] = datetime.utcnow().isoformat()
        try:
            self._os.sync_client.update(
                index=self._index,
                id=review_id,
                body={"doc": updates},
                refresh=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update review {review_id}: {e}")
            return False

    def search_similar(
        self,
        query_text: str,
        k: int = 10,
        min_score: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar reviews using vector similarity.

        Falls back to BM25 keyword search if embedding fails.
        """
        # Generate embedding for query
        try:
            embedding_result = self._embedding.embed_sync(query_text)
            return self._vector_search(
                embedding_result.embedding,
                k,
                min_score,
                filters
            )
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to keyword search: {e}")
            return self._keyword_search(query_text, k, filters)

    def _vector_search(
        self,
        vector: List[float],
        k: int,
        min_score: float,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Perform KNN vector search."""
        query = {
            "size": k,
            "min_score": min_score,
            "query": {
                "knn": {
                    "content_embedding": {
                        "vector": vector,
                        "k": k
                    }
                }
            }
        }

        if filters:
            query["query"] = {
                "bool": {
                    "must": query["query"],
                    "filter": self._build_filter(filters)
                }
            }

        response = self._os.sync_client.search(index=self._index, body=query)
        return [
            {**hit['_source'], '_score': hit['_score']}
            for hit in response['hits']['hits']
        ]

    def _keyword_search(
        self,
        query_text: str,
        k: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Perform BM25 keyword search."""
        query = {
            "size": k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "cleansed_content": {
                                    "query": query_text,
                                    "analyzer": "korean_search",
                                    "boost": 2.0
                                }
                            }
                        },
                        {
                            "match": {
                                "original_content": {
                                    "query": query_text,
                                    "analyzer": "korean_search"
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            }
        }

        if filters:
            query["query"]["bool"]["filter"] = self._build_filter(filters)

        response = self._os.sync_client.search(index=self._index, body=query)
        return [
            {**hit['_source'], '_score': hit['_score']}
            for hit in response['hits']['hits']
        ]

    def _build_filter(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build OpenSearch filter from dictionary."""
        filter_clauses = []

        for field, value in filters.items():
            if isinstance(value, list):
                filter_clauses.append({"terms": {field: value}})
            elif isinstance(value, dict):
                if 'gte' in value or 'lte' in value:
                    filter_clauses.append({"range": {field: value}})
        return filter_clauses

    def aggregate_sentiment_sync(
        self,
        app_id: Optional[str] = None,
        days: int = 30,
        year: Optional[int] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aggregate sentiment statistics (Synchronous).
        """
        client = self._os.sync_client
        
        # 1. Current Period
        interval = "day"
        if year:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            date_range = (start_date, end_date)
            interval = "month"
        else:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            date_range = (start_date, end_date)
            if days > 90:
                interval = "week"
            if days > 365:
                interval = "year"
        
        # 2. Previous Period (for trends)
        if year:
            prev_year = year - 1
            prev_start_date = datetime(prev_year, 1, 1)
            prev_end_date = datetime(prev_year, 12, 31, 23, 59, 59)
            # If comparing with incomplete current year (YTD), we might want to cap prev_end_date?
            # For now, comparing with full previous year is a standard approach for "Yearly" stats,
            # or we could match the duration. Let's match the duration for fairness if current is incomplete.
            if end_date < datetime(year, 12, 31):
                # Current year is incomplete (YTD)
                duration = end_date - start_date
                prev_end_date = prev_start_date + duration
        else:
            prev_end_date = date_range[0]
            prev_start_date = prev_end_date - (date_range[1] - date_range[0])
        
        def build_query(dr):
            q = {"bool": {"must": [{"match_all": {}}]}}
            filters = []
            if app_id:
                # Expand app_id to include legacy IDs for unified view
                from app.services.app_service import get_app_service
                app_service = get_app_service()
                all_ids = app_service.get_all_package_ids(app_id)
                if all_ids:
                    filters.append({"terms": {"app_id": all_ids}})
                else:
                    filters.append({"term": {"app_id": app_id}})
            
            # Category filter
            if category and category != '0':
                category_map = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}
                group_code = category_map.get(category)
                if group_code:
                    from app.services.app_service import get_app_service
                    app_service = get_app_service()
                    apps = app_service.get_apps_by_group(group_code)
                    app_ids = [app['package_id'] for app in apps]
                    if app_ids:
                        filters.append({"terms": {"app_id": app_ids}})
                    else:
                        filters.append({"term": {"app_id": "NON_EXISTENT"}})

            filters.append({
                "range": {
                    "review_date": {
                        "gte": dr[0].isoformat(),
                        "lte": dr[1].isoformat()
                    }
                }
            })
            q["bool"]["filter"] = filters
            return q

        # Aggregations for both periods
        aggs_def = {
            "sentiment_distribution": {
                "terms": {"field": "sentiment.label"}
            },
            "avg_rating": {
                "avg": {"field": "rating"}
            },
            "sentiment_over_time": {
                "date_histogram": {
                    "field": "review_date",
                    "calendar_interval": interval
                },
                "aggs": {
                    "avg_score": {"avg": {"field": "sentiment.score"}},
                    "sentiment_breakdown": {
                        "terms": {
                            "field": "sentiment.label",
                            "size": 5
                        }
                    }
                }
            }
        }

        # Fetch Current
        curr_query = {
            "size": 0,
            "query": build_query(date_range),
            "aggs": aggs_def
        }
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DEBUG QUERY: {curr_query}")
        curr_resp = client.search(index=self._index, body=curr_query, track_total_hits=True)
        curr_aggs = curr_resp['aggregations']
        curr_total = curr_resp['hits']['total']['value']
        curr_rating = curr_aggs['avg_rating']['value'] or 0.0
        
        curr_pos_count = 0
        for bucket in curr_aggs['sentiment_distribution']['buckets']:
            key = bucket['key'].lower()
            if key in ['positive', 'very_positive']:
                curr_pos_count += bucket['doc_count']
        curr_pos_rate = (curr_pos_count / curr_total * 100) if curr_total > 0 else 0.0

        # Fetch Previous
        prev_query = {
            "size": 0,
            "query": build_query((prev_start_date, prev_end_date)),
            "aggs": {
                "sentiment_distribution": {
                    "terms": {"field": "sentiment.label"}
                },
                "avg_rating": {
                    "avg": {"field": "rating"}
                }
            }
        }
        prev_resp = client.search(index=self._index, body=prev_query, track_total_hits=True)
        prev_aggs = prev_resp['aggregations']
        prev_total = prev_resp['hits']['total']['value']
        prev_rating = prev_aggs['avg_rating']['value'] or 0.0
        
        prev_pos_count = 0
        for bucket in prev_aggs['sentiment_distribution']['buckets']:
            key = bucket['key'].lower()
            if key in ['positive', 'very_positive']:
                prev_pos_count += bucket['doc_count']
        prev_pos_rate = (prev_pos_count / prev_total * 100) if prev_total > 0 else 0.0

        # Calculate Changes (cap at ±999.9% to prevent absurd values)
        if prev_total > 0:
            raw_change = (curr_total - prev_total) / prev_total * 100
            reviews_change = max(-999.9, min(999.9, raw_change))
        else:
            reviews_change = 0.0
            
        rating_change = curr_rating - prev_rating
        pos_rate_change = curr_pos_rate - prev_pos_rate

        return {
            'total_reviews': curr_total,
            'average_rating': curr_rating,
            'positive_rate': curr_pos_rate,
            'reviews_change': reviews_change,
            'rating_change': rating_change,
            'pos_rate_change': pos_rate_change,
            'sentiment_trend': curr_aggs['sentiment_over_time']['buckets'],
            'raw_aggs': curr_aggs
        }

    def get_recent_reviews_sync(
        self,
        limit: int = 20,
        dept_code: Optional[str] = None,
        year: Optional[int] = None,
        category: Optional[str] = None,
        app_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent reviews (Synchronous).
        
        Args:
            limit: Number of reviews to return
            dept_code: Optional department code to filter by
            year: Optional year filter
            category: Optional category filter
            app_id: Optional app ID to filter by
        """
        query = {
            "size": limit,
            "sort": [{"review_date": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [{"match_all": {}}],
                    "filter": []
                }
            }
        }
        
        # Add filters
        if dept_code and dept_code != "ALL":
            # If dept_code is a division, we might need prefix query or similar
            # For now assuming exact match on escalated_to or primary_dept
            query["query"]["bool"]["filter"].append({
                "term": {"complaint.escalated_to": dept_code}
            })
            
        if app_id:
            # Expand app_id to include legacy IDs for unified view
            from app.services.app_service import get_app_service
            app_service = get_app_service()
            all_ids = app_service.get_all_package_ids(app_id)
            if all_ids:
                query["query"]["bool"]["filter"].append({"terms": {"app_id": all_ids}})
            else:
                query["query"]["bool"]["filter"].append({"term": {"app_id": app_id}})
        
        # Remove duplicate filter - the filter at lines 791-796 already handles dept_code

        # Year filter
        if year:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            query["query"]["bool"]["filter"].append({
                "range": {
                    "review_date": {
                        "gte": start_date.isoformat(),
                        "lte": end_date.isoformat()
                    }
                }
            })
            
        # Category filter
        if category and category != '0':
            category_map = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}
            group_code = category_map.get(category)
            if group_code:
                from app.services.app_service import get_app_service
                app_service = get_app_service()
                apps = app_service.get_apps_by_group(group_code)
                app_ids = [app['package_id'] for app in apps]
                if app_ids:
                    query["query"]["bool"]["filter"].append({"terms": {"app_id": app_ids}})
                else:
                    query["query"]["bool"]["filter"].append({"term": {"app_id": "NON_EXISTENT"}})
        
        try:
            response = self._os.sync_client.search(index=self._index, body=query)
            return response['hits']['hits']
        except Exception as e:
            logger.error(f"Failed to get recent reviews: {e}")
            return []

    def get_recent_complaints_sync(
        self,
        limit: int = 20,
        dept_code: Optional[str] = None,
        year: Optional[int] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent complaints (Synchronous).
        
        Args:
            limit: Number of complaints to return
            dept_code: Optional department code to filter by
            year: Optional year filter
            category: Optional category filter
        """
        query = {
            "size": limit,
            "sort": [{"review_date": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "sentiment"}}  # CRITICAL: Only analyzed reviews
                    ],
                    "filter": [
                        {"term": {"complaint.is_complaint": True}}
                    ]
                }
            }
        }
        
        if dept_code and dept_code != "ALL":
            query["query"]["bool"]["filter"].append(
                {"term": {"complaint.primary_dept": dept_code}}
            )

        # Year filter
        if year:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            query["query"]["bool"]["filter"].append({
                "range": {
                    "review_date": {
                        "gte": start_date.isoformat(),
                        "lte": end_date.isoformat()
                    }
                }
            })
        else:
            # Default to last 30 days to prevent full table scan
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            query["query"]["bool"]["filter"].append({
                "range": {
                    "review_date": {
                        "gte": start_date.isoformat(),
                        "lte": end_date.isoformat()
                    }
                }
            })
            
        # Category filter
        if category and category != '0':
            category_map = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}
            group_code = category_map.get(category)
            if group_code:
                from app.services.app_service import get_app_service
                app_service = get_app_service()
                apps = app_service.get_apps_by_group(group_code)
                app_ids = [app['package_id'] for app in apps]
                if app_ids:
                    query["query"]["bool"]["filter"].append({"terms": {"app_id": app_ids}})
                else:
                    query["query"]["bool"]["filter"].append({"term": {"app_id": "NON_EXISTENT"}})
        
        try:
            response = self._os.sync_client.search(index=self._index, body=query)
            return response['hits']['hits']
        except Exception as e:
            logger.error(f"Failed to get recent complaints: {e}")
            return []

    def get_complaint_stats_sync(
        self,
        app_id: Optional[str] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        days: int = 30,
        year: Optional[int] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get complaint statistics (Synchronous) with trends."""
        client = self._os.sync_client
        
        # 1. Current Period
        if not date_range:
            if year:
                start_date = datetime(year, 1, 1)
                end_date = datetime(year, 12, 31, 23, 59, 59)
                date_range = (start_date, end_date)
            elif days:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
                date_range = (start_date, end_date)
            else:
                # Default to 30 days
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=30)
                date_range = (start_date, end_date)
            
        # 2. Previous Period
        prev_end_date = date_range[0]
        prev_start_date = prev_end_date - (date_range[1] - date_range[0])
        
        def build_query(dr, is_complaint_only=True):
            q = {
                "bool": {
                    "must": [
                        {"exists": {"field": "sentiment"}}  # CRITICAL: Only analyzed reviews
                    ],
                    "filter": []
                }
            }
            
            if is_complaint_only:
                q["bool"]["filter"].append({"term": {"complaint.is_complaint": True}})
                
            if app_id:
                # Expand app_id to include legacy IDs for unified view
                from app.services.app_service import get_app_service
                app_service = get_app_service()
                all_ids = app_service.get_all_package_ids(app_id)
                if all_ids:
                    q["bool"]["filter"].append({"terms": {"app_id": all_ids}})
                else:
                    q["bool"]["filter"].append({"term": {"app_id": app_id}})
            
            # Category filter
            if category and category != '0':
                # Map category to group code if needed, or use direct filter if implemented
                # Assuming category maps to group_code which we need to resolve to app_ids
                # Or if we have category field in index. 
                # Current index has 'category.primary', but 'category' param is '1','2' etc.
                # Let's use the same mapping logic as other methods
                category_map = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}
                group_code = category_map.get(category)
                if group_code:
                    # We need to filter by apps in this group. 
                    # Ideally we should have group_code in the index.
                    # As a workaround, we can fetch apps for this group and filter by app_id terms
                    from app.services.app_service import get_app_service
                    app_service = get_app_service()
                    apps = app_service.get_apps_by_group(group_code)
                    app_ids = [app['package_id'] for app in apps]
                    if app_ids:
                        q["bool"]["filter"].append({"terms": {"app_id": app_ids}})
                    else:
                        # No apps in this category, force empty result
                        q["bool"]["filter"].append({"term": {"app_id": "NON_EXISTENT"}})

            q["bool"]["filter"].append({
                "range": {
                    "review_date": {
                        "gte": dr[0].isoformat(),
                        "lte": dr[1].isoformat()
                    }
                }
            })
            return q

        # Fetch Current
        curr_query = {
            "size": 0,
            "query": build_query(date_range, is_complaint_only=True),
            "aggs": {
                "complaint_status": {
                    "terms": {"field": "complaint.status"}
                },
                "complaint_department": {
                    "terms": {"field": "complaint.escalated_to"}
                }
            }
        }
        curr_resp = client.search(index=self._index, body=curr_query, track_total_hits=True)
        curr_total = curr_resp['hits']['total']['value']
        
        # Need total reviews to calculate rate
        # We can reuse aggregate_sentiment_sync logic or just query count
        curr_reviews_query = {
            "size": 0,
            "query": build_query(date_range, is_complaint_only=False)
        }
        curr_reviews_resp = client.search(index=self._index, body=curr_reviews_query, track_total_hits=True)
        curr_reviews_total = curr_reviews_resp['hits']['total']['value']
        
        logger.info(f"DEBUG: get_complaint_stats_sync - curr_total (complaints): {curr_total}")
        logger.info(f"DEBUG: get_complaint_stats_sync - curr_reviews_total (all): {curr_reviews_total}")
        logger.info(f"DEBUG: get_complaint_stats_sync - query (complaints): {curr_query}")
        logger.info(f"DEBUG: get_complaint_stats_sync - query (all): {curr_reviews_query}")

        complaint_rate = (curr_total / curr_reviews_total * 100) if curr_reviews_total > 0 else 0.0

        # 3. Trends (Daily)
        trend_query = {
            "size": 0,
            "query": build_query(date_range),
            "aggs": {
                "daily_complaints": {
                    "date_histogram": {
                        "field": "review_date",
                        "calendar_interval": "day"
                    }
                }
            }
        }
        trend_resp = client.search(index=self._index, body=trend_query)
        trend_buckets = trend_resp['aggregations']['daily_complaints']['buckets']
        
        trend_data = [
            {"date": b['key_as_string'].split('T')[0], "count": b['doc_count']}
            for b in trend_buckets
        ]

        return {
            "total_complaints": curr_total,
            "complaint_rate": round(complaint_rate, 1),
            "status_breakdown": {
                b['key']: b['doc_count'] 
                for b in curr_resp['aggregations']['complaint_status']['buckets']
            },
            "dept_breakdown": {
                b['key']: b['doc_count']
                for b in curr_resp['aggregations']['complaint_department']['buckets']
            },
            "trend": trend_data
        }

    def get_filter_counts_sync(
        self,
        dept_code: Optional[str] = None,
        app_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Dict[str, int]]:
        """
        Get counts for App and Dept filters based on current selection.
        """
        client = self._os.sync_client
        
        # Base time filter
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        time_filter = {
            "range": {
                "review_date": {
                    "gte": start_date.isoformat(),
                    "lte": end_date.isoformat()
                }
            }
        }

        # 1. Get App Counts (filtered by Dept if selected)
        # CRITICAL: Only count analyzed reviews with complaints
        app_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "sentiment"}},  # Only analyzed
                        {"term": {"complaint.is_complaint": True}}  # Only complaints
                    ],
                    "filter": [time_filter]
                }
            },
            "aggs": {
                "apps": {
                    "terms": {"field": "app_id", "size": 20}
                }
            }
        }
        if dept_code and dept_code != 'ALL':
             app_query["query"]["bool"]["filter"].append(
                 {"term": {"complaint.primary_dept": dept_code}}
             )

        # 2. Get Dept Counts (filtered by App if selected)
        dept_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "sentiment"}},
                        {"term": {"complaint.is_complaint": True}}
                    ],
                    "filter": [time_filter]
                }
            },
            "aggs": {
                "depts": {
                    "terms": {"field": "complaint.primary_dept", "size": 20}
                }
            }
        }
        if app_id:
            # Expand app_id to include legacy IDs for unified view
            from app.services.app_service import get_app_service
            app_service = get_app_service()
            all_ids = app_service.get_all_package_ids(app_id)
            if all_ids:
                dept_query["query"]["bool"]["filter"].append({"terms": {"app_id": all_ids}})
            else:
                dept_query["query"]["bool"]["filter"].append({"term": {"app_id": app_id}})

        # Execute
        try:
            app_resp = client.search(index=self._index, body=app_query)
            dept_resp = client.search(index=self._index, body=dept_query)

            app_counts = {
                bucket['key']: bucket['doc_count'] 
                for bucket in app_resp['aggregations']['apps']['buckets']
            }
            
            dept_counts = {
                bucket['key']: bucket['doc_count']
                for bucket in dept_resp['aggregations']['depts']['buckets']
            }
            
            return {
                "app_counts": app_counts,
                "dept_counts": dept_counts
            }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to get filter counts: {e}")
            return {"app_counts": {}, "dept_counts": {}}

    def get_filter_counts_from_mart(
        self,
        dept_code: Optional[str] = None,
        app_id: Optional[str] = None
    ) -> Dict[str, Dict[str, int]]:
        """
        Get filter counts from mart table (fast).
        Uses last_30_days_count to match Phase 1 default filter.
        """
        from app.core.mysql_client import get_mysql_client
        mysql = get_mysql_client()
        
        # App counts (filtered by dept if specified)
        if dept_code and dept_code != 'ALL':
            app_sql = """
                SELECT app_id, SUM(last_30_days_count) as count
                FROM mart_dept_review_filter_counts
                WHERE dept_code = %s
                GROUP BY app_id
            """
            app_rows = mysql.execute_all(app_sql, (dept_code,))
        else:
            app_sql = """
                SELECT app_id, SUM(last_30_days_count) as count
                FROM mart_dept_review_filter_counts
                GROUP BY app_id
            """
            app_rows = mysql.execute_all(app_sql)
        
        # Dept counts (filtered by app if specified)
        if app_id:
            dept_sql = """
                SELECT dept_code, last_30_days_count as count
                FROM mart_dept_review_filter_counts
                WHERE app_id = %s
            """
            dept_rows = mysql.execute_all(dept_sql, (app_id,))
        else:
            dept_sql = """
                SELECT dept_code, SUM(last_30_days_count) as count
                FROM mart_dept_review_filter_counts
                GROUP BY dept_code
            """
            dept_rows = mysql.execute_all(dept_sql)
        
        return {
            "app_counts": {row['app_id']: row['count'] for row in app_rows},
            "dept_counts": {row['dept_code']: row['count'] for row in dept_rows}
        }

    def get_app_rankings_sync(
        self, 
        days: int = 30, 
        limit: int = 5,
        year: Optional[int] = None,
        category: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get top and bottom ranked apps (Synchronous)."""
        client = self._os.sync_client
        
        if year:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
        else:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        
        query = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "review_date": {
                                    "gte": start_date.isoformat(),
                                    "lte": end_date.isoformat()
                                }
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "apps": {
                    "terms": {
                        "field": "app_id",  # Changed from package_id to app_id
                        "size": 100
                    },
                    "aggs": {
                        "avg_rating": {
                            "avg": {
                                "field": "rating"
                            }
                        }
                    }
                }
            }
        }
        
        # Category filter
        if category and category != '0':
            category_map = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}
            group_code = category_map.get(category)
            if group_code:
                from app.services.app_service import get_app_service
                app_service = get_app_service()
                apps = app_service.get_apps_by_group(group_code)
                app_ids = [app['package_id'] for app in apps]
                if app_ids:
                    query["query"]["bool"]["filter"].append({"terms": {"app_id": app_ids}})
                else:
                    query["query"]["bool"]["filter"].append({"term": {"app_id": "NON_EXISTENT"}})
        
        response = client.search(body=query, index=self._index)
        buckets = response['aggregations']['apps']['buckets']
        
        # Get app metadata for group names
        from app.services.app_service import get_app_service
        from app.services.category_service import get_category_service
        
        app_service = get_app_service()
        category_service = get_category_service()
        all_apps = app_service.get_all_apps()
        
        # Create app_id->metadata mapping (app_id is the field name in OpenSearch)
        app_map = {app['package_id']: app for app in all_apps}
        
        apps_data = []
        for bucket in buckets:
            app_id = bucket['key']  # This is the app_id from OpenSearch
            app_meta = app_map.get(app_id, {})
            group_code = app_meta.get('group_code', 'unknown')
            group_korean = category_service.GROUP_CODE_KOREAN_NAMES.get(group_code, group_code)
            
            apps_data.append({
                'name': app_meta.get('company_name', app_id),
                'reviews': bucket['doc_count'],
                'score': bucket['avg_rating']['value'],
                'group': group_korean
            })
        
        apps_data = [app for app in apps_data if app['reviews'] >= 1]
        sorted_apps = sorted(apps_data, key=lambda x: x['score'] if x['score'] else 0, reverse=True)
        
        # Return top 10 for top and bottom
        return {
            'top': sorted_apps[:10],
            'bottom': sorted_apps[-10:][::-1] if len(sorted_apps) >= 10 else []
        }

    def _get_all_time_from_mart(self, category: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Fetch aggregated yearly stats from mart_app_stats_yearly for All Time view.
        """
        mysql = get_mysql_client()
        
        # Fetch directly from yearly mart table
        sql = """
            SELECT app_id, year, total_reviews, avg_rating
            FROM mart_app_stats_yearly
            ORDER BY year ASC
        """
        
        rows = mysql.execute_all(sql)
        if not rows:
            return None
            
        # Get app info
        from app.services.app_service import get_app_service
        app_service = get_app_service()
        all_apps = app_service.get_all_apps()
        app_map = {app['package_id']: app for app in all_apps}
        
        years = sorted(list(set(row['year'] for row in rows)))
        series_data = []
        
        for app_id, app_meta in app_map.items():
            app_rows = [r for r in rows if r['app_id'] == app_id]
            if not app_rows:
                continue
                
            group_code = app_meta.get('group_code')
            if category and category != '0':
                target_group = {'1': 'banks', '2': 'cards', '3': 'fintech', '4': 'securities'}.get(category)
                if group_code != target_group:
                    continue
            
            data_points = []
            for y in years:
                row = next((r for r in app_rows if r['year'] == y), None)
                if row:
                    val = row['avg_rating']
                    data_points.append(float(val) if val else 0.0)
                else:
                    data_points.append(0.0)
            
            series_data.append({
                'name': app_meta.get('company_name', app_id),
                'data': data_points,
                'category': group_code
            })
            
        return {
            'series': series_data,
            'dates': [f"{y}-01-01" for y in years]
        }

    def _get_from_mart(self, year: int, category: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Layer 1: Fetch aggregated stats from Mart table.
        """
        mysql = get_mysql_client()
        
        # Fetch all data for the year
        sql = """
            SELECT app_id, month, total_reviews, avg_rating
            FROM mart_app_stats_monthly
            WHERE year = %s
            ORDER BY month ASC
        """
        rows = mysql.execute_all(sql, (year,))
        
        if not rows:
            return None

        # Filter out future months if querying current year
        current_date = datetime.now()
        if year == current_date.year:
            rows = [r for r in rows if r['month'] <= current_date.month]
            
        # Get app info
        from app.services.app_service import get_app_service
        app_service = get_app_service()
        all_apps = app_service.get_all_apps()
        app_map = {app['package_id']: app for app in all_apps}
        
        series_data = []
        months = sorted(list(set(row['month'] for row in rows)))
        date_labels = [f"{year}-{m:02d}" for m in months]
        
        category_map = {
            '1': 'banks',
            '2': 'cards',
            '3': 'fintech',
            '4': 'securities'
        }
        
        if category and category != '0':
            # Specific category: Show apps
            target_group = category_map.get(category)
            if not target_group:
                return None
                
            # Filter apps by that category
            target_apps = [app['package_id'] for app in all_apps if app.get('group_code') == target_group]
            
            for app_id in target_apps:
                app_rows = [r for r in rows if r['app_id'] == app_id]
                if not app_rows:
                    continue
                    
                data_points = []
                for m in months:
                    row = next((r for r in app_rows if r['month'] == m), None)
                    data_points.append(row['avg_rating'] if row else 0)
                
                app_name = app_map.get(app_id, {}).get('company_name', app_id)
                series_data.append({
                    'name': app_name,
                    'data': data_points,
                    'category': target_group
                })
        else:
            # All categories: Show category averages
            group_codes = ['banks', 'cards', 'fintech', 'securities']
            
            for group in group_codes:
                # Find apps in this group
                group_apps = {app['package_id'] for app in all_apps if app.get('group_code') == group}
                
                # Filter rows for this group
                group_rows = [r for r in rows if r['app_id'] in group_apps]
                
                if not group_rows:
                    continue
                
                data_points = []
                for m in months:
                    month_rows = [r for r in group_rows if r['month'] == m]
                    if not month_rows:
                        data_points.append(0)
                        continue
                        
                    total_reviews = sum(r['total_reviews'] for r in month_rows)
                    if total_reviews > 0:
                        weighted_sum = sum(r['total_reviews'] * r['avg_rating'] for r in month_rows)
                        avg = weighted_sum / total_reviews
                    else:
                        avg = 0
                    data_points.append(round(avg, 2))
                
                series_data.append({
                    'name': group.capitalize(),
                    'data': data_points,
                    'dates': date_labels
                })
                
        if not series_data:
            return None
            
        return {
            'series': series_data,
            'dates': date_labels
        }

    def get_dashboard_stats_layered(
        self,
        year: Optional[int] = None,
        days: int = 30,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get dashboard stats using 3-layer strategy.
        Layer 1: Raw (OpenSearch)
        Layer 2: Mart (MariaDB)
        Layer 3: Fallback (Default)
        """
        # Layer 1: Raw (OpenSearch)
        try:
            # Calculate dates for Raw layer
            # Cap end_date at current time to avoid showing future dates with 0 values
            current_time = datetime.utcnow()
            end_date = current_time
            
            if year:
                start_date = datetime(year, 1, 1)
                year_end = datetime(year, 12, 31, 23, 59, 59)
                # Use the earlier of year_end or current_time
                end_date = min(year_end, current_time) if year == current_time.year else year_end
            else:
                start_date = end_date - timedelta(days=days)
                # The interval logic for `aggregate_sentiment_by_category` is handled within that method.
                # No need to set `interval` here.
            data = self.aggregate_sentiment_by_category(
                category=category,
                start_date=start_date,
                end_date=end_date,
                interval="month" if year else None
            )
            
            # Check if data is empty
            if data and data.get('series'):
                data['meta'] = {'source': 'raw'}
                return data
        except Exception as e:
            logger.error(f"Layer 1 (Raw) failed: {e}")

        # Layer 2: Mart (MariaDB)
        if year:
            try:
                data = self._get_from_mart(year, category)
                if data:
                    data['meta'] = {'source': 'mart'}
                    return data
            except Exception as e:
                logger.error(f"Layer 2 (Mart) failed: {e}")
        else:
            # All Time View: Try to get aggregated yearly stats from Mart
            try:
                data = self._get_all_time_from_mart(category)
                if data:
                    data['meta'] = {'source': 'mart'}
                    return data
            except Exception as e:
                logger.error(f"Layer 2 (Mart All Time) failed: {e}")
            
        # Layer 3: Fallback
        return {
            'series': [],
            'dates': [],
            'meta': {'source': 'fallback'}
        }

    def aggregate_sentiment_by_category(
        self,
        category: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: int = 30,
        interval: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aggregate sentiment data by category/group for multi-line chart.
        
        Args:
            category: Category filter ('1'=banks, '2'=cards, '3'=fintech, etc). If None or '0', shows all categories.
            start_date: Start date for filtering
            end_date: End date for filtering
            days: Number of days to look back if dates not provided
        
        Returns:
            Dict with 'series' array containing data for each category/app and 'dates' array
        """
        client = self._os.sync_client
        
        # Calculate date range
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        # Determine interval
        if not interval:
            interval = "day"
            delta_days = (end_date - start_date).days
            if delta_days > 400:
                interval = "year"
            elif delta_days > 360:
                interval = "month"
            elif delta_days > 90:
                interval = "week"
        
        # Map category number to group_code
        category_map = {
            '1': 'banks',
            '2': 'cards',
            '3': 'fintech',
            '4': 'securities'
        }
        
        # Get services
        from app.services.app_service import get_app_service
        from app.services.category_service import get_category_service
        
        app_service = get_app_service()
        category_service = get_category_service()
        all_apps = app_service.get_all_apps()
        
        series_data = []
        
        if category and category != '0':
            # Single category - show individual apps
            group_code = category_map.get(category)
            if group_code:
                category_apps = [app for app in all_apps if app.get('group_code') == group_code]
                
                for app in category_apps:  # Show all apps in category
                    package_id = app.get('package_id')
                    if not package_id:
                        continue
                    
                    query = {
                        "size": 0,
                        "query": {
                            "bool": {
                                "must": [
                                    {"range": {"review_date": {
                                        "gte": start_date.isoformat(),
                                        "lte": end_date.isoformat()
                                    }}},
                                    {"term": {"app_id": package_id}}
                                ]
                            }
                        },
                        "aggs": {
                            "over_time": {
                                "date_histogram": {
                                    "field": "review_date",
                                    "calendar_interval": interval,
                                    "min_doc_count": 0,
                                    "extended_bounds": {
                                        "min": start_date.isoformat(),
                                        "max": end_date.isoformat()
                                    }
                                },
                                "aggs": {
                                    "avg_rating": {"avg": {"field": "rating"}}
                                }
                            }
                        }
                    }
                    
                    try:
                        result = client.search(body=query, index=self._index)
                        buckets = result['aggregations']['over_time']['buckets']
                        
                        logger.info(f"App {package_id}: found {len(buckets)} buckets, doc_count check: {[b.get('doc_count', 0) for b in buckets[:3]]}")
                        
                        if buckets and any(b.get('doc_count', 0) > 0 for b in buckets):
                            series_data.append({
                                'name': app.get('company_name', package_id),
                                'data': [b['avg_rating']['value'] if b.get('avg_rating') and b['avg_rating']['value'] else 0 for b in buckets],
                                'dates': [b['key_as_string'] for b in buckets]
                            })
                            logger.info(f"Added series for {app.get('company_name', package_id)}: {len(buckets)} data points")
                    except Exception as e:
                        logger.error(f"Error aggregating for app {package_id}: {e}")
                        continue
        else:
            # All categories - show category averages
            group_codes = ['banks', 'cards', 'fintech', 'securities']
            
            logger.info(f"Aggregating for all categories: {group_codes}")
            
            for group_code in group_codes:
                category_apps = [app for app in all_apps if app.get('group_code') == group_code]
                package_ids = [app.get('package_id') for app in category_apps if app.get('package_id')]
                
                logger.info(f"Category {group_code}: found {len(package_ids)} apps")
                
                if not package_ids:
                    continue
                
                query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {"range": {"review_date": {
                                    "gte": start_date.isoformat(),
                                    "lte": end_date.isoformat()
                                }}},
                                {"terms": {"app_id": package_ids}}
                            ]
                        }
                    },
                    "aggs": {
                        "over_time": {
                            "date_histogram": {
                                "field": "review_date",
                                "calendar_interval": interval,
                                "min_doc_count": 0,
                                "extended_bounds": {
                                    "min": start_date.isoformat(),
                                    "max": end_date.isoformat()
                                }
                            },
                            "aggs": {
                                "avg_rating": {"avg": {"field": "rating"}}
                            }
                        }
                    }
                }
                
                try:
                    result = client.search(body=query, index=self._index)
                    buckets = result['aggregations']['over_time']['buckets']
                    total_docs = sum(b.get('doc_count', 0) for b in buckets)
                    
                    logger.info(f"Category {group_code}: {len(buckets)} buckets, total docs: {total_docs}")
                    
                    if buckets and any(b.get('doc_count', 0) > 0 for b in buckets):
                        korean_name = category_service.GROUP_CODE_KOREAN_NAMES.get(group_code, group_code)
                        series_data.append({
                            'name': korean_name,
                            'data': [b['avg_rating']['value'] if b.get('avg_rating') and b['avg_rating']['value'] else 0 for b in buckets],
                            'dates': [b['key_as_string'] for b in buckets]
                        })
                        logger.info(f"Added series for category {korean_name}: {len(buckets)} data points")
                except Exception as e:
                    logger.error(f"Error aggregating for category {group_code}: {e}")
                    continue
        
        logger.info(f"Total series collected: {len(series_data)}")
        common_dates = series_data[0]['dates'] if series_data else []
        
        return {
            'series': series_data,
            'dates': common_dates
        }



# Singleton instance
_review_service: Optional[ReviewService] = None


def get_review_service() -> ReviewService:
    """Get singleton ReviewService instance."""
    global _review_service
    if _review_service is None:
        _review_service = ReviewService()
    return _review_service
    async def get_app_rankings(self, days: int = 30, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get top and bottom ranked apps based on average rating.
        
        Args:
            days: Number of days to look back
            limit: Number of apps to return
            
        Returns:
            Dictionary with 'top' and 'bottom' lists
        """
        try:
            client = await self._get_client()
            
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            query = {
                "size": 0,
                "query": {
                    "range": {
                        "review_date": {
                            "gte": start_date.isoformat(),
                            "lte": end_date.isoformat()
                        }
                    }
                },
                "aggs": {
                    "apps": {
                        "terms": {
                            "field": "app_name",
                            "size": 100  # Get enough apps to sort
                        },
                        "aggs": {
                            "avg_rating": {
                                "avg": {
                                    "field": "rating"
                                }
                            }
                        }
                    }
                }
            }
            
            response = await client.search(
                body=query,
                index=REVIEW_INDEX
            )
            
            buckets = response['aggregations']['apps']['buckets']
            
            # Process buckets
            apps_data = []
            for bucket in buckets:
                apps_data.append({
                    'name': bucket['key'],
                    'reviews': bucket['doc_count'],
                    'score': bucket['avg_rating']['value'],
                    # Placeholder for group/category as we don't have it in index yet
                    'group': '금융' 
                })
            
            # Sort by score
            # Filter out apps with very few reviews to avoid noise? (e.g. < 10)
            apps_data = [app for app in apps_data if app['reviews'] >= 1]
            
            sorted_apps = sorted(apps_data, key=lambda x: x['score'] if x['score'] else 0, reverse=True)
            
            return {
                'top': sorted_apps[:limit],
                'bottom': sorted_apps[-limit:][::-1] if sorted_apps else []
            }
            
        except Exception as e:
            logger.error(f"Error getting app rankings: {e}")
            return {'top': [], 'bottom': []}
