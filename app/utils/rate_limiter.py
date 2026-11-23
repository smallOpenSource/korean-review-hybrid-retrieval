"""
API endpoint rate limiter for Flask routes

Provides per-IP and per-user rate limiting for API endpoints
to prevent abuse and ensure fair resource usage.

Created: 2025-12-31 (Session 2: Input Validation Infrastructure)
"""

from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import logging

from app.core.redis_client import get_redis_client, RedisClient

logger = logging.getLogger(__name__)


class APIRateLimitExceeded(Exception):
    """API endpoint rate limit exceeded"""

    def __init__(self, limit: int, window: int, retry_after: int):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window}s. "
            f"Retry after {retry_after}s"
        )


class APIRateLimiter:
    """
    Redis-based rate limiter for API endpoints
    Supports per-IP and per-user rate limiting
    """

    KEY_PREFIX = "api_rate_limit"

    def __init__(self, redis_client: Optional[RedisClient] = None):
        self._redis = redis_client or get_redis_client()

    def _get_client_identifier(self) -> str:
        """Get unique identifier for current request (IP or user_id)"""
        # Try to get user_id from request context (if JWT is used)
        user_id = getattr(request, 'user_id', None)
        if user_id:
            return f"user:{user_id}"

        # Fallback to IP address
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
        else:
            ip = request.remote_addr or 'unknown'

        return f"ip:{ip}"

    def _get_redis_key(self, identifier: str, endpoint: str, window: int) -> str:
        """Generate Redis key for rate limit counter"""
        timestamp = int(datetime.now().timestamp() / window) * window
        return f"{self.KEY_PREFIX}:{endpoint}:{identifier}:{timestamp}"

    def check_limit(
        self,
        endpoint: str,
        limit: int,
        window: int
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit

        Args:
            endpoint: API endpoint identifier
            limit: Maximum requests allowed
            window: Time window in seconds

        Returns:
            (allowed, current_count, retry_after)
        """
        identifier = self._get_client_identifier()
        key = self._get_redis_key(identifier, endpoint, window)

        try:
            # Increment counter
            current = self._redis.incr(key)

            # Set expiration on first request
            if current == 1:
                self._redis.expire(key, window)

            if current <= limit:
                return True, current, 0

            # Calculate retry_after
            ttl = self._redis.ttl(key)
            retry_after = ttl if ttl > 0 else window

            return False, current, retry_after

        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}")
            # Fail open (allow request) on Redis errors
            return True, 0, 0

    def reset_limit(self, endpoint: str, identifier: Optional[str] = None):
        """Reset rate limit for specific identifier (admin function)"""
        if identifier is None:
            identifier = self._get_client_identifier()

        pattern = f"{self.KEY_PREFIX}:{endpoint}:{identifier}:*"
        try:
            keys = self._redis.keys(pattern)
            if keys:
                self._redis.delete(*keys)
                logger.info(f"Reset rate limit for {identifier} on {endpoint}")
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")


def rate_limit(limit: int, window: int = 60, endpoint: Optional[str] = None):
    """
    Rate limiting decorator for Flask routes

    Args:
        limit: Maximum requests allowed
        window: Time window in seconds (default: 60)
        endpoint: Custom endpoint identifier (default: use route path)

    Usage:
        @api_bp.route('/search')
        @rate_limit(limit=100, window=60)  # 100 requests per minute
        def search_endpoint():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Use route path as endpoint identifier
            endpoint_id = endpoint or request.endpoint or request.path

            rate_limiter = get_api_rate_limiter()
            allowed, current, retry_after = rate_limiter.check_limit(
                endpoint=endpoint_id,
                limit=limit,
                window=window
            )

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for {rate_limiter._get_client_identifier()} "
                    f"on {endpoint_id}: {current}/{limit}"
                )
                return jsonify({
                    'status': 'error',
                    'error_code': 'RATE_LIMIT_EXCEEDED',
                    'message': f'Rate limit exceeded: {limit} requests per {window}s',
                    'details': {
                        'limit': limit,
                        'window': window,
                        'current': current,
                        'retry_after': retry_after
                    }
                }), 429

            # Add rate limit headers to response
            response = fn(*args, **kwargs)

            # Handle both Response objects and tuples
            if isinstance(response, tuple):
                resp_obj, status_code = response[0], response[1] if len(response) > 1 else 200
            else:
                resp_obj, status_code = response, 200

            # Add headers if response is a Response object
            if hasattr(resp_obj, 'headers'):
                resp_obj.headers['X-RateLimit-Limit'] = str(limit)
                resp_obj.headers['X-RateLimit-Remaining'] = str(max(0, limit - current))
                resp_obj.headers['X-RateLimit-Reset'] = str(int(datetime.now().timestamp()) + window)

            return (resp_obj, status_code) if isinstance(response, tuple) else resp_obj

        return wrapper
    return decorator


# Singleton instance
_api_rate_limiter: Optional[APIRateLimiter] = None


def get_api_rate_limiter() -> APIRateLimiter:
    """Get singleton API rate limiter instance"""
    global _api_rate_limiter
    if _api_rate_limiter is None:
        _api_rate_limiter = APIRateLimiter()
    return _api_rate_limiter
