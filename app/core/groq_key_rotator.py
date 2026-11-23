"""
Groq API Key Rotation Manager.
Automatically rotates between 1-5 API keys when rate limits are reached.
Uses database (MySQL) for state persistence.
"""

import logging
from typing import List, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)


class GroqKeyRotator:
    """
    Groq API Key rotation manager.

    Implements single-tier rotation strategy:
    - Key Rotation: Cycles through 1-5 API keys (circular rotation)

    Uses database table `groq_rotation_state` to track current key index.
    """

    def __init__(self, api_keys: List[str], model: str):
        """
        Initialize key rotator.

        Args:
            api_keys: List of 1-5 Groq API keys
            model: Model name (for reference, not rotated)

        Raises:
            ValueError: If no API keys provided
        """
        if not api_keys or len(api_keys) < 1:
            raise ValueError(f"At least 1 Groq API key required, got {len(api_keys)}")

        self._keys = api_keys
        self._model = model  # Store for reference

        logger.info(f"Initialized Groq rotator with {len(api_keys)} keys for model {model}")

    def _get_db_session(self):
        """Get database session."""
        from scheduler.utils.database import get_db_session
        return get_db_session()

    def _get_state(self) -> int:
        """
        Get current rotation state from database.

        Returns:
            key_index: Current key index (0-4)
        """
        session = self._get_db_session()
        try:
            result = session.execute(
                text("SELECT current_key_index FROM groq_rotation_state WHERE id=1")
            ).fetchone()

            if result:
                key_idx = result[0]
                # Bounds checking
                if 0 <= key_idx < len(self._keys):
                    return key_idx
                else:
                    logger.warning(f"Invalid key index in DB ({key_idx}), resetting to 0")
                    self._set_state(0)
                    return 0
            else:
                # Initialize if not exists
                logger.info("Rotation state not found, initializing to key 0")
                self._set_state(0)
                return 0
        except Exception as e:
            logger.error(f"Failed to get rotation state from database: {e}")
            logger.warning("Defaulting to key 0")
            return 0
        finally:
            session.close()

    def _set_state(self, key_index: int):
        """
        Update rotation state in database.

        Args:
            key_index: API key index (0-4)
        """
        session = self._get_db_session()
        try:
            session.execute(
                text(
                    "INSERT INTO groq_rotation_state (id, current_key_index) "
                    "VALUES (1, :key) "
                    "ON DUPLICATE KEY UPDATE current_key_index=:key"
                ),
                {"key": key_index}
            )
            session.commit()
        except Exception as e:
            logger.error(f"Failed to set rotation state in database: {e}")
            session.rollback()
        finally:
            session.close()

    def get_current_key(self) -> str:
        """Get current API key."""
        key_index = self._get_state()
        return self._keys[key_index]

    def get_current_index(self) -> int:
        """Get current key index (0-4)."""
        return self._get_state()

    def get_current_model(self) -> str:
        """Get model name (for compatibility with Gemini rotator)."""
        return self._model

    def rotate_to_next_key(self) -> str:
        """
        Rotate to next API key (circular).

        Returns:
            new_key: The new current API key
        """
        current_index = self._get_state()
        next_index = (current_index + 1) % len(self._keys)

        self._set_state(next_index)

        logger.info(
            f"→ Key rotation: {current_index} → {next_index} ({next_index + 1}/{len(self._keys)})"
        )

        return self._keys[next_index]

    def get_key_count(self) -> int:
        """Get number of registered API keys."""
        return len(self._keys)

    def reset_to_first(self):
        """Reset to first key (index 0)."""
        self._set_state(0)
        logger.info("Reset to first Groq API key (index 0)")


# Singleton instance
_groq_key_rotator: Optional[GroqKeyRotator] = None


def get_groq_key_rotator(
    api_keys: Optional[List[str]] = None,
    model: Optional[str] = None
) -> Optional[GroqKeyRotator]:
    """
    Get singleton Groq key rotator instance.

    Args:
        api_keys: 1-5 API keys (required on first call)
        model: Model name (required on first call)

    Returns:
        GroqKeyRotator instance or None if no keys/model provided
    """
    global _groq_key_rotator

    if _groq_key_rotator is None and api_keys and model:
        _groq_key_rotator = GroqKeyRotator(api_keys, model)

    return _groq_key_rotator
