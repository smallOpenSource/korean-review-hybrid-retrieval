"""
Pydantic schemas for LLM interactions.
Defines data models for agent results and reasoning.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger(__name__)

class SentimentLabel(str, Enum):
    """Sentiment classification labels."""
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


# 감정 레이블 한글 매핑
SENTIMENT_LABELS = {
    SentimentLabel.VERY_NEGATIVE: "매우 부정",
    SentimentLabel.NEGATIVE: "부정",
    SentimentLabel.NEUTRAL: "중립",
    SentimentLabel.POSITIVE: "긍정",
    SentimentLabel.VERY_POSITIVE: "매우 긍정",
}


# Sentiment label defensive mapping for common LLM variations
SENTIMENT_LABEL_MAPPINGS = {
    'slightly_negative': SentimentLabel.NEGATIVE,
    'slightly_positive': SentimentLabel.POSITIVE,
    'moderately_negative': SentimentLabel.NEGATIVE,
    'moderately_positive': SentimentLabel.POSITIVE,
    'extremely_negative': SentimentLabel.VERY_NEGATIVE,
    'extremely_positive': SentimentLabel.VERY_POSITIVE,
    'somewhat_negative': SentimentLabel.NEGATIVE,
    'somewhat_positive': SentimentLabel.POSITIVE,
    'neutral_negative': SentimentLabel.NEGATIVE,
    'neutral_positive': SentimentLabel.POSITIVE,
    'mixed': SentimentLabel.NEUTRAL,
    'ambiguous': SentimentLabel.NEUTRAL,
}


def get_sentiment_label(sentiment: SentimentLabel) -> str:
    """감정 레이블 한글 반환."""
    return SENTIMENT_LABELS.get(sentiment, sentiment.value)

class ReasoningStep(BaseModel):
    """Single step in the reasoning process."""
    step_number: int = Field(default=1, description="Step number in the sequence")
    description: str = Field(default="", description="Description of the reasoning step")
    evidence: Union[str, List[str]] = Field(default="", description="Evidence from the text supporting this step")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score for this step")

class Reasoning(BaseModel):
    """Complete reasoning information from LLM analysis."""
    summary: str = Field(default="", description="Summary of the reasoning")
    steps: List[ReasoningStep] = Field(default_factory=list, description="List of reasoning steps")
    key_factors: List[str] = Field(default_factory=list, description="Key factors influencing the decision")
    evidence_quotes: List[str] = Field(default_factory=list, description="Direct quotes used as evidence")
    alternative_interpretations: List[str] = Field(default_factory=list, description="Alternative interpretations considered")
    confidence_factors: Dict[str, List[str]] = Field(default_factory=dict, description="Factors affecting confidence (positive/negative)")

class SentimentResult(BaseModel):
    """Result of sentiment analysis."""
    sentiment_label: SentimentLabel = Field(..., description="Overall sentiment label")
    sentiment_score: int = Field(..., ge=1, le=5, description="Sentiment score from 1 to 5")
    emotions: List[str] = Field(
        default_factory=list,
        description="List of detected emotions (free-text, supports Korean and English)"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")

    @field_validator('sentiment_score')
    @classmethod
    def validate_score(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError('Score must be between 1 and 5')
        return v

    @field_validator('emotions')
    @classmethod
    def validate_emotions(cls, v: List[str]) -> List[str]:
        """
        빈 문자열만 제거, LLM 출력 그대로 저장.
        중복/개수 제한 없음 - LLM 판단 신뢰.
        """
        return [e.strip() for e in v if e and e.strip()]

class MetricInfo(BaseModel):
    """Information about a detected metric."""
    detected: bool = Field(default=False, description="Whether the metric was detected")
    keywords: List[str] = Field(default_factory=list, description="Keywords triggering detection")
    sub_categories: List[str] = Field(default_factory=list, description="Detailed sub-categories")
    issues: List[str] = Field(default_factory=list, description="Specific issues identified")
    screens: List[str] = Field(default_factory=list, description="Related app screens")
    services: List[str] = Field(default_factory=list, description="Related services")

class ReviewMetrics(BaseModel):
    """Extracted metrics from review."""
    feature: MetricInfo = Field(default_factory=MetricInfo, description="Feature usage metrics")
    service: MetricInfo = Field(default_factory=MetricInfo, description="Service quality metrics")
    performance: MetricInfo = Field(default_factory=MetricInfo, description="Performance metrics")
    related_screen: MetricInfo = Field(default_factory=MetricInfo, description="Screen/UI metrics")

class CategoryResult(BaseModel):
    """Result of category classification."""
    primary_category: str = Field(..., description="Main category of the review")
    secondary_categories: List[str] = Field(default_factory=list, description="Secondary categories")
    metrics: ReviewMetrics = Field(..., description="Detailed metrics")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

    # NEW: Field validator for primary_category
    @field_validator('primary_category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Ensure category is not empty."""
        v = v.strip()
        if not v:
            logger.warning("Empty primary_category, defaulting to 'other'")
            return 'other'
        return v

    # NEW: Field validator for secondary_categories
    @field_validator('secondary_categories')
    @classmethod
    def validate_secondary(cls, v: List[str]) -> List[str]:
        """Remove duplicates and empty strings."""
        # Remove empty/whitespace-only items
        cleaned = [s.strip() for s in v if s and s.strip()]
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique[:3]  # Limit to 3 max

class ComplaintType(str, Enum):
    """Complaint type classification."""
    GENERAL_REVIEW = "general_review"
    PRAISE = "praise"
    IMPROVEMENT_REQUEST = "improvement_request"
    DISSATISFACTION = "dissatisfaction"
    ERROR_REPORT = "error_report"
    DAMAGE_REPORT = "damage_report"
    LEGAL_ISSUE = "legal_issue"


# 민원 타입 한글 매핑
COMPLAINT_TYPE_LABELS = {
    ComplaintType.GENERAL_REVIEW: "일반 리뷰",
    ComplaintType.PRAISE: "칭찬",
    ComplaintType.IMPROVEMENT_REQUEST: "개선 요청",
    ComplaintType.DISSATISFACTION: "불만",
    ComplaintType.ERROR_REPORT: "오류 신고",
    ComplaintType.DAMAGE_REPORT: "피해 신고",
    ComplaintType.LEGAL_ISSUE: "법적 문제",
}

# 민원 타입 역매핑 (한글 → 영어)
COMPLAINT_TYPE_REVERSE = {v: k for k, v in COMPLAINT_TYPE_LABELS.items()}

class UrgencyLevel(int, Enum):
    """Urgency level for complaints."""
    LOW = 1       # General request
    MEDIUM = 2    # Function error, inconvenience
    HIGH = 3      # Service outage, repeated error
    CRITICAL = 4  # Financial damage, security incident, legal

class EscalationLevel(str, Enum):
    """Escalation level for complaint handling."""
    STAFF = "staff"
    TEAM_LEAD = "team_lead"
    DEPT_HEAD = "dept_head"
    EXECUTIVE = "executive"


# 에스컬레이션 레벨 한글 매핑
ESCALATION_LEVEL_LABELS = {
    EscalationLevel.STAFF: "담당자",
    EscalationLevel.TEAM_LEAD: "팀장",
    EscalationLevel.DEPT_HEAD: "부서장",
    EscalationLevel.EXECUTIVE: "임원",
}

# 에스컬레이션 레벨 역매핑 (한글 → 영어)
ESCALATION_LEVEL_REVERSE = {v: k for k, v in ESCALATION_LEVEL_LABELS.items()}

class DepartmentInfo(BaseModel):
    """Department assignment information."""
    code: str = Field(..., description="Department code")
    name: str = Field(..., description="Department name")
    role: str = Field(default="primary", description="Role (primary, support, etc.)")
    division_name: Optional[str] = Field(None, description="Division name")
    routing_scores: Optional[Dict[str, float]] = Field(None, description="Routing scores")

class ComplaintResult(BaseModel):
    """Result of complaint classification."""
    is_complaint: bool = Field(..., description="Whether it is a complaint")
    complaint_type: ComplaintType = Field(..., description="Type of complaint")
    sub_type: Optional[str] = Field(None, description="Detailed subtype")
    urgency: UrgencyLevel = Field(..., description="Urgency level")
    severity: int = Field(..., ge=1, le=5, description="Severity 1-5")
    primary_dept: DepartmentInfo = Field(..., description="Primary department")
    secondary_depts: List[DepartmentInfo] = Field(default_factory=list, description="Secondary departments")
    escalation_required: bool = Field(..., description="Whether escalation is required")
    escalation_level: Optional[EscalationLevel] = Field(None, description="Level of escalation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    sla_hours: int = Field(default=168, description="SLA deadline in hours")
    routing_method: str = Field(default="hybrid", description="Method used for routing")

    # NEW: Field validator for severity range
    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v: int) -> int:
        """Ensure severity is within valid range."""
        if not 1 <= v <= 5:
            logger.warning(f"Invalid severity {v}, clamping to range [1,5]")
            return max(1, min(5, v))
        return v

    # NEW: Model validator for cross-field logic
    @model_validator(mode='after')
    def validate_complaint_logic(self):
        """Validate complaint logic consistency (from groq_model_guide.md)."""
        # If not a complaint, reset urgency/severity to low
        if not self.is_complaint and (self.urgency.value > 2 or self.severity > 2):
            logger.warning(
                f"Non-complaint has high urgency/severity, adjusting: "
                f"urgency {self.urgency.value}→1, severity {self.severity}→1"
            )
            self.urgency = UrgencyLevel.LOW
            self.severity = 1

        # If escalation required, ensure escalation_level is set
        if self.escalation_required and self.escalation_level is None:
            self.escalation_level = EscalationLevel.TEAM_LEAD
            logger.warning("Escalation required but level not set, defaulting to TEAM_LEAD")

        return self

class ImpactLevel(str, Enum):
    """Impact level for insights."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TrendDirection(str, Enum):
    """Trend direction."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"

class KeyInsight(BaseModel):
    """A key insight from analysis."""
    title: str = Field(..., description="Insight title")
    description: str = Field(..., description="Detailed description")
    impact: ImpactLevel = Field(..., description="Impact level")
    trend: TrendDirection = Field(..., description="Trend direction")

class RootCause(BaseModel):
    """Root cause analysis for an issue."""
    issue: str = Field(..., description="The issue being analyzed")
    cause: str = Field(..., description="Identified root cause")
    evidence: str = Field(..., description="Supporting evidence")

class Recommendation(BaseModel):
    """Actionable recommendation."""
    title: str = Field(..., description="Recommendation title")
    description: str = Field(..., description="Detailed description")
    priority: int = Field(..., ge=1, le=5, description="Priority 1-5")
    expected_impact: str = Field(..., description="Expected impact of implementation")
    responsible_dept: str = Field(..., description="Responsible department")

class InsightResult(BaseModel):
    """Result of insight generation."""
    executive_summary: str = Field(..., description="Executive summary")
    key_insights: List[KeyInsight] = Field(default_factory=list, description="List of key insights")
    root_causes: List[RootCause] = Field(default_factory=list, description="List of root causes")
    recommendations: List[Recommendation] = Field(default_factory=list, description="List of recommendations")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence score")

class UnifiedAnalysisResult(BaseModel):
    """Combined result of all analysis tasks."""
    sentiment: SentimentResult = Field(..., description="Sentiment analysis result")
    category: CategoryResult = Field(..., description="Category classification result")
    complaint: ComplaintResult = Field(..., description="Complaint classification result")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")

    # NEW: Model validator for overall confidence
    @model_validator(mode='after')
    def validate_overall_confidence(self):
        """Validate overall confidence against component confidences."""
        avg_confidence = (
            self.sentiment.confidence +
            self.category.confidence +
            self.complaint.confidence
        ) / 3

        # Overall confidence should not exceed average by more than 10%
        if self.confidence > avg_confidence + 0.1:
            logger.warning(
                f"Overall confidence {self.confidence:.2f} too high, "
                f"adjusting to average {avg_confidence:.2f}"
            )
            self.confidence = avg_confidence

        return self

class QueryResult(BaseModel):
    """Query agent result schema."""
    query: str = Field(..., description="생성된 쿼리")
    query_type: str = Field(..., description="쿼리 타입 (knn/bm25/hybrid)")
    search_params: Dict[str, Any] = Field(default_factory=dict, description="검색 파라미터")
    filters: Optional[Dict[str, Any]] = Field(None, description="필터 조건")
