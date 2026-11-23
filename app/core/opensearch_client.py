"""
OpenSearch client with SSL verification skip and authentication support.
Handles connection pooling and provides async interface.
"""

import logging
from typing import Dict, List, Any, Optional
from functools import lru_cache
from opensearchpy import OpenSearch, AsyncOpenSearch
from opensearchpy.exceptions import OpenSearchException
import urllib3

from app.config.settings import get_settings

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """
    OpenSearch client wrapper with SSL skip and authentication.
    Supports both sync and async operations.
    """

    def __init__(self):
        self._settings = get_settings().opensearch
        self._sync_client: Optional[OpenSearch] = None
        self._async_client: Optional[AsyncOpenSearch] = None

    def _get_connection_params(self) -> Dict[str, Any]:
        """Build connection parameters from settings."""
        return {
            'hosts': self._settings.hosts,
            'http_auth': self._settings.http_auth,
            'use_ssl': True,
            'verify_certs': self._settings.ssl_verify,
            'ssl_show_warn': False,
            'ssl_assert_hostname': False,
            'timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True,
        }

    @property
    def sync_client(self) -> OpenSearch:
        """Get synchronous OpenSearch client (lazy initialization)."""
        if self._sync_client is None:
            params = self._get_connection_params()
            self._sync_client = OpenSearch(**params)
            logger.info(f"OpenSearch sync client connected to {self._settings.hosts}")
        return self._sync_client

    @property
    def client(self) -> OpenSearch:
        """Alias of sync_client (used by SimilarReviewService and DedupService)."""
        return self.sync_client

    @property
    def async_client(self) -> AsyncOpenSearch:
        """Get asynchronous OpenSearch client (new instance per call)."""
        # We must create a new client each time because Flask is sync and we use
        # run_async which creates a new event loop for each request.
        # Reusing a client tied to a closed loop causes hanging.
        params = self._get_connection_params()
        return AsyncOpenSearch(**params)

    # -------------------------------------------------------------------------
    # Health and Info
    # -------------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Check cluster health."""
        try:
            return self.sync_client.cluster.health()
        except OpenSearchException as e:
            logger.error(f"OpenSearch health check failed: {e}")
            raise

    async def async_health_check(self) -> Dict[str, Any]:
        """Check cluster health (async)."""
        try:
            return await self.async_client.cluster.health()
        except OpenSearchException as e:
            logger.error(f"OpenSearch async health check failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Index Operations
    # -------------------------------------------------------------------------

    def create_index(self, index: str, mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Create an index with mappings."""
        try:
            if not self.sync_client.indices.exists(index=index):
                response = self.sync_client.indices.create(
                    index=index,
                    body=mappings
                )
                logger.info(f"Created index: {index}")
                return response
            else:
                logger.info(f"Index already exists: {index}")
                return {"acknowledged": True, "already_exists": True}
        except OpenSearchException as e:
            logger.error(f"Failed to create index {index}: {e}")
            raise

    async def async_create_index(self, index: str, mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Create an index with mappings (async)."""
        try:
            exists = await self.async_client.indices.exists(index=index)
            if not exists:
                response = await self.async_client.indices.create(
                    index=index,
                    body=mappings
                )
                logger.info(f"Created index: {index}")
                return response
            else:
                logger.info(f"Index already exists: {index}")
                return {"acknowledged": True, "already_exists": True}
        except OpenSearchException as e:
            logger.error(f"Failed to create index {index}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Document Operations
    # -------------------------------------------------------------------------

    def index_document(
        self,
        index: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Index a single document."""
        try:
            return self.sync_client.index(
                index=index,
                body=document,
                id=doc_id,
                refresh='wait_for'
            )
        except OpenSearchException as e:
            logger.error(f"Failed to index document: {e}")
            raise

    async def async_index_document(
        self,
        index: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Index a single document (async)."""
        try:
            return await self.async_client.index(
                index=index,
                body=document,
                id=doc_id,
                refresh='wait_for'
            )
        except OpenSearchException as e:
            logger.error(f"Failed to index document: {e}")
            raise

    def bulk_index(
        self,
        index: str,
        documents: List[Dict[str, Any]],
        id_field: str = 'review_id'
    ) -> Dict[str, Any]:
        """Bulk index documents."""
        try:
            actions = []
            for doc in documents:
                action = {
                    "index": {
                        "_index": index,
                        "_id": doc.get(id_field)
                    }
                }
                actions.append(action)
                actions.append(doc)

            return self.sync_client.bulk(body=actions, refresh='wait_for')
        except OpenSearchException as e:
            logger.error(f"Bulk index failed: {e}")
            raise

    async def async_bulk_index(
        self,
        index: str,
        documents: List[Dict[str, Any]],
        id_field: str = 'review_id'
    ) -> Dict[str, Any]:
        """Bulk index documents (async)."""
        try:
            actions = []
            for doc in documents:
                action = {
                    "index": {
                        "_index": index,
                        "_id": doc.get(id_field)
                    }
                }
                actions.append(action)
                actions.append(doc)

            return await self.async_client.bulk(body=actions, refresh='wait_for')
        except OpenSearchException as e:
            logger.error(f"Bulk index failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    def search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 10,
        from_: int = 0
    ) -> Dict[str, Any]:
        """Execute a search query."""
        try:
            return self.sync_client.search(
                index=index,
                body=query,
                size=size,
                from_=from_
            )
        except OpenSearchException as e:
            logger.error(f"Search failed: {e}")
            raise

    async def async_search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 10,
        from_: int = 0
    ) -> Dict[str, Any]:
        """Execute a search query (async)."""
        try:
            return await self.async_client.search(
                index=index,
                body=query,
                size=size,
                from_=from_
            )
        except OpenSearchException as e:
            logger.error(f"Search failed: {e}")
            raise

    def knn_search(
        self,
        index: str,
        vector: List[float],
        field: str = 'embedding',
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a KNN vector search."""
        query = {
            "size": k,
            "query": {
                "knn": {
                    field: {
                        "vector": vector,
                        "k": k
                    }
                }
            }
        }

        if filters:
            query["query"] = {
                "bool": {
                    "must": [query["query"]],
                    "filter": filters
                }
            }

        return self.search(index=index, query=query, size=k)

    async def async_knn_search(
        self,
        index: str,
        vector: List[float],
        field: str = 'embedding',
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a KNN vector search (async)."""
        query = {
            "size": k,
            "query": {
                "knn": {
                    field: {
                        "vector": vector,
                        "k": k
                    }
                }
            }
        }

        if filters:
            query["query"] = {
                "bool": {
                    "must": [query["query"]],
                    "filter": filters
                }
            }

        return await self.async_search(index=index, query=query, size=k)

    # -------------------------------------------------------------------------
    # Aggregation Operations
    # -------------------------------------------------------------------------

    def aggregate(
        self,
        index: str,
        aggs: Dict[str, Any],
        query: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute an aggregation query."""
        body = {"size": 0, "aggs": aggs}
        if query:
            body["query"] = query

        return self.search(index=index, query=body)

    async def async_aggregate(
        self,
        index: str,
        aggs: Dict[str, Any],
        query: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute an aggregation query (async)."""
        body = {"size": 0, "aggs": aggs}
        if query:
            body["query"] = query

        return await self.async_search(index=index, query=body)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def close(self):
        """Close sync client connections."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    async def async_close(self):
        """Close async client connections."""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None


# Singleton instance
_opensearch_client: Optional[OpenSearchClient] = None


def get_opensearch_client() -> OpenSearchClient:
    """Get singleton OpenSearch client instance."""
    global _opensearch_client
    if _opensearch_client is None:
        _opensearch_client = OpenSearchClient()
    return _opensearch_client
