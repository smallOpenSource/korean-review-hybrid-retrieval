"""
Rate Limiter for LLM API calls.
Supports RPM (Requests Per Minute) and RPD (Requests Per Day) limits.
Uses Redis for distributed rate limiting across multiple instances.
"""

import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Callable, Any
from functools import wraps
from datetime import datetime, timedelta

from app.config.settings import get_settings
from app.config.llm_config import get_llm_config, ModelSpec
from app.core.redis_client import get_redis_client, RedisClient

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, model: str, limit_type: str, retry_after: float = None):
        self.model = model
        self.limit_type = limit_type
        self.retry_after = retry_after
        message = f"Rate limit exceeded for {model} ({limit_type})"
        if retry_after:
            message += f". Retry after {retry_after:.1f} seconds"
        super().__init__(message)


@dataclass
class RateLimitStatus:
    """Current rate limit status for a model."""
    model: str
    rpm_limit: int
    rpm_used: int
    rpm_remaining: int
    rpd_limit: int
    rpd_used: int
    rpd_remaining: int
    is_limited: bool
    retry_after: Optional[float] = None


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.
    Provides smooth rate limiting with burst capability.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens added per second
            capacity: Maximum tokens (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            # Add tokens based on elapsed time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def wait_for_tokens(self, tokens: int = 1, timeout: float = 60.0) -> bool:
        """Wait until tokens are available or timeout."""
        start = time.monotonic()

        while time.monotonic() - start < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.1)

        return False

    def time_until_available(self, tokens: int = 1) -> float:
        """Calculate time until tokens will be available."""
        if self.tokens >= tokens:
            return 0
        return (tokens - self.tokens) / self.rate


class RateLimiter:
    """
    Distributed rate limiter using Redis.
    Enforces RPM and RPD limits for LLM API calls.
    """

    # Redis key prefixes
    KEY_PREFIX_RPM = "rate_limit:rpm"
    KEY_PREFIX_RPD = "rate_limit:rpd"

    def __init__(self, redis_client: Optional[RedisClient] = None):
        self._redis = redis_client or get_redis_client()
        self._llm_config = get_llm_config()
        self._local_buckets: Dict[str, TokenBucket] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}

    def _get_rpm_key(self, model: str, key_index: Optional[int] = None) -> str:
        """Get Redis key for RPM counter."""
        minute = datetime.now().strftime("%Y%m%d%H%M")
        if key_index is not None:
            return f"{self.KEY_PREFIX_RPM}:{model}:key{key_index}:{minute}"
        return f"{self.KEY_PREFIX_RPM}:{model}:{minute}"

    def _get_rpd_key(self, model: str, key_index: Optional[int] = None) -> str:
        """Get Redis key for RPD counter."""
        day = datetime.now().strftime("%Y%m%d")
        if key_index is not None:
            return f"{self.KEY_PREFIX_RPD}:{model}:key{key_index}:{day}"
        return f"{self.KEY_PREFIX_RPD}:{model}:{day}"

    def _get_model_spec(self, model: str) -> ModelSpec:
        """Get model specification from config."""
        spec = self._llm_config.models.get(model)
        if not spec:
            raise ValueError(f"Unknown model: {model}")
        return spec

    def _get_token_bucket(self, model: str) -> TokenBucket:
        """Get or create token bucket for a model."""
        if model not in self._local_buckets:
            spec = self._get_model_spec(model)
            # Rate is RPM / 60 = requests per second
            rate = spec.rpm / 60.0
            self._local_buckets[model] = TokenBucket(rate, spec.rpm)
        return self._local_buckets[model]

    def _get_semaphore(self, model: str) -> asyncio.Semaphore:
        """Get or create semaphore for concurrent request limiting."""
        if model not in self._semaphores:
            spec = self._get_model_spec(model)
            self._semaphores[model] = asyncio.Semaphore(spec.concurrent)
        return self._semaphores[model]

    async def check_rpm_limit(self, model: str, key_index: Optional[int] = None, rpm_limit: Optional[int] = None) -> tuple[bool, int]:
        """
        Check if RPM limit allows a request.

        Args:
            model: Model name
            key_index: API key index (for Gemini rotation)
            rpm_limit: Optional custom RPM limit (overrides model spec)

        Returns:
            (allowed, current_count)
        """
        # Use custom rpm_limit if provided, otherwise get from model spec
        if rpm_limit is None:
            spec = self._get_model_spec(model)
            rpm_limit = spec.rpm

        key = self._get_rpm_key(model, key_index)

        try:
            current = self._redis.get(key)
            current_count = int(current) if current else 0
            return current_count < rpm_limit, current_count
        except Exception as e:
            logger.warning(f"Redis RPM check failed, allowing request: {e}")
            return True, 0

    async def check_rpd_limit(self, model: str, key_index: Optional[int] = None) -> tuple[bool, int]:
        """
        Check if RPD limit allows a request.

        Args:
            model: Model name
            key_index: API key index (for Gemini rotation)

        Returns:
            (allowed, current_count)
        """
        spec = self._get_model_spec(model)
        key = self._get_rpd_key(model, key_index)

        try:
            current = self._redis.get(key)
            current_count = int(current) if current else 0
            return current_count < spec.rpd, current_count
        except Exception as e:
            logger.warning(f"Redis RPD check failed: {e}")
            return True, 0

    async def increment_counters(self, model: str, key_index: Optional[int] = None):
        """Increment both RPM and RPD counters."""
        rpm_key = self._get_rpm_key(model, key_index)
        rpd_key = self._get_rpd_key(model, key_index)

        try:
            pipe = self._redis.pipeline()

            # RPM counter (expires in 60 seconds)
            pipe.incr(rpm_key)
            pipe.expire(rpm_key, 60)

            # RPD counter (expires in 24 hours)
            pipe.incr(rpd_key)
            pipe.expire(rpd_key, 86400)

            pipe.execute()
        except Exception as e:
            logger.warning(f"Redis counter increment failed: {e}")

    def _get_retry_after_key(self, provider: str, model: str, key_index: Optional[int] = None) -> str:
        """
        Get Redis key for retry_after timestamp.

        Format: rate_limit:retry_after:{provider}:{model}:key{index}
        """
        key_suffix = f"key{key_index}" if key_index is not None else "default"
        return f"rate_limit:retry_after:{provider}:{model}:{key_suffix}"

    def set_retry_after(self, provider: str, model: str, key_index: Optional[int], retry_after: float):
        """
        Store retry_after time in Redis.

        IMPORTANT: If a longer retry_after already exists (e.g., RPD limit until midnight),
        do NOT overwrite it with a shorter one (e.g., RPM limit for 60 seconds).

        Args:
            provider: LLM provider name (e.g., 'groq', 'gemini')
            model: Model name
            key_index: API key index
            retry_after: Seconds to wait before retry
        """
        key = self._get_retry_after_key(provider, model, key_index)
        new_retry_until = time.time() + retry_after

        try:
            # Check if a longer retry_after already exists
            existing = self._redis.get(key)
            if existing:
                existing_retry_until = float(existing)
                if new_retry_until <= existing_retry_until:
                    remaining = existing_retry_until - time.time()
                    logger.debug(
                        f"Skipping shorter retry_after for {provider} key {key_index}: "
                        f"existing {remaining:.0f}s > new {retry_after:.0f}s"
                    )
                    return

            # Store Unix timestamp when retry is allowed
            self._redis.set(key, str(new_retry_until), ex=int(retry_after) + 5)
            logger.info(
                f"Set retry_after for {provider} key {key_index}: "
                f"wait {retry_after:.1f}s (until {time.strftime('%H:%M:%S', time.localtime(new_retry_until))})"
            )
        except Exception as e:
            logger.warning(f"Failed to set retry_after in Redis: {e}")

    def get_retry_after(self, provider: str, model: str, key_index: Optional[int]) -> float:
        """
        Get remaining wait time before retry is allowed.

        Args:
            provider: LLM provider name
            model: Model name
            key_index: API key index

        Returns:
            Remaining seconds to wait (0 if retry is allowed)
        """
        key = self._get_retry_after_key(provider, model, key_index)

        try:
            retry_until_str = self._redis.get(key)
            if not retry_until_str:
                return 0.0

            retry_until = float(retry_until_str)
            remaining = retry_until - time.time()
            return max(0.0, remaining)
        except Exception as e:
            logger.warning(f"Failed to get retry_after from Redis: {e}")
            return 0.0

    def is_retry_allowed(self, provider: str, model: str, key_index: Optional[int]) -> bool:
        """
        Check if retry is allowed (retry_after time has passed).

        Args:
            provider: LLM provider name
            model: Model name
            key_index: API key index

        Returns:
            True if retry is allowed, False if still blocked
        """
        remaining = self.get_retry_after(provider, model, key_index)
        return remaining == 0.0

    async def acquire(self, model: str) -> bool:
        """
        Try to acquire permission for an API call.

        Returns:
            True if allowed, False if rate limited
        """
        # Check RPD first (stricter limit)
        rpd_allowed, rpd_count = await self.check_rpd_limit(model)
        if not rpd_allowed:
            logger.warning(f"RPD limit reached for {model}: {rpd_count}")
            return False

        # Check RPM
        rpm_allowed, rpm_count = await self.check_rpm_limit(model)
        if not rpm_allowed:
            logger.warning(f"RPM limit reached for {model}: {rpm_count}")
            return False

        # Use local token bucket for smoother rate limiting
        bucket = self._get_token_bucket(model)
        if not await bucket.acquire():
            return False

        # Increment counters
        await self.increment_counters(model)
        return True

    async def wait_and_acquire(self, model: str, timeout: float = 60.0) -> bool:
        """
        Wait until rate limit allows a request or timeout.

        Args:
            model: Model name
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout

        Raises:
            RateLimitExceeded: If daily limit is reached
        """
        start = time.monotonic()

        while time.monotonic() - start < timeout:
            # Check daily limit (can't wait for this)
            rpd_allowed, rpd_count = await self.check_rpd_limit(model)
            if not rpd_allowed:
                raise RateLimitExceeded(
                    model=model,
                    limit_type="RPD",
                    retry_after=self._seconds_until_midnight()
                )

            if await self.acquire(model):
                return True

            await asyncio.sleep(0.5)

        raise RateLimitExceeded(
            model=model,
            limit_type="RPM",
            retry_after=60 - (time.monotonic() - start) % 60
        )

    async def get_status(self, model: str) -> RateLimitStatus:
        """Get current rate limit status for a model."""
        spec = self._get_model_spec(model)

        rpm_allowed, rpm_count = await self.check_rpm_limit(model)
        rpd_allowed, rpd_count = await self.check_rpd_limit(model)

        is_limited = not rpm_allowed or not rpd_allowed
        retry_after = None

        if not rpm_allowed:
            bucket = self._get_token_bucket(model)
            retry_after = bucket.time_until_available()
        elif not rpd_allowed:
            retry_after = self._seconds_until_midnight()

        return RateLimitStatus(
            model=model,
            rpm_limit=spec.rpm,
            rpm_used=rpm_count,
            rpm_remaining=max(0, spec.rpm - rpm_count),
            rpd_limit=spec.rpd,
            rpd_used=rpd_count,
            rpd_remaining=max(0, spec.rpd - rpd_count),
            is_limited=is_limited,
            retry_after=retry_after
        )

    def _seconds_until_midnight(self) -> float:
        """Calculate seconds until midnight (RPD reset)."""
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return (midnight - now).total_seconds()

    async def execute_with_limit(
        self,
        model: str,
        func: Callable,
        *args,
        secondary_model: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with rate limiting.
        Uses secondary model if primary is rate limited.

        Args:
            model: Primary model name
            func: Async function to execute
            secondary_model: Model to use if primary is rate limited
            *args, **kwargs: Arguments for func
        """
        semaphore = self._get_semaphore(model)

        async with semaphore:
            try:
                await self.wait_and_acquire(model, timeout=30.0)
                return await func(*args, model=model, **kwargs)

            except RateLimitExceeded as e:
                if secondary_model:
                    logger.info(
                        f"Primary model {model} rate limited, "
                        f"switching to secondary model {secondary_model}"
                    )
                    await self.wait_and_acquire(secondary_model, timeout=30.0)
                    return await func(*args, model=secondary_model, **kwargs)
                raise


def rate_limited(model_param: str = "model", secondary_model_param: str = None):
    """
    Decorator for rate limiting async functions.

    Args:
        model_param: Name of the parameter containing model name
        secondary_model_param: Name of the parameter for secondary model
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            model = kwargs.get(model_param)
            if not model:
                raise ValueError(f"Missing required parameter: {model_param}")

            secondary_model = kwargs.get(secondary_model_param) if secondary_model_param else None

            rate_limiter = get_rate_limiter()

            return await rate_limiter.execute_with_limit(
                model=model,
                func=func,
                *args,
                secondary_model=secondary_model,
                **kwargs
            )

        return wrapper
    return decorator


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
