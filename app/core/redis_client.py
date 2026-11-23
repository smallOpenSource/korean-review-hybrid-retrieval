"""
Redis client with Sentinel support for high availability.
Automatically discovers and connects to the master node.
"""

import logging
from typing import Optional, Any, List
from functools import lru_cache
import redis
from redis.sentinel import Sentinel
from redis.exceptions import RedisError

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client with Sentinel support.
    Automatically connects to master through Sentinel.
    """

    def __init__(self):
        self._settings = get_settings().redis
        self._sentinel: Optional[Sentinel] = None
        self._master: Optional[redis.Redis] = None

    def _get_sentinel(self) -> Sentinel:
        """Get or create Sentinel instance."""
        if self._sentinel is None:
            sentinel_kwargs = {
                'socket_timeout': self._settings.socket_timeout,
            }
            if self._settings.password:
                sentinel_kwargs['password'] = self._settings.password

            self._sentinel = Sentinel(
                sentinels=self._settings.sentinel_list,
                sentinel_kwargs=sentinel_kwargs
            )
            logger.info(f"Redis Sentinel connected to {self._settings.sentinel_list}")

        return self._sentinel

    @property
    def master(self) -> redis.Redis:
        """Get Redis master connection through Sentinel."""
        if self._master is None:
            sentinel = self._get_sentinel()

            master_kwargs = {
                'socket_timeout': self._settings.socket_timeout,
                'db': self._settings.db,
                'decode_responses': True,
            }
            if self._settings.password:
                master_kwargs['password'] = self._settings.password

            self._master = sentinel.master_for(
                self._settings.master_name,
                **master_kwargs
            )
            logger.info(f"Redis master '{self._settings.master_name}' connection established")

        return self._master

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            return self.master.ping()
        except RedisError as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def get_master_info(self) -> dict:
        """Get information about the current master."""
        try:
            sentinel = self._get_sentinel()
            master_addr = sentinel.discover_master(self._settings.master_name)
            return {
                "master_name": self._settings.master_name,
                "host": master_addr[0],
                "port": master_addr[1],
                "connected": self.health_check()
            }
        except RedisError as e:
            logger.error(f"Failed to get master info: {e}")
            raise

    # -------------------------------------------------------------------------
    # Basic Operations
    # -------------------------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            return self.master.get(key)
        except RedisError as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            raise

    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """Set key-value pair with optional expiration."""
        try:
            return self.master.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
        except RedisError as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            raise

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        try:
            return self.master.delete(*keys)
        except RedisError as e:
            logger.error(f"Redis DELETE failed: {e}")
            raise

    def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        try:
            return self.master.exists(*keys)
        except RedisError as e:
            logger.error(f"Redis EXISTS failed: {e}")
            raise

    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        try:
            return self.master.expire(key, seconds)
        except RedisError as e:
            logger.error(f"Redis EXPIRE failed for key {key}: {e}")
            raise

    def ttl(self, key: str) -> int:
        """Get TTL of a key."""
        try:
            return self.master.ttl(key)
        except RedisError as e:
            logger.error(f"Redis TTL failed for key {key}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Counter Operations (for Rate Limiting)
    # -------------------------------------------------------------------------

    def incr(self, key: str) -> int:
        """Increment counter."""
        try:
            return self.master.incr(key)
        except RedisError as e:
            logger.error(f"Redis INCR failed for key {key}: {e}")
            raise

    def incrby(self, key: str, amount: int) -> int:
        """Increment counter by amount."""
        try:
            return self.master.incrby(key, amount)
        except RedisError as e:
            logger.error(f"Redis INCRBY failed for key {key}: {e}")
            raise

    def decr(self, key: str) -> int:
        """Decrement counter."""
        try:
            return self.master.decr(key)
        except RedisError as e:
            logger.error(f"Redis DECR failed for key {key}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Hash Operations
    # -------------------------------------------------------------------------

    def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field value."""
        try:
            return self.master.hget(name, key)
        except RedisError as e:
            logger.error(f"Redis HGET failed: {e}")
            raise

    def hset(self, name: str, key: str = None, value: Any = None, mapping: dict = None) -> int:
        """Set hash field(s)."""
        try:
            return self.master.hset(name, key, value, mapping)
        except RedisError as e:
            logger.error(f"Redis HSET failed: {e}")
            raise

    def hgetall(self, name: str) -> dict:
        """Get all hash fields."""
        try:
            return self.master.hgetall(name)
        except RedisError as e:
            logger.error(f"Redis HGETALL failed: {e}")
            raise

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        """Increment hash field."""
        try:
            return self.master.hincrby(name, key, amount)
        except RedisError as e:
            logger.error(f"Redis HINCRBY failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # List Operations
    # -------------------------------------------------------------------------

    def lpush(self, name: str, *values: Any) -> int:
        """Push values to list head."""
        try:
            return self.master.lpush(name, *values)
        except RedisError as e:
            logger.error(f"Redis LPUSH failed: {e}")
            raise

    def rpush(self, name: str, *values: Any) -> int:
        """Push values to list tail."""
        try:
            return self.master.rpush(name, *values)
        except RedisError as e:
            logger.error(f"Redis RPUSH failed: {e}")
            raise

    def lrange(self, name: str, start: int, end: int) -> List[str]:
        """Get list range."""
        try:
            return self.master.lrange(name, start, end)
        except RedisError as e:
            logger.error(f"Redis LRANGE failed: {e}")
            raise

    def llen(self, name: str) -> int:
        """Get list length."""
        try:
            return self.master.llen(name)
        except RedisError as e:
            logger.error(f"Redis LLEN failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Pipeline Operations
    # -------------------------------------------------------------------------

    def pipeline(self, transaction: bool = True):
        """Get pipeline for batch operations."""
        return self.master.pipeline(transaction=transaction)

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def close(self):
        """Close Redis connections."""
        if self._master:
            self._master.close()
            self._master = None
        if self._sentinel:
            # Sentinel doesn't have a close method, but we can clear it
            self._sentinel = None
        logger.info("Redis connections closed")


# Singleton instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """Get singleton Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
