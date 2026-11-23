"""
Two-Stage Analysis Agent.
Stage 1: Quick classification (sentiment + category) for all reviews.
Stage 2: Detailed complaint analysis (department assignment) for complaints only.
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Literal

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
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
    COMPLAINT_TYPE_REVERSE,
    UrgencyLevel,
    EscalationLevel,
    ESCALATION_LEVEL_REVERSE,
    DepartmentInfo
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Azure Structured Output Pydantic 스키마
# 가이드 권장: extra="forbid" → additionalProperties: false 자동 포함
# ══════════════════════════════════════════════════════════════

# Stage 1: Quick classification response schema
class _S1Sentiment(BaseModel, extra="forbid"):
    sentiment_label: str
    sentiment_score: int
    emotions: List[str]
    confidence: float

class _S1Category(BaseModel, extra="forbid"):
    primary_category: str
    secondary_categories: List[str]
    confidence: float

class _S1Result(BaseModel, extra="forbid"):
    sentiment: _S1Sentiment
    category: _S1Category

class _S1Reasoning(BaseModel, extra="forbid"):
    summary: str
    key_factors: List[str]

class Stage1ResponseSchema(BaseModel, extra="forbid"):
    result: _S1Result
    reasoning: _S1Reasoning

# Stage 2: Detailed complaint analysis response schema
class _S2DeptInfo(BaseModel, extra="forbid"):
    code: str
    name: str

class _S2SecondaryDept(BaseModel, extra="forbid"):
    code: str
    role: str

class _S2Complaint(BaseModel, extra="forbid"):
    is_complaint: bool
    complaint_type: str
    sub_type: str
    urgency: int
    severity: int
    primary_dept: _S2DeptInfo
    secondary_depts: List[_S2SecondaryDept]
    escalation_required: bool
    escalation_level: str
    confidence: float

class _S2Result(BaseModel, extra="forbid"):
    complaint: _S2Complaint

class _S2ReasoningStep(BaseModel, extra="forbid"):
    step_number: int
    description: str
    evidence: str
    confidence: float

class _S2Reasoning(BaseModel, extra="forbid"):
    summary: str
    steps: List[_S2ReasoningStep]
    key_factors: List[str]
    evidence_quotes: List[str]

class Stage2ResponseSchema(BaseModel, extra="forbid"):
    result: _S2Result
    reasoning: _S2Reasoning


class TwoStageResult:
    """Wrapper to make two-stage results compatible with batch job expectations."""
    def __init__(self, result: UnifiedAnalysisResult, reasoning=None):
        self.result = result
        self.reasoning = reasoning


class TwoStageAnalysisAgent(BaseAgent):
    """
    Agent for two-stage analysis:
    - Stage 1 (all reviews): Quick sentiment + category classification (~1.2s)
    - Stage 2 (complaints only): Detailed department assignment (~3-5s)

    Benefits:
    - 60-70% of reviews skip expensive Stage 2
    - +40% throughput improvement
    - Reduced prompt size per stage
    """

    AGENT_TYPE = "two_stage"
    TASK_TYPE = "unified_analysis"  # Use existing task type for LLM config
    CONFIDENCE_THRESHOLD = 0.7

    # Stage 1 configuration
    STAGE1_PROMPT_ID = "quick_classification"
    STAGE1_MAX_TOKENS = 4096  # json_schema strict 모드에서 잘림 방지 (1024→4096)

    # Stage 2 configuration
    STAGE2_PROMPT_ID = "detailed_complaint_analysis"
    STAGE2_MAX_TOKENS = 4096  # json_schema strict 모드에서 잘림 방지 (2048→4096)


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Helper agents for formatting prompts
        self._category_agent = get_category_agent()
        self._complaint_agent = get_complaint_agent()

    async def analyze(self, input_data: Dict[str, Any]):
        """
        Perform two-stage analysis.

        Args:
            input_data: Review data

        Returns:
            TwoStageResult with UnifiedAnalysisResult
        """
        # Stage 1: Quick classification (all reviews)
        stage1_result = await self._stage1_quick_classify(input_data)

        # Check if complaint based on Stage 1 results
        if self._is_potential_complaint(stage1_result):
            logger.info(f"Review is potential complaint, running Stage 2 detailed analysis")
            # Stage 2: Detailed complaint analysis (complaints only)
            stage2_result = await self._stage2_detailed_analysis(input_data, stage1_result)
            # Merge results and wrap
            unified_result = self._merge_results(stage1_result, stage2_result)
            return TwoStageResult(result=unified_result)
        else:
            logger.info(f"Review is not complaint, skipping Stage 2")
            # Non-complaint: return Stage 1 only with default complaint data
            unified_result = self._create_non_complaint_result(stage1_result)
            return TwoStageResult(result=unified_result)

    async def _stage1_quick_classify(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage 1: Quick classification (sentiment + category).

        Returns:
            Dict with sentiment and category data
        """
        # Prepare Stage 1 prompt
        prompt_vars = {
            'app_name': str(input_data.get('app_name') or 'Unknown App'),
            'rating': str(input_data.get('rating') or 'N/A'),
            'content': str(input_data.get('content') or ''),
            'categories': self._category_agent._format_categories(),
            'additional_context': str(input_data.get('additional_context') or '')
        }

        # Call LLM with Stage 1 prompt
        prompt_template = self._prompts.get(self.STAGE1_PROMPT_ID)
        prompt = prompt_template.render(**prompt_vars)

        llm_response = await self._llm.generate(
            prompt=prompt,
            task_type=self.TASK_TYPE,
            json_schema=Stage1ResponseSchema.model_json_schema(),
            generation_params={
                'max_tokens': self.STAGE1_MAX_TOKENS,
            }
        )

        # Parse Stage 1 response (already parsed by LLM client)
        if llm_response.parsed_json:
            return llm_response.parsed_json.get('result', {})
        return {}

    async def _stage2_detailed_analysis(
        self,
        input_data: Dict[str, Any],
        stage1_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 2: Detailed complaint analysis (department assignment).

        Args:
            input_data: Original review data
            stage1_result: Results from Stage 1

        Returns:
            Dict with complaint data
        """
        sentiment_data = stage1_result.get('sentiment', {})
        category_data = stage1_result.get('category', {})

        # Prepare Stage 2 prompt
        prompt_vars = {
            'app_name': str(input_data.get('app_name') or 'Unknown App'),
            'content': str(input_data.get('content') or ''),
            'sentiment_label': sentiment_data.get('sentiment_label', 'neutral'),
            'primary_category': category_data.get('primary_category', 'other'),
            'department_codes': self._complaint_agent._format_department_codes(),
            'secondary_categories': str(category_data.get('secondary_categories', [])),
            'additional_context': str(input_data.get('additional_context') or '')
        }

        # Call LLM with Stage 2 prompt
        prompt_template = self._prompts.get(self.STAGE2_PROMPT_ID)
        prompt = prompt_template.render(**prompt_vars)

        llm_response = await self._llm.generate(
            prompt=prompt,
            task_type=self.TASK_TYPE,
            json_schema=Stage2ResponseSchema.model_json_schema(),
            generation_params={
                'max_tokens': self.STAGE2_MAX_TOKENS,
            }
        )

        # Parse Stage 2 response (already parsed by LLM client)
        if llm_response.parsed_json:
            return llm_response.parsed_json.get('result', {})
        return {}

    # Common LLM mistakes → Correct complaint types (defensive mapping)
    COMPLAINT_TYPE_MAPPINGS = {
        'performance': ComplaintType.DISSATISFACTION,
        '성능': ComplaintType.DISSATISFACTION,
        'speed': ComplaintType.DISSATISFACTION,
        'stability': ComplaintType.ERROR_REPORT,
        '안정성': ComplaintType.ERROR_REPORT,
    }

    def _parse_escalation_level(self, level_string: str, default: EscalationLevel = EscalationLevel.STAFF) -> EscalationLevel:
        """
        Parse escalation level string from LLM response (handles both Korean and English).

        Args:
            level_string: Escalation level string from LLM (can be Korean or English)
            default: Default escalation level if parsing fails

        Returns:
            EscalationLevel enum
        """
        if not level_string:
            return default

        # Try Korean → English mapping first
        if level_string in ESCALATION_LEVEL_REVERSE:
            return ESCALATION_LEVEL_REVERSE[level_string]

        # Try direct EscalationLevel construction (for English strings)
        try:
            return EscalationLevel(level_string)
        except ValueError:
            logger.warning(f"Unknown escalation level: {level_string}, using default {default.value}")
            return default

    def _parse_complaint_type(self, type_string: str, default: ComplaintType = ComplaintType.GENERAL_REVIEW) -> ComplaintType:
        """
        Parse complaint type string from LLM response (handles both Korean and English).
        Includes defensive mapping for common LLM mistakes.

        Args:
            type_string: Complaint type string from LLM (can be Korean or English)
            default: Default complaint type if parsing fails

        Returns:
            ComplaintType enum
        """
        if not type_string:
            return default

        # Try defensive mapping first (common LLM mistakes)
        if type_string in self.COMPLAINT_TYPE_MAPPINGS:
            mapped_type = self.COMPLAINT_TYPE_MAPPINGS[type_string]
            logger.debug(f"Mapped complaint type: {type_string} → {mapped_type.value}")
            return mapped_type

        # Try Korean → English mapping
        if type_string in COMPLAINT_TYPE_REVERSE:
            return COMPLAINT_TYPE_REVERSE[type_string]

        # Try direct ComplaintType construction (for English strings)
        try:
            return ComplaintType(type_string)
        except ValueError:
            logger.warning(f"Unknown complaint type: {type_string}, using default {default.value}")
            return default

    def _is_potential_complaint(self, stage1_result: Dict[str, Any]) -> bool:
        """
        Determine if review is a potential complaint based on Stage 1 results.

        Heuristic:
        - Negative sentiment (very_negative, negative)
        - Low sentiment score (configurable via TWO_STAGE_SENTIMENT_THRESHOLD)
        - Specific emotions (anger, frustration, disappointment)

        Args:
            stage1_result: Stage 1 classification results

        Returns:
            True if likely complaint, False otherwise
        """
        sentiment_data = stage1_result.get('sentiment', {})

        # Get threshold from environment (default: 2)
        threshold = int(os.getenv('TWO_STAGE_SENTIMENT_THRESHOLD', '2'))

        # Check sentiment label
        sentiment_label = sentiment_data.get('sentiment_label', 'neutral').lower()
        if sentiment_label in ['very_negative', 'negative']:
            return True

        # Check sentiment score (configurable threshold)
        sentiment_score = sentiment_data.get('sentiment_score', 3)
        if sentiment_score <= threshold:
            return True

        # Check emotions
        emotions = sentiment_data.get('emotions', [])
        complaint_emotions = {'anger', 'frustration', 'disappointment', 'dissatisfaction'}
        if any(emotion.lower() in complaint_emotions for emotion in emotions):
            return True

        return False

    def _merge_results(
        self,
        stage1_result: Dict[str, Any],
        stage2_result: Dict[str, Any]
    ) -> UnifiedAnalysisResult:
        """
        Merge Stage 1 and Stage 2 results.

        Args:
            stage1_result: Sentiment + Category from Stage 1
            stage2_result: Complaint details from Stage 2

        Returns:
            UnifiedAnalysisResult
        """
        # Parse sentiment
        sentiment_data = stage1_result.get('sentiment', {})
        label_str = sentiment_data.get('sentiment_label', 'neutral').lower()

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

        sentiment = SentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_data.get('sentiment_score', 3),
            emotions=sentiment_data.get('emotions', []),  # Pass-through, trust LLM output
            confidence=sentiment_data.get('confidence', 0.7)
        )

        # Parse category
        category_data = stage1_result.get('category', {})
        category = CategoryResult(
            primary_category=category_data.get('primary_category', 'other'),
            secondary_categories=category_data.get('secondary_categories', []),
            metrics=ReviewMetrics(),  # Default empty metrics for two-stage
            confidence=category_data.get('confidence', 0.7)
        )

        # Parse complaint (from Stage 2)
        complaint_data = stage2_result.get('complaint', {})
        primary_dept_data = complaint_data.get('primary_dept', {})

        complaint = ComplaintResult(
            is_complaint=complaint_data.get('is_complaint', True),
            complaint_type=self._parse_complaint_type(
                complaint_data.get('complaint_type', '불만'),
                default=ComplaintType.DISSATISFACTION
            ),
            sub_type=complaint_data.get('sub_type', ''),
            urgency=UrgencyLevel(complaint_data.get('urgency', 2)),
            severity=complaint_data.get('severity', 3),
            primary_dept=DepartmentInfo(
                code=primary_dept_data.get('code', 'CS_CENTER'),
                name=primary_dept_data.get('name', '고객센터')
            ),
            secondary_depts=[
                DepartmentInfo(code=d.get('code', ''), name=d.get('name', ''))
                for d in complaint_data.get('secondary_depts', [])
            ],
            escalation_required=complaint_data.get('escalation_required', False),
            escalation_level=self._parse_escalation_level(
                complaint_data.get('escalation_level', '담당자'),
                default=EscalationLevel.STAFF
            ),
            confidence=complaint_data.get('confidence', 0.7)
        )

        # Overall confidence (average of stage confidences)
        overall_confidence = (sentiment.confidence + category.confidence + complaint.confidence) / 3

        return UnifiedAnalysisResult(
            sentiment=sentiment,
            category=category,
            complaint=complaint,
            confidence=overall_confidence
        )

    def _create_non_complaint_result(self, stage1_result: Dict[str, Any]) -> UnifiedAnalysisResult:
        """
        Create result for non-complaint reviews (Stage 1 only).

        Args:
            stage1_result: Sentiment + Category from Stage 1

        Returns:
            UnifiedAnalysisResult with default complaint data
        """
        # Parse sentiment
        sentiment_data = stage1_result.get('sentiment', {})
        label_str = sentiment_data.get('sentiment_label', 'neutral').lower()

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

        sentiment = SentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_data.get('sentiment_score', 3),
            emotions=sentiment_data.get('emotions', []),  # Pass-through, trust LLM output
            confidence=sentiment_data.get('confidence', 0.7)
        )

        # Parse category
        category_data = stage1_result.get('category', {})
        category = CategoryResult(
            primary_category=category_data.get('primary_category', 'other'),
            secondary_categories=category_data.get('secondary_categories', []),
            metrics=ReviewMetrics(),
            confidence=category_data.get('confidence', 0.7)
        )

        # Default complaint data for non-complaints
        complaint = ComplaintResult(
            is_complaint=False,
            complaint_type=ComplaintType.GENERAL_REVIEW,
            sub_type='',
            urgency=UrgencyLevel.LOW,
            severity=1,
            primary_dept=DepartmentInfo(code="CS_CENTER", name="고객센터"),
            secondary_depts=[],
            escalation_required=False,
            escalation_level=EscalationLevel.STAFF,
            confidence=0.9  # High confidence for non-complaint
        )

        overall_confidence = (sentiment.confidence + category.confidence + complaint.confidence) / 3

        return UnifiedAnalysisResult(
            sentiment=sentiment,
            category=category,
            complaint=complaint,
            confidence=overall_confidence
        )

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Not used in two-stage agent (uses stage-specific prompt preparation).
        Kept for interface compatibility.
        """
        return {}

    def _parse_result(self, parsed_json: Dict[str, Any]) -> UnifiedAnalysisResult:
        """
        Not used in two-stage agent (uses _merge_results and _create_non_complaint_result).
        Kept for interface compatibility.
        """
        return UnifiedAnalysisResult(
            sentiment=SentimentResult(sentiment_label=SentimentLabel.NEUTRAL, sentiment_score=3, emotions=[], confidence=0.0),
            category=CategoryResult(primary_category='other', secondary_categories=[], metrics=ReviewMetrics(), confidence=0.0),
            complaint=ComplaintResult(is_complaint=False, complaint_type=ComplaintType.GENERAL_REVIEW, urgency=UrgencyLevel.LOW, severity=1, primary_dept=DepartmentInfo(code="CS_CENTER", name="고객센터"), secondary_depts=[], escalation_required=False, confidence=0.0),
            confidence=0.0
        )

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """
        Extract overall confidence from parsed response.

        Args:
            parsed_json: Parsed JSON response

        Returns:
            Confidence score (0.0-1.0)
        """
        # Try to get result.confidence first
        if isinstance(parsed_json, dict):
            result = parsed_json.get('result', {})
            if isinstance(result, dict) and 'confidence' in result:
                return float(result.get('confidence', 0.7))

        # Default confidence for two-stage analysis
        return 0.7


# Factory function for dependency injection
_two_stage_agent_instance: Optional[TwoStageAnalysisAgent] = None


def get_two_stage_agent() -> TwoStageAnalysisAgent:
    """
    Get or create TwoStageAnalysisAgent instance (singleton pattern).

    Returns:
        TwoStageAnalysisAgent instance
    """
    global _two_stage_agent_instance
    if _two_stage_agent_instance is None:
        _two_stage_agent_instance = TwoStageAnalysisAgent()
    return _two_stage_agent_instance
