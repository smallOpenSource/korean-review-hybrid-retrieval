"""
BGE Rerank Service with API and Local fallback.
Uses bge-reranker-v2-m3 for reranking search results in RAG pipeline.

Fallback order:
1. BGE Rerank API (with Bearer token)
2. Local bge-reranker-v2-m3 (CPU)

Usage in RAG:
1. Vector search returns Top-K candidates (e.g., k=100)
2. Reranker reorders candidates by relevance
3. Return Top-N results (e.g., n=10)
"""

import logging
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
import aiohttp

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result of rerank operation."""
    index: int  # Original index in input list
    score: float  # Relevance score
    text: str  # Document text


@dataclass
class RerankResponse:
    """Response from rerank operation."""
    results: List[RerankResult]
    model: str
    source: str  # "api" or "local"
    latency_ms: int


class BaseRerankClient(ABC):
    """Abstract base class for rerank clients."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> RerankResponse:
        """Rerank documents by relevance to query."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this client is available."""
        pass


class BGERerankAPIClient(BaseRerankClient):
    """BGE Rerank API client with Bearer token authentication."""

    def __init__(self):
        self._settings = get_settings().bge
        self._session: Optional[aiohttp.ClientSession] = None

    def is_available(self) -> bool:
        """Check if API is configured."""
        return bool(self._settings.rerank_api_url and self._settings.rerank_api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.rerank_api_key}"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> RerankResponse:
        """Rerank documents via API."""
        start_time = time.monotonic()
        session = await self._get_session()

        payload = {
            "query": query,
            "documents": documents,
            "model": self._settings.rerank_model
        }
        if top_n:
            payload["top_n"] = top_n

        try:
            async with session.post(
                self._settings.rerank_api_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                response.raise_for_status()
                data = await response.json()

            latency_ms = int((time.monotonic() - start_time) * 1000)

            results = [
                RerankResult(
                    index=item["index"],
                    score=item["score"],
                    text=documents[item["index"]]
                )
                for item in data["results"]
            ]

            return RerankResponse(
                results=results,
                model=self._settings.rerank_model,
                source="api",
                latency_ms=latency_ms
            )
        except Exception as e:
            logger.error(f"BGE Rerank API failed: {e}")
            raise

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()


class BGERerankLocalClient(BaseRerankClient):
    """Local BGE rerank client using FlagEmbedding (CPU)."""

    def __init__(self):
        self._settings = get_settings().bge
        self._model = None
        self._initialized = False

    def is_available(self) -> bool:
        """Local model is always available as fallback."""
        return True

    def _initialize(self):
        """Lazy initialization of the model."""
        if not self._initialized:
            try:
                from FlagEmbedding import FlagReranker
                import torch

                logger.info(f"Loading local rerank model: {self._settings.local_rerank_model}")

                # Determine device
                device = self._settings.local_device
                use_fp16 = device != "cpu"

                self._model = FlagReranker(
                    self._settings.local_rerank_model,
                    use_fp16=use_fp16,
                    device=device
                )

                self._initialized = True
                logger.info(f"Local rerank model loaded on {device}")

            except ImportError:
                logger.error("FlagEmbedding not installed. Run: pip install FlagEmbedding")
                raise

            except Exception as e:
                logger.error(f"Failed to load local rerank model: {e}")
                raise

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> RerankResponse:
        """Rerank documents using local model."""
        start_time = time.monotonic()

        # Run in thread pool to avoid blocking
        scores = await asyncio.to_thread(self._rerank_sync, query, documents)

        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Create results with original indices and scores
        indexed_scores = [(i, score, doc) for i, (score, doc) in enumerate(zip(scores, documents))]
        # Sort by score descending
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        # Apply top_n if specified
        if top_n:
            indexed_scores = indexed_scores[:top_n]

        results = [
            RerankResult(
                index=idx,
                score=float(score),
                text=doc
            )
            for idx, score, doc in indexed_scores
        ]

        return RerankResponse(
            results=results,
            model=self._settings.local_rerank_model,
            source="local",
            latency_ms=latency_ms
        )

    def _rerank_sync(self, query: str, documents: List[str]) -> List[float]:
        """Synchronous reranking."""
        self._initialize()

        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]

        # Compute scores
        scores = self._model.compute_score(pairs, normalize=True)

        # Ensure scores is a list
        if not isinstance(scores, list):
            scores = [scores]

        return scores


class RerankService:
    """
    Unified Rerank Service with automatic fallback.

    Uses bge-reranker-v2-m3 for reranking RAG search results.

    Fallback order:
    1. BGE Rerank API (fast, requires network)
    2. Local bge-reranker-v2-m3 (CPU, always available)
    """

    def __init__(self):
        self._api_client = BGERerankAPIClient()
        self._local_client = BGERerankLocalClient()

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> RerankResponse:
        """
        Rerank documents by relevance to query with automatic fallback.

        Args:
            query: Search query
            documents: List of document texts to rerank
            top_n: Return only top N results (optional)

        Returns:
            RerankResponse with sorted results
        """
        if not documents:
            return RerankResponse(
                results=[],
                model="none",
                source="none",
                latency_ms=0
            )

        # Try API first
        if self._api_client.is_available():
            try:
                result = await self._api_client.rerank(query, documents, top_n)
                logger.debug(f"Rerank via API in {result.latency_ms}ms for {len(documents)} docs")
                return result
            except Exception as e:
                logger.warning(f"API rerank failed, falling back to local: {e}")

        # Fallback to local
        try:
            result = await self._local_client.rerank(query, documents, top_n)
            logger.debug(f"Rerank locally in {result.latency_ms}ms for {len(documents)} docs")
            return result
        except Exception as e:
            logger.error(f"Local rerank also failed: {e}")
            raise RuntimeError(f"All rerank methods failed: {e}")

    async def rerank_with_metadata(
        self,
        query: str,
        documents: List[dict],
        text_field: str = "content",
        top_n: Optional[int] = None
    ) -> List[dict]:
        """
        Rerank documents with metadata preservation.

        Args:
            query: Search query
            documents: List of document dicts with text and metadata
            text_field: Field name containing the text to rerank
            top_n: Return only top N results

        Returns:
            List of document dicts sorted by relevance, with 'rerank_score' added
        """
        if not documents:
            return []

        # Extract texts
        texts = [doc.get(text_field, "") for doc in documents]

        # Rerank
        response = await self.rerank(query, texts, top_n)

        # Map results back to documents with scores
        reranked_docs = []
        for result in response.results:
            doc = documents[result.index].copy()
            doc["rerank_score"] = result.score
            reranked_docs.append(doc)

        return reranked_docs

    async def close(self):
        """Cleanup resources."""
        await self._api_client.close()


# Singleton instance
_rerank_service: Optional[RerankService] = None


def get_rerank_service() -> RerankService:
    """Get singleton RerankService instance."""
    global _rerank_service
    if _rerank_service is None:
        _rerank_service = RerankService()
    return _rerank_service
