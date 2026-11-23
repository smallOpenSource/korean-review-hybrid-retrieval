"""
Gemini API Key and Model Rotation Manager.
Automatically rotates between models first, then between API keys when rate limits are reached.
Uses database (MySQL) for state persistence.
"""

import logging
from typing import List, Optional, Tuple
from sqlalchemy import text

logger = logging.getLogger(__name__)


class GeminiKeyRotator:
    """
    Gemini API Key and Model rotation manager.
    
    Implements two-tier rotation strategy:
    1. Model Rotation (Inner Loop): Try all models with current key
    2. Key Rotation (Outer Loop): After all models fail, rotate to next key and reset to first model
    
    Uses database table `gemini_rotation_state` to track current key and model indices.
    """
    
    def __init__(self, api_keys: List[str], models: List[str]):
        """
        Initialize key and model rotator.
        
        Args:
            api_keys: List of Gemini API keys
            models: List of model names in rotation order
        """
        if not api_keys:
            raise ValueError("At least one API key required")
        if not models:
            raise ValueError("At least one model required")
        
        self._keys = api_keys
        self._models = models
        
        logger.info(f"Initialized Gemini rotator with {len(api_keys)} keys and {len(models)} models")
    
    def _get_db_session(self):
        """Get database session."""
        from scheduler.utils.database import get_db_session
        return get_db_session()
    
    def _get_state(self) -> Tuple[int, int]:
        """
        Get current rotation state from database.
        
        Returns:
            (key_index, model_index) tuple
        """
        session = self._get_db_session()
        try:
            result = session.execute(
                text("SELECT current_key_index, current_model_index FROM gemini_rotation_state WHERE id=1")
            ).fetchone()
            
            if result:
                key_idx, model_idx = result[0], result[1]
                # Bounds checking
                if 0 <= key_idx < len(self._keys) and 0 <= model_idx < len(self._models):
                    return (key_idx, model_idx)
                else:
                    logger.warning(f"Invalid indices in DB (key:{key_idx}, model:{model_idx}), resetting to (0,0)")
                    self._set_state(0, 0)
                    return (0, 0)
            else:
                # Initialize if not exists
                logger.info("Rotation state not found, initializing to (0, 0)")
                self._set_state(0, 0)
                return (0, 0)
        except Exception as e:
            logger.error(f"Failed to get rotation state from database: {e}")
            return (0, 0)
        finally:
            session.close()
    
    def _set_state(self, key_index: int, model_index: int):
        """
        Update rotation state in database.
        
        Args:
            key_index: API key index
            model_index: Model index
        """
        session = self._get_db_session()
        try:
            session.execute(
                text(
                    "INSERT INTO gemini_rotation_state (id, current_key_index, current_model_index) "
                    "VALUES (1, :key, :model) "
                    "ON DUPLICATE KEY UPDATE current_key_index=:key, current_model_index=:model"
                ),
                {"key": key_index, "model": model_index}
            )
            session.commit()
        except Exception as e:
            logger.error(f"Failed to set rotation state in database: {e}")
            session.rollback()
        finally:
            session.close()
    
    def get_current_key(self) -> str:
        """Get current API key."""
        key_index, _ = self._get_state()
        return self._keys[key_index]
    
    def get_current_index(self) -> int:
        """Get current key index."""
        key_index, _ = self._get_state()
        return key_index
    
    def get_current_model(self) -> str:
        """Get current model name."""
        _, model_index = self._get_state()
        return self._models[model_index]
    
    def get_current_model_index(self) -> int:
        """Get current model index."""
        _, model_index = self._get_state()
        return model_index
    
    def rotate_to_next_model(self) -> Tuple[str, str]:
        """
        Rotate to next model (keep same API key).
        This is the INNER loop of the rotation strategy.
        
        Returns:
            (current_key, new_model) tuple
        """
        key_index, model_index = self._get_state()
        next_model_index = (model_index + 1) % len(self._models)
        
        self._set_state(key_index, next_model_index)
        
        logger.info(
            f"→ Model rotation: {self._models[model_index]} → {self._models[next_model_index]} "
            f"(key {key_index} unchanged)"
        )
        
        return (self._keys[key_index], self._models[next_model_index])
    
    def rotate_to_next_key(self) -> Tuple[str, str]:
        """
        Rotate to next API key AND reset model to first.
        This is the OUTER loop of the rotation strategy.
        
        Returns:
            (new_key, first_model) tuple
        """
        key_index, _ = self._get_state()
        next_key_index = (key_index + 1) % len(self._keys)
        
        # Reset to first model when rotating keys
        self._set_state(next_key_index, 0)
        
        logger.info(
            f"→ Key rotation: {key_index} → {next_key_index}, reset to model 0 ({self._models[0]})"
        )
        
        return (self._keys[next_key_index], self._models[0])
    
    def get_key_count(self) -> int:
        """Get number of registered API keys."""
        return len(self._keys)
    
    def get_model_count(self) -> int:
        """Get number of registered models."""
        return len(self._models)
    
    def reset_to_first(self):
        """Reset to first key and first model."""
        self._set_state(0, 0)
        logger.info("Reset to first Gemini API key and first model")


# Singleton instance
_key_rotator: Optional[GeminiKeyRotator] = None


def get_gemini_key_rotator(api_keys: Optional[List[str]] = None, models: Optional[List[str]] = None) -> Optional[GeminiKeyRotator]:
    """
    Get singleton Gemini key rotator instance.
    
    Args:
        api_keys: API keys (required on first call)
        models: Model names (required on first call)
    
    Returns:
        GeminiKeyRotator instance or None if no keys/models provided
    """
    global _key_rotator
    
    if _key_rotator is None and api_keys and models:
        _key_rotator = GeminiKeyRotator(api_keys, models)
    
    return _key_rotator

