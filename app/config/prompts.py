"""
Prompt templates for LLM agents.
All prompts are loaded from YAML configuration to avoid hardcoding.
"""

import yaml
from dataclasses import dataclass
from typing import Dict, Any, Optional
from pathlib import Path
from functools import lru_cache
from string import Template


CONFIG_DIR = Path(__file__).parent


@dataclass
class PromptTemplate:
    """Single prompt template with metadata."""
    id: str
    version: str
    description: str
    template: str
    required_variables: list
    optional_variables: list

    def render(self, **kwargs) -> str:
        """Render the template with provided variables."""
        # Validate required variables
        missing = [v for v in self.required_variables if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")

        # Use safe substitution for optional variables
        template = Template(self.template)
        return template.safe_substitute(**kwargs)


class PromptTemplates:
    """Container for all prompt templates."""

    def __init__(self, templates: Dict[str, PromptTemplate], department_codes: Dict[str, Any]):
        self._templates = templates
        self._department_codes = department_codes

    @classmethod
    def load(cls) -> 'PromptTemplates':
        """Load all prompt templates from YAML file."""
        config_path = CONFIG_DIR / 'prompts.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        templates = {}
        for template_id, template_data in config_data.get('templates', {}).items():
            templates[template_id] = PromptTemplate(
                id=template_id,
                version=template_data.get('version', '1.0.0'),
                description=template_data.get('description', ''),
                template=template_data.get('template', ''),
                required_variables=template_data.get('required_variables', []),
                optional_variables=template_data.get('optional_variables', [])
            )

        # Load department codes (legacy fallback)
        department_codes = config_data.get('department_codes', {})

        return cls(templates, department_codes)

    def get(self, template_id: str) -> PromptTemplate:
        """Get a prompt template by ID."""
        if template_id not in self._templates:
            raise ValueError(f"Unknown prompt template: {template_id}")
        return self._templates[template_id]

    def render(self, template_id: str, **kwargs) -> str:
        """Render a prompt template with provided variables."""
        return self.get(template_id).render(**kwargs)

    def list_templates(self) -> Dict[str, str]:
        """List all available templates with descriptions."""
        return {
            tid: t.description
            for tid, t in self._templates.items()
        }

    def get_department_codes(self) -> Dict[str, Any]:
        """
        Get department codes (legacy fallback).

        Note: For new implementations, use DepartmentRoutingService instead.
        This method is kept for backward compatibility.
        """
        return self._department_codes


@lru_cache(maxsize=1)
def get_prompt_templates() -> PromptTemplates:
    """Get cached prompt templates."""
    return PromptTemplates.load()
