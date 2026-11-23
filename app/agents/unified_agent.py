"""
Unified Analysis Agent.
Combines Sentiment, Category, and Complaint analysis into a single LLM call.
"""

import logging
from typing import Dict, Any, Optional

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)
from app.agents.category_agent import get_category_agent
from app.agents.complaint_agent import get_complaint_agent
from app.schemas.llm import (
    UnifiedAnalysisResult,
    SentimentResult,
    CategoryResult,
    ComplaintResult,
    SentimentLabel,
    SENTIMENT_LABEL_MAPPINGS,
    ReviewMetrics,
    MetricInfo,
    ComplaintType,
    UrgencyLevel,
    EscalationLevel,
    DepartmentInfo
)


class UnifiedAnalysisAgent(BaseAgent):
    """
    Agent for performing unified analysis (Sentiment + Category + Complaint).
    Reduces LLM calls from 3 to 1 per review.
    """

    AGENT_TYPE = "unified"
    TASK_TYPE = "unified_analysis"
    PROMPT_TEMPLATE_ID = "unified_analysis"
    CONFIDENCE_THRESHOLD = 0.7
    RESPONSE_SCHEMA = UnifiedAnalysisResult  # NEW: Pydantic schema for response

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Helper agents for formatting prompts (reusing existing logic)
        self._category_agent = get_category_agent()
        self._complaint_agent = get_complaint_agent()

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare variables for unified analysis prompt."""
        # Safe extraction with None handling
        app_name = input_data.get('app_name') or 'Unknown App'
        rating = input_data.get('rating')
        if rating is None or rating == '':
            rating = 'N/A'
        
        return {
            'app_name': str(app_name),
            'rating': str(rating),
            'content': str(input_data.get('content') or ''),
            'categories': self._category_agent._format_categories(),
            'department_codes': self._complaint_agent._format_department_codes(),
            'additional_context': str(input_data.get('additional_context') or ''),
            'previous_complaints': str(input_data.get('previous_complaints') or '')
        }

    def _parse_result(self, parsed_json: Dict[str, Any]) -> UnifiedAnalysisResult:
        """Parse unified result from LLM response."""
        result_data = parsed_json if isinstance(parsed_json, dict) else {}
        # Handle case where parsed_json is valid dict but empty or missing keys
        if not result_data:
            # Return default/empty result with low confidence
            return UnifiedAnalysisResult(
                sentiment=SentimentResult(sentiment_label=SentimentLabel.NEUTRAL, sentiment_score=3, emotions=[], confidence=0.0),
                category=CategoryResult(primary_category='other', secondary_categories=[], metrics=ReviewMetrics(), confidence=0.0),
                complaint=ComplaintResult(is_complaint=False, complaint_type=ComplaintType.GENERAL_REVIEW, urgency=UrgencyLevel.LOW, severity=1, primary_dept=DepartmentInfo(code="CS_CENTER", name="고객센터"), secondary_depts=[], escalation_required=False, confidence=0.0),
                confidence=0.0
            )
        
        # 1. Parse Sentiment
        sentiment_data = result_data.get('sentiment') or {}
        sentiment_result = self._parse_sentiment(sentiment_data)

        # 2. Parse Category
        category_data = result_data.get('category') or {}
        category_result = self._parse_category(category_data)

        # 3. Parse Complaint
        complaint_data = result_data.get('complaint') or {}
        complaint_result = self._parse_complaint(complaint_data)

        confidence = float(result_data.get('confidence', 0.7))

        return UnifiedAnalysisResult(
            sentiment=sentiment_result,
            category=category_result,
            complaint=complaint_result,
            confidence=confidence
        )

    def _parse_sentiment(self, data: Dict[str, Any]) -> SentimentResult:
        """Parse sentiment section."""
        # Reuse logic similar to SentimentAgent but adapted for dict input
        label_str = data.get('sentiment_label', 'neutral').lower()

        # Try defensive mapping first (common LLM variations)
        if label_str in SENTIMENT_LABEL_MAPPINGS:
            sentiment_label = SENTIMENT_LABEL_MAPPINGS[label_str]
            logger.debug(f"Mapped sentiment label: {label_str} → {sentiment_label.value}")
        else:
            try:
                sentiment_label = SentimentLabel(label_str)
            except ValueError:
                logger.warning(f"Unknown sentiment label: {label_str}, using neutral")
                sentiment_label = SentimentLabel.NEUTRAL

        sentiment_score = self._safe_int(data.get('sentiment_score'), 3)
        sentiment_score = max(1, min(5, sentiment_score))

        # Parse emotions (pass-through, trust LLM output)
        emotions = data.get('emotions', [])

        return SentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            emotions=emotions,
            confidence=float(data.get('confidence', 0.5))
        )

    def _parse_category(self, data: Dict[str, Any]) -> CategoryResult:
        """Parse category section."""
        primary = data.get('primary_category', 'other')
        if primary not in self._category_agent.CATEGORIES:
            primary = 'other'

        secondary = data.get('secondary_categories', [])
        secondary = [c for c in secondary if c in self._category_agent.CATEGORIES]
        # Parse metrics
        metrics_data = data.get('metrics') or {}
        metrics = self._category_agent._parse_metrics(metrics_data)

        return CategoryResult(
            primary_category=primary,
            secondary_categories=secondary,
            metrics=metrics,
            confidence=float(data.get('confidence', 0.5))
        )

    def _safe_int(self, value: Any, default: int = 1) -> int:
        """Safely convert value to int with default fallback."""
        if value is None or value == '':
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _parse_complaint(self, data: Dict[str, Any]) -> ComplaintResult:
        """Parse complaint section."""
        is_complaint = bool(data.get('is_complaint', False))

        # Parse complaint type with defensive mapping
        type_str = data.get('complaint_type', 'general_review')

        # Defensive mapping for common LLM mistakes
        type_mappings = {
            'performance': 'dissatisfaction',
            '성능': 'dissatisfaction',
            'speed': 'dissatisfaction',
            'stability': 'error_report',
            '안정성': 'error_report',
        }

        if type_str in type_mappings:
            original_type = type_str
            type_str = type_mappings[type_str]
            logger.debug(f"Mapped complaint type: {original_type} → {type_str}")

        try:
            complaint_type = ComplaintType(type_str)
        except ValueError:
            complaint_type = ComplaintType.GENERAL_REVIEW

        urgency_val = self._safe_int(data.get('urgency'), 1)
        urgency = UrgencyLevel(max(1, min(4, urgency_val)))

        severity = self._safe_int(data.get('severity'), 1)
        severity = max(1, min(5, severity))

        # Parse departments using ComplaintAgent's logic
        # Parse primary department
        primary_data = data.get('primary_dept') or {}
        primary_dept = self._complaint_agent._parse_department(primary_data, role="primary")

        # Parse secondary departments
        secondary_data = data.get('secondary_depts') or []
        secondary_depts = [
            self._complaint_agent._parse_department(d, role=d.get('role', 'support'))
            for d in secondary_data
        ]

        escalation_required = bool(data.get('escalation_required', False))
        escalation_level = None
        if escalation_required:
            level_str = data.get('escalation_level', 'staff')
            # Simple mapping, full logic in ComplaintAgent
            try:
                escalation_level = EscalationLevel(level_str)
            except ValueError:
                escalation_level = EscalationLevel.STAFF

        return ComplaintResult(
            is_complaint=is_complaint,
            complaint_type=complaint_type,
            sub_type=data.get('sub_type'),
            urgency=urgency,
            severity=severity,
            primary_dept=primary_dept,
            secondary_depts=secondary_depts,
            escalation_required=escalation_required,
            escalation_level=escalation_level,
            confidence=float(data.get('confidence', 0.5))
        )

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract overall confidence."""
        if not parsed_json:
            return 0.5
        result = parsed_json.get('result') or {}
        return float(result.get('confidence', 0.5))

    def _create_default_result(self, input_data: Dict[str, Any]) -> UnifiedAnalysisResult:
        """
        Create default result based on rating only.
        From groq_model_guide.md lines 394-435
        """
        rating = input_data.get('rating', 3)
        if rating is None or rating == '':
            rating = 3
        try:
            rating = int(rating)
        except (ValueError, TypeError):
            rating = 3

        # Rating-based sentiment inference
        if rating <= 2:
            sentiment_label = SentimentLabel.NEGATIVE
            sentiment_score = rating
            emotions = ['frustration']
        elif rating >= 4:
            sentiment_label = SentimentLabel.POSITIVE
            sentiment_score = rating
            emotions = ['satisfaction']
        else:
            sentiment_label = SentimentLabel.NEUTRAL
            sentiment_score = 3
            emotions = ['indifference']

        sentiment = SentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            emotions=emotions,
            confidence=0.3
        )

        category = CategoryResult(
            primary_category='other',
            secondary_categories=[],
            metrics=ReviewMetrics(),
            confidence=0.3
        )

        complaint = ComplaintResult(
            is_complaint=(rating <= 2),
            complaint_type=ComplaintType.GENERAL_REVIEW if rating > 2 else ComplaintType.DISSATISFACTION,
            urgency=UrgencyLevel.LOW,
            severity=1 if rating > 2 else 3,
            primary_dept=DepartmentInfo(code="CS_CENTER", name="고객센터"),
            secondary_depts=[],
            escalation_required=False,
            confidence=0.3
        )

        logger.info(
            f"Created default result from rating {rating}: "
            f"sentiment={sentiment_label.value}, is_complaint={complaint.is_complaint}"
        )

        return UnifiedAnalysisResult(
            sentiment=sentiment,
            category=category,
            complaint=complaint,
            confidence=0.3
        )

    def _create_partial_result(
        self,
        parsed_json: Dict[str, Any],
        confidence: float = 0.5
    ) -> UnifiedAnalysisResult:
        """Create partial result with defaults for missing sections."""
        result_data = parsed_json.get('result', {})

        # Try to parse each section, use defaults if missing/invalid
        try:
            sentiment_data = result_data.get('sentiment', {})
            sentiment = self._parse_sentiment(sentiment_data)
        except Exception:
            sentiment = SentimentResult(
                sentiment_label=SentimentLabel.NEUTRAL,
                sentiment_score=3,
                emotions=[],
                confidence=0.3
            )

        try:
            category_data = result_data.get('category', {})
            category = self._parse_category(category_data)
        except Exception:
            category = CategoryResult(
                primary_category='other',
                secondary_categories=[],
                metrics=ReviewMetrics(),
                confidence=0.3
            )

        try:
            complaint_data = result_data.get('complaint', {})
            complaint = self._parse_complaint(complaint_data)
        except Exception:
            complaint = ComplaintResult(
                is_complaint=False,
                complaint_type=ComplaintType.GENERAL_REVIEW,
                urgency=UrgencyLevel.LOW,
                severity=1,
                primary_dept=DepartmentInfo(code="CS_CENTER", name="고객센터"),
                secondary_depts=[],
                escalation_required=False,
                confidence=0.3
            )

        logger.info("Created partial result with some defaults")

        return UnifiedAnalysisResult(
            sentiment=sentiment,
            category=category,
            complaint=complaint,
            confidence=min(sentiment.confidence, category.confidence, complaint.confidence)
        )


_unified_agent: Optional[UnifiedAnalysisAgent] = None

def get_unified_agent() -> UnifiedAnalysisAgent:
    """Get singleton UnifiedAnalysisAgent instance."""
    global _unified_agent
    if _unified_agent is None:
        _unified_agent = UnifiedAnalysisAgent()
    return _unified_agent
