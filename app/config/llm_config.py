"""
LLM Configuration with model specifications and rate limits.
Loaded from YAML configuration file.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
from functools import lru_cache


CONFIG_DIR = Path(__file__).parent


@dataclass
class ModelSpec:
    """Specification for a single LLM model."""
    name: str
    context_window: int
    rpm: int                    # Requests Per Minute
    rpd: int                    # Requests Per Day
    tpm: int                    # Tokens Per Minute
    concurrent: int             # Max concurrent requests
    temperature: float
    max_output_tokens: int
    top_p: float
    is_embedding: bool = False
    dimensions: Optional[int] = None
    secondary_model: Optional[str] = None


@dataclass
class TaskModelMapping:
    """Mapping of task types to model specifications."""
    task_type: str
    primary_model: str
    secondary_model: str
    temperature: float
    max_output_tokens: int


@dataclass
class LLMConfig:
    """Complete LLM configuration."""
    models: Dict[str, ModelSpec]
    task_mappings: Dict[str, TaskModelMapping]
    embedding_dimensions: int
    retry_config: Dict[str, Any]

    @classmethod
    def load(cls) -> 'LLMConfig':
        """Load configuration from YAML file."""
        config_path = CONFIG_DIR / 'llm_models.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        # Parse models
        models = {}
        for model_name, model_data in config_data.get('models', {}).items():
            models[model_name] = ModelSpec(
                name=model_name,
                context_window=model_data.get('context_window', 1000000),
                rpm=model_data.get('rate_limits', {}).get('rpm', 15),
                rpd=model_data.get('rate_limits', {}).get('rpd', 1500),
                tpm=model_data.get('rate_limits', {}).get('tpm', 1000000),
                concurrent=model_data.get('rate_limits', {}).get('concurrent', 5),
                temperature=model_data.get('default_params', {}).get('temperature', 0.1),
                max_output_tokens=model_data.get('default_params', {}).get('max_output_tokens', 1024),
                top_p=model_data.get('default_params', {}).get('top_p', 0.95),
                is_embedding=model_data.get('is_embedding', False),
                dimensions=model_data.get('dimensions'),
                secondary_model=model_data.get('secondary_model')
            )

        # Parse task mappings
        task_mappings = {}
        for task_name, task_data in config_data.get('task_mappings', {}).items():
            task_mappings[task_name] = TaskModelMapping(
                task_type=task_name,
                primary_model=task_data.get('primary_model'),
                secondary_model=task_data.get('secondary_model'),
                temperature=task_data.get('temperature', 0.1),
                max_output_tokens=task_data.get('max_output_tokens', 1024)
            )

        return cls(
            models=models,
            task_mappings=task_mappings,
            embedding_dimensions=config_data.get('embedding', {}).get('dimensions', 1024),
            retry_config=config_data.get('retry', {})
        )

    def get_model_for_task(self, task_type: str) -> ModelSpec:
        """Get the primary model specification for a task type."""
        mapping = self.task_mappings.get(task_type)
        if not mapping:
            raise ValueError(f"Unknown task type: {task_type}")
        return self.models.get(mapping.primary_model)

    def get_secondary_model_for_task(self, task_type: str) -> Optional[ModelSpec]:
        """Get the secondary model specification for a task type (rate limit scenario)."""
        mapping = self.task_mappings.get(task_type)
        if not mapping or not mapping.secondary_model:
            return None
        return self.models.get(mapping.secondary_model)


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfig:
    """Get cached LLM configuration."""
    return LLMConfig.load()
