"""
BGE Embedding Service with API and Local fallback.
Uses bge-m3-ko for Korean-optimized embeddings (1024 dimensions).

Fallback order:
1. BGE API (with Bearer token)
2. Local bge-m3-ko (CPU)

Important: Only bge-m3-ko is used to ensure embedding consistency.
Different embedding models produce incompatible vectors.
"""

import logging
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Union
import aiohttp
import requests as http_requests
import numpy as np

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result from embedding operation."""
    embedding: List[float]
    model: str
    source: str  # "api" or "local"
    dimensions: int
    latency_ms: int
    is_local_model: bool = False

    @property
    def embedding_array(self) -> np.ndarray:
        """Get embedding as numpy array."""
        return np.array(self.embedding)


class BaseEmbeddingClient(ABC):
    """Abstract base class for embedding clients."""

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this client is available."""
        pass


class BGEAPIClient(BaseEmbeddingClient):
    """BGE Embedding API client with Bearer token authentication."""

    def __init__(self):
        self._settings = get_settings().bge
        self._session: Optional[aiohttp.ClientSession] = None

    def is_available(self) -> bool:
        """Check if API is configured."""
        return bool(self._settings.embedding_api_url and self._settings.embedding_api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.embedding_api_key}"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding via API."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Use BGE server format
        payload = {
            "texts": [text],
            "return_dense": True,
            "return_sparse": False,
            "return_colbert_vecs": False
        }

        # Load timeout from centralized settings
        settings = get_settings()
        timeout = aiohttp.ClientTimeout(total=settings.bge_timeouts.embedding)

        try:
            async with session.post(
                self._settings.embedding_api_url,
                json=payload,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()

            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            # Handle multiple response formats:
            # 1. BGE server: dense_embeddings[]
            # 2. Custom: embeddings[]
            # 3. OpenAI: data[].embedding
            if "dense_embeddings" in data:
                embedding = data["dense_embeddings"][0]
            elif "embeddings" in data:
                embedding = data["embeddings"][0]
            elif "data" in data and len(data["data"]) > 0:
                embedding = data["data"][0]["embedding"]
            else:
                raise ValueError(f"Unexpected response format: {list(data.keys())}")

            return EmbeddingResult(
                embedding=embedding,
                model=self._settings.embedding_model,
                source="api",
                dimensions=len(embedding),
                latency_ms=latency_ms,
                is_local_model=False
            )
        except Exception as e:
            logger.error(f"BGE API embedding failed: {e}")
            raise

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts via API."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Use BGE server format
        payload = {
            "texts": texts,
            "return_dense": True,
            "return_sparse": False,
            "return_colbert_vecs": False
        }

        # Load batch timeout from centralized settings
        settings = get_settings()
        timeout_batch = aiohttp.ClientTimeout(total=settings.bge_timeouts.batch)

        try:
            async with session.post(
                self._settings.embedding_api_url,
                json=payload,
                timeout=timeout_batch
            ) as response:
                response.raise_for_status()
                data = await response.json()

            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            # Handle multiple response formats:
            # 1. BGE server: dense_embeddings[]
            # 2. Custom: embeddings[]
            # 3. OpenAI: data[].embedding
            if "dense_embeddings" in data:
                embeddings = data["dense_embeddings"]
            elif "embeddings" in data:
                embeddings = data["embeddings"]
            elif "data" in data:
                embeddings = [item["embedding"] for item in data["data"]]
            else:
                raise ValueError(f"Unexpected response format: {list(data.keys())}")

            return [
                EmbeddingResult(
                    embedding=emb,
                    model=self._settings.embedding_model,
                    source="api",
                    dimensions=len(emb),
                    latency_ms=latency_ms // len(texts),
                    is_local_model=False
                )
                for emb in embeddings
            ]
        except Exception as e:
            logger.error(f"BGE API batch embedding failed: {e}")
            raise

    def embed_sync(self, text: str) -> EmbeddingResult:
        """동기 API 호출 (requests 사용)."""
        start_time = time.monotonic()
        settings = get_settings()

        payload = {
            "texts": [text],
            "return_dense": True,
            "return_sparse": False,
            "return_colbert_vecs": False
        }

        resp = http_requests.post(
            self._settings.embedding_api_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.embedding_api_key}"
            },
            timeout=(3, settings.bge_timeouts.embedding),  # (connect, read)
        )
        resp.raise_for_status()
        data = resp.json()

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if "dense_embeddings" in data:
            embedding = data["dense_embeddings"][0]
        elif "embeddings" in data:
            embedding = data["embeddings"][0]
        elif "data" in data and len(data["data"]) > 0:
            embedding = data["data"][0]["embedding"]
        else:
            raise ValueError(f"Unexpected response format: {list(data.keys())}")

        return EmbeddingResult(
            embedding=embedding,
            model=self._settings.embedding_model,
            source="api",
            dimensions=len(embedding),
            latency_ms=latency_ms,
            is_local_model=False
        )

    def embed_batch_sync(self, texts: List[str]) -> List[EmbeddingResult]:
        """동기 배치 API 호출 (requests 사용). 서브배치 분할로 타임아웃 방지."""
        settings = get_settings()
        all_results: List[EmbeddingResult] = []
        sub_batch_size = self._settings.embed_batch_dop  # .env EMBED_BATCH_DOP (기본값 10)

        for i in range(0, len(texts), sub_batch_size):
            batch = texts[i:i + sub_batch_size]
            start_time = time.monotonic()

            payload = {
                "texts": batch,
                "return_dense": True,
                "return_sparse": False,
                "return_colbert_vecs": False
            }

            resp = http_requests.post(
                self._settings.embedding_api_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._settings.embedding_api_key}"
                },
                timeout=(3, settings.bge_timeouts.embedding),  # (connect, read)
            )
            resp.raise_for_status()
            data = resp.json()

            latency_ms = int((time.monotonic() - start_time) * 1000)

            if "dense_embeddings" in data:
                embeddings = data["dense_embeddings"]
            elif "embeddings" in data:
                embeddings = data["embeddings"]
            elif "data" in data:
                embeddings = [item["embedding"] for item in data["data"]]
            else:
                raise ValueError(f"Unexpected response format: {list(data.keys())}")

            all_results.extend([
                EmbeddingResult(
                    embedding=emb,
                    model=self._settings.embedding_model,
                    source="api",
                    dimensions=len(emb),
                    latency_ms=latency_ms // max(len(batch), 1),
                    is_local_model=False
                )
                for emb in embeddings
            ])

            logger.debug(f"API batch embed {i+1}-{i+len(batch)}/{len(texts)}: {latency_ms}ms")

        return all_results

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()


class BGELocalClient(BaseEmbeddingClient):
    """Local BGE embedding client using sentence-transformers (CPU)."""

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
                from sentence_transformers import SentenceTransformer
                import torch

                logger.info(f"Loading local embedding model: {self._settings.local_embedding_model}")

                self._model = SentenceTransformer(
                    self._settings.local_embedding_model,
                    cache_folder=self._settings.local_model_cache_dir,
                    device=self._settings.local_device
                )

                # Ensure CPU usage if specified
                if self._settings.local_device == "cpu":
                    self._model = self._model.to(torch.device("cpu"))

                self._initialized = True
                logger.info(f"Local embedding model loaded on {self._settings.local_device}")

            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise

            except Exception as e:
                logger.error(f"Failed to load local embedding model: {e}")
                raise

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding using local model."""
        start_time = time.monotonic()

        # Run in thread pool to avoid blocking
        embedding = await asyncio.to_thread(self._embed_sync_internal, text)

        latency_ms = int((time.monotonic() - start_time) * 1000)

        return EmbeddingResult(
            embedding=embedding,
            model=self._settings.local_embedding_model,
            source="local",
            dimensions=len(embedding),
            latency_ms=latency_ms,
            is_local_model=True
        )

    def embed_sync(self, text: str) -> EmbeddingResult:
        """Synchronous embedding generation."""
        start_time = time.monotonic()
        embedding = self._embed_sync_internal(text)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        return EmbeddingResult(
            embedding=embedding,
            model=self._settings.local_embedding_model,
            source="local",
            dimensions=len(embedding),
            latency_ms=latency_ms,
            is_local_model=True
        )

    def _embed_sync_internal(self, text: str) -> List[float]:
        """Internal synchronous embedding generation."""
        self._initialize()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        start_time = time.monotonic()

        # Run in thread pool
        embeddings = await asyncio.to_thread(self._embed_batch_sync_internal, texts)

        latency_ms = int((time.monotonic() - start_time) * 1000)

        return [
            EmbeddingResult(
                embedding=emb,
                model=self._settings.local_embedding_model,
                source="local",
                dimensions=len(emb),
                latency_ms=latency_ms // max(len(texts), 1),
                is_local_model=True
            )
            for emb in embeddings
        ]

    def embed_batch_sync(self, texts: List[str]) -> List[EmbeddingResult]:
        """Synchronous batch embedding generation."""
        start_time = time.monotonic()
        embeddings = self._embed_batch_sync_internal(texts)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        return [
            EmbeddingResult(
                embedding=emb,
                model=self._settings.local_embedding_model,
                source="local",
                dimensions=len(emb),
                latency_ms=latency_ms // max(len(texts), 1),
                is_local_model=True
            )
            for emb in embeddings
        ]

    def _embed_batch_sync_internal(self, texts: List[str]) -> List[List[float]]:
        """Internal synchronous batch embedding generation."""
        self._initialize()
        embeddings = self._model.encode(
            texts,
            batch_size=self._settings.local_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return [emb.tolist() for emb in embeddings]


class EmbeddingService:
    """
    Unified Embedding Service with automatic fallback.

    Uses ONLY bge-m3-ko to ensure embedding consistency.
    Different models produce incompatible vectors.

    Fallback order:
    1. BGE API (fast, requires network)
    2. Local bge-m3-ko (CPU, always available)
    """

    def __init__(self):
        self._api_client = BGEAPIClient()
        self._local_client = BGELocalClient()
        self._settings = get_settings().bge

    async def embed(
        self,
        text: Union[str, List[str]],
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> Union[EmbeddingResult, List[EmbeddingResult]]:
        """
        Generate embedding with automatic fallback.

        Args:
            text: Text or list of texts to embed
            task_type: Embedding task type (for compatibility, not used by BGE)

        Returns:
            EmbeddingResult or list of EmbeddingResult
        """
        single_input = isinstance(text, str)

        if single_input:
            result = await self._embed_single(text)
            return result
        else:
            results = await self._embed_batch(text)
            results = await self._embed_batch(text)
            return results

    def embed_sync(
        self,
        text: Union[str, List[str]],
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> Union[EmbeddingResult, List[EmbeddingResult]]:
        """
        Synchronous embedding generation.
        Fallback: API → Local (async embed()과 동일 전략).
        """
        single_input = isinstance(text, str)

        # API 우선 시도
        if self._api_client.is_available():
            try:
                if single_input:
                    return self._api_client.embed_sync(text)
                else:
                    return self._api_client.embed_batch_sync(text)
            except Exception as e:
                logger.warning(f"API embed_sync failed, falling back to local: {e}")

        # Fallback to local
        if single_input:
            return self._local_client.embed_sync(text)
        else:
            return self._local_client.embed_batch_sync(text)

    async def _embed_single(self, text: str) -> EmbeddingResult:
        """Embed single text with fallback."""
        # Try API first
        if self._api_client.is_available():
            try:
                result = await self._api_client.embed(text)
                logger.debug(f"Embedding generated via API in {result.latency_ms}ms")
                return result
            except Exception as e:
                logger.warning(f"API embedding failed, falling back to local: {e}")

        # Fallback to local
        try:
            result = await self._local_client.embed(text)
            logger.debug(f"Embedding generated locally in {result.latency_ms}ms")
            return result
        except Exception as e:
            logger.error(f"Local embedding also failed: {e}")
            raise RuntimeError(f"All embedding methods failed: {e}")

    async def _embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed multiple texts with fallback."""
        if not texts:
            return []

        # Try API first
        if self._api_client.is_available():
            try:
                results = await self._api_client.embed_batch(texts)
                logger.debug(f"Batch embeddings ({len(texts)}) generated via API")
                return results
            except Exception as e:
                logger.warning(f"API batch embedding failed, falling back to local: {e}")

        # Fallback to local
        try:
            results = await self._local_client.embed_batch(texts)
            logger.debug(f"Batch embeddings ({len(texts)}) generated locally")
            return results
        except Exception as e:
            logger.error(f"Local batch embedding also failed: {e}")
            raise RuntimeError(f"All embedding methods failed: {e}")

    async def embed_for_storage(self, text: str) -> np.ndarray:
        """Generate embedding for document storage."""
        result = await self.embed(text, task_type="RETRIEVAL_DOCUMENT")
        return result.embedding_array

    async def embed_for_query(self, text: str) -> np.ndarray:
        """Generate embedding for search query."""
        result = await self.embed(text, task_type="RETRIEVAL_QUERY")
        return result.embedding_array

    @property
    def dimensions(self) -> int:
        """Get embedding dimensions (1024 for bge-m3-ko)."""
        return self._settings.embedding_dimensions

    async def close(self):
        """Cleanup resources."""
        await self._api_client.close()


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(opensearch_client=None) -> EmbeddingService:
    """Get singleton EmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
