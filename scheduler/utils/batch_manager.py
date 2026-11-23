"""
Dynamic Batch Size Manager for adaptive batch processing.
Uses Redis for state persistence across scheduler restarts.
Adjusts batch size based on success rate (2-6 range).
"""

import logging
import time
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BatchSizeStatus:
    """Current batch size status."""
    current_size: int
    success_count: int
    failure_count: int
    success_rate: float
    last_updated: float


class DynamicBatchSizeManager:
    """
    Manages dynamic batch sizing with Redis-backed persistence.

    Strategy:
    - Start at batch_size=2 (conservative)
    - Grow by 1 if success_rate >= 80% (max 6)
    - Shrink by 1 if success_rate < 80% (min 2)
    - Persist state to Redis for restart resilience
    """

    # Redis keys
    KEY_PREFIX = "batch_manager"
    KEY_CURRENT_SIZE = f"{KEY_PREFIX}:current_size"
    KEY_SUCCESS_COUNT = f"{KEY_PREFIX}:success_count"
    KEY_FAILURE_COUNT = f"{KEY_PREFIX}:failure_count"
    KEY_LAST_UPDATED = f"{KEY_PREFIX}:last_updated"

    # Configuration (aggressive throughput - failures will be retried)
    MIN_BATCH_SIZE = 10
    MAX_BATCH_SIZE = 40
    SUCCESS_THRESHOLD = 0.70  # 70% success rate required for growth
    SAMPLE_SIZE = 3  # Number of batches to consider for rate calculation

    def __init__(self, redis_client):
        """
        Initialize batch manager.

        Args:
            redis_client: Redis client instance for state persistence
        """
        self._redis = redis_client
        self._initialize_state()

    def _initialize_state(self):
        """Initialize state if not exists in Redis."""
        if not self._redis.exists(self.KEY_CURRENT_SIZE):
            logger.info("Initializing batch manager state (first run) - starting at batch_size=6")
            self._redis.set(self.KEY_CURRENT_SIZE, "6")  # Start at max capacity (NUM_PARALLEL=3 × 2 instances)
            self._redis.set(self.KEY_SUCCESS_COUNT, "0")
            self._redis.set(self.KEY_FAILURE_COUNT, "0")
            self._redis.set(self.KEY_LAST_UPDATED, str(time.time()))

    def get_current_batch_size(self) -> int:
        """
        Get current batch size from Redis.

        Returns:
            Current batch size (2-6)
        """
        size_str = self._redis.get(self.KEY_CURRENT_SIZE)
        if size_str is None:
            logger.warning("Batch size not found in Redis, reinitializing")
            self._initialize_state()
            return self.MIN_BATCH_SIZE

        size = int(size_str)
        # Ensure within bounds
        size = max(self.MIN_BATCH_SIZE, min(self.MAX_BATCH_SIZE, size))
        return size

    def record_batch_result(self, success_count: int, failure_count: int):
        """
        Record batch processing result and adjust batch size if needed.

        Args:
            success_count: Number of successful items in batch
            failure_count: Number of failed items in batch
        """
        # Update counters
        current_success = int(self._redis.get(self.KEY_SUCCESS_COUNT) or "0")
        current_failure = int(self._redis.get(self.KEY_FAILURE_COUNT) or "0")

        new_success = current_success + success_count
        new_failure = current_failure + failure_count

        self._redis.set(self.KEY_SUCCESS_COUNT, str(new_success))
        self._redis.set(self.KEY_FAILURE_COUNT, str(new_failure))
        self._redis.set(self.KEY_LAST_UPDATED, str(time.time()))

        # Calculate success rate
        total = new_success + new_failure
        if total == 0:
            return  # No data yet

        success_rate = new_success / total

        # Log current status
        current_size = self.get_current_batch_size()
        logger.info(
            f"Batch result recorded: success={success_count}, failure={failure_count} "
            f"(total: {new_success}/{total}, rate={success_rate:.2%}, batch_size={current_size})"
        )

        # Adjust batch size if we have enough samples
        if total >= self.SAMPLE_SIZE:
            self._adjust_batch_size(success_rate, current_size)
            # Reset counters after adjustment
            self._redis.set(self.KEY_SUCCESS_COUNT, "0")
            self._redis.set(self.KEY_FAILURE_COUNT, "0")

    def _adjust_batch_size(self, success_rate: float, current_size: int):
        """
        Adjust batch size based on success rate.

        Args:
            success_rate: Current success rate (0.0-1.0)
            current_size: Current batch size
        """
        new_size = current_size

        if success_rate >= self.SUCCESS_THRESHOLD:
            # Success rate is good, try to grow
            if current_size < self.MAX_BATCH_SIZE:
                new_size = current_size + 1
                logger.info(
                    f"Increasing batch size: {current_size} → {new_size} "
                    f"(success_rate={success_rate:.2%} >= {self.SUCCESS_THRESHOLD:.0%})"
                )
        else:
            # Success rate is low, shrink
            if current_size > self.MIN_BATCH_SIZE:
                new_size = current_size - 1
                logger.warning(
                    f"Decreasing batch size: {current_size} → {new_size} "
                    f"(success_rate={success_rate:.2%} < {self.SUCCESS_THRESHOLD:.0%})"
                )

        if new_size != current_size:
            self._redis.set(self.KEY_CURRENT_SIZE, str(new_size))

    def get_status(self) -> BatchSizeStatus:
        """
        Get current batch size status.

        Returns:
            BatchSizeStatus with current metrics
        """
        current_size = self.get_current_batch_size()
        success_count = int(self._redis.get(self.KEY_SUCCESS_COUNT) or "0")
        failure_count = int(self._redis.get(self.KEY_FAILURE_COUNT) or "0")
        last_updated = float(self._redis.get(self.KEY_LAST_UPDATED) or "0")

        total = success_count + failure_count
        success_rate = (success_count / total) if total > 0 else 0.0

        return BatchSizeStatus(
            current_size=current_size,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            last_updated=last_updated
        )

    def reset(self):
        """Reset batch size to minimum and clear counters."""
        logger.info("Resetting batch manager to initial state")
        self._redis.set(self.KEY_CURRENT_SIZE, str(self.MIN_BATCH_SIZE))
        self._redis.set(self.KEY_SUCCESS_COUNT, "0")
        self._redis.set(self.KEY_FAILURE_COUNT, "0")
        self._redis.set(self.KEY_LAST_UPDATED, str(time.time()))
