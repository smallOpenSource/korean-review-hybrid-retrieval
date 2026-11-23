"""
Category Classification Agent.
Classifies reviews into categories and extracts metrics.
"""

from typing import Dict, Any, List, Optional

from app.agents.base_agent import BaseAgent
from app.schemas.llm import CategoryResult, ReviewMetrics, MetricInfo
from app.constants import ReviewCategory, CATEGORY_LABELS, CATEGORY_DESCRIPTIONS, get_all_categories


class CategoryAgent(BaseAgent):
    """
    Agent for classifying reviews into categories.

    Classifies reviews based on:
    - Primary category (main topic)
    - Secondary categories (related topics)
    - Feature metrics (login, transfer, payment, etc.)
    - Service metrics (customer service quality)
    - Performance metrics (speed, stability)
    - Related screens/services
    """

    AGENT_TYPE = "category"
    TASK_TYPE = "category_classification"
    PROMPT_TEMPLATE_ID = "category_classification"
    CONFIDENCE_THRESHOLD = 0.65

    # Available categories (from ReviewCategory Enum)
    CATEGORIES = [cat.value for cat in get_all_categories()]

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare variables for category classification prompt."""
        # Format categories for prompt
        categories_formatted = self._format_categories()

        return {
            'content': input_data.get('content', ''),
            'categories': categories_formatted
        }

    def _format_categories(self) -> str:
        """Format category list for prompt using ReviewCategory Enum."""
        lines = []
        for cat in ReviewCategory:
            label = CATEGORY_LABELS.get(cat, cat.value)
            desc = CATEGORY_DESCRIPTIONS.get(cat, "")
            lines.append(f"- {cat.value}: {label} - {desc}")

        return "\n".join(lines)

    def _parse_result(self, parsed_json: Dict[str, Any]) -> CategoryResult:
        """Parse category result from LLM response."""
        result_data = parsed_json if isinstance(parsed_json, dict) else {}

        # Parse primary category
        primary = result_data.get('primary_category', ReviewCategory.ETC.value)
        if primary not in self.CATEGORIES:
            primary = ReviewCategory.ETC.value

        # Parse secondary categories
        secondary = result_data.get('secondary_categories', [])
        secondary = [c for c in secondary if c in self.CATEGORIES]

        # Parse metrics
        metrics_data = result_data.get('metrics', {})
        metrics = self._parse_metrics(metrics_data)

        confidence = float(result_data.get('confidence', 0.5))

        return CategoryResult(
            primary_category=primary,
            secondary_categories=secondary,
            metrics=metrics,
            confidence=confidence
        )

    def _parse_metrics(self, metrics_data: Dict[str, Any]) -> ReviewMetrics:
        """Parse metrics from response."""
        def parse_metric(data: Dict[str, Any]) -> MetricInfo:
            return MetricInfo(
                detected=data.get('detected', False),
                keywords=data.get('keywords', []),
                sub_categories=data.get('sub_categories', []),
                issues=data.get('issues', []),
                screens=data.get('screens', []),
                services=data.get('services', [])
            )

        return ReviewMetrics(
            feature=parse_metric(metrics_data.get('feature', {})),
            service=parse_metric(metrics_data.get('service', {})),
            performance=parse_metric(metrics_data.get('performance', {})),
            related_screen=parse_metric(metrics_data.get('related_screen', {}))
        )

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract confidence from parsed response."""
        result = parsed_json.get('result', {})
        return float(result.get('confidence', 0.5))

    def _should_flag_for_review(
        self,
        confidence: float,
        result: CategoryResult,
        reasoning
    ) -> bool:
        """Determine if category result needs human review."""
        # Low confidence
        if confidence < self.CONFIDENCE_THRESHOLD:
            return True

        # Classified as 'etc' with low confidence
        if result.primary_category == ReviewCategory.ETC.value and confidence < 0.8:
            return True

        # No metrics detected at all
        all_metrics = [
            result.metrics.feature,
            result.metrics.service,
            result.metrics.performance,
            result.metrics.related_screen
        ]
        if not any(m.detected for m in all_metrics):
            return True

        return super()._should_flag_for_review(confidence, result, reasoning)


def get_category_agent() -> CategoryAgent:
    """Get singleton CategoryAgent instance."""
    return CategoryAgent()
