"""
Base Agent class for all analysis agents.
Provides common functionality for LLM-based analysis with reasoning tracking.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, TypeVar, Generic, Union

from app.agents.llm_client import GeminiClient, LLMResponse, get_gemini_client
from app.config.prompts import PromptTemplates, get_prompt_templates
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ReasoningStep:
    """Single step in the reasoning process."""
    step_number: int = 1
    description: str = ""
    evidence: Union[str, List[str]] = ""
    confidence: float = 0.0


@dataclass
class Reasoning:
    """Complete reasoning information from LLM analysis."""
    summary: str
    steps: List[ReasoningStep]
    key_factors: List[str]
    evidence_quotes: List[str]
    alternative_interpretations: List[str]
    confidence_factors: Dict[str, List[str]]


    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'summary': self.summary,
            'steps': [
                {
                    'step_number': s.step_number,
                    'description': s.description,
                    'evidence': s.evidence,
                    'confidence': s.confidence
                }
                for s in self.steps
            ],
            'key_factors': self.key_factors,
            'evidence_quotes': self.evidence_quotes,
            'alternative_interpretations': self.alternative_interpretations,
            'confidence_factors': self.confidence_factors
        }


@dataclass
class AgentResult(Generic[T]):
    """Result from an agent analysis."""
    # Identification
    analysis_id: str
    agent_type: str
    timestamp: datetime

    # Input/Output
    input_data: Dict[str, Any]
    result: T
    raw_response: str

    # LLM Metadata
    model_used: str
    is_secondary_model: bool
    input_tokens: int
    output_tokens: int
    latency_ms: int

    # Reasoning (for prompt improvement)
    reasoning: Reasoning
    confidence: float

    # Quality flags
    is_low_confidence: bool
    needs_review: bool

    # Prompt tracking
    prompt_template_id: str
    prompt_version: str

    def to_storage_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for OpenSearch storage."""
        # Use Pydantic model_dump() for reasoning
        reasoning_dict = (
            self.reasoning.model_dump()
            if hasattr(self.reasoning, 'model_dump')
            else self.reasoning.to_dict()
        )

        return {
            'analysis_id': self.analysis_id,
            'analysis_type': self.agent_type,
            'analyzed_at': self.timestamp.isoformat(),
            'model_name': self.model_used,
            'is_secondary_model': self.is_secondary_model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'latency_ms': self.latency_ms,
            'confidence_score': self.confidence,
            'is_low_confidence': self.is_low_confidence,
            'needs_review': self.needs_review,
            'prompt_template_id': self.prompt_template_id,
            'prompt_version': self.prompt_version,
            'reasoning': reasoning_dict,
            'feedback': None  # To be filled by human review
        }


class BaseAgent(ABC):
    """
    Base class for all analysis agents.
    Provides common LLM interaction and reasoning tracking.
    """

    # Override in subclasses
    AGENT_TYPE: str = "base"
    TASK_TYPE: str = "sentiment_analysis"
    PROMPT_TEMPLATE_ID: str = "sentiment_analysis"
    RESPONSE_SCHEMA: Optional[type] = None  # NEW: Pydantic model for response schema

    def __init__(
        self,
        llm_client: Optional[GeminiClient] = None,
        prompt_templates: Optional[PromptTemplates] = None
    ):
        self._llm = llm_client or get_gemini_client()
        self._prompts = prompt_templates or get_prompt_templates()
        self._settings = get_settings()
        # 동적으로 임계값 로드
        self._confidence_threshold = self._get_confidence_threshold()

    def _get_confidence_threshold(self) -> float:
        """Get confidence threshold from settings."""
        thresholds = self._settings.agent_thresholds
        threshold_map = {
            'sentiment': thresholds.sentiment,
            'category': thresholds.category,
            'complaint': thresholds.complaint,
            'insight': thresholds.insight,
            'unified': thresholds.unified,
            'base': thresholds.base
        }
        return threshold_map.get(self.AGENT_TYPE, thresholds.base)

    @abstractmethod
    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare variables for prompt template.
        Override in subclasses to provide task-specific variables.
        """
        pass

    @abstractmethod
    def _parse_result(self, parsed_json: Dict[str, Any]) -> Any:
        """
        Parse the result field from LLM response.
        Override in subclasses to convert to task-specific types.
        """
        pass

    @abstractmethod
    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """
        Extract confidence score from parsed response.
        Override in subclasses for task-specific confidence extraction.
        """
        pass

    def _should_flag_for_review(
        self,
        confidence: float,
        result: Any,
        reasoning: Reasoning
    ) -> bool:
        """
        Determine if result should be flagged for human review.
        Can be overridden for task-specific logic.
        """
        # Low confidence
        if confidence < self._confidence_threshold:
            return True

        # High uncertainty in reasoning
        if reasoning.alternative_interpretations:
            return True

        # Negative confidence factors outweigh positive
        neg_factors = len(reasoning.confidence_factors.get('negative', []))
        pos_factors = len(reasoning.confidence_factors.get('positive', []))
        if neg_factors > pos_factors:
            return True

        return False

    def _create_partial_result(
        self,
        parsed_json: Dict[str, Any],
        confidence: float = 0.5
    ) -> Any:
        """
        Create partial result with default values for missing fields.
        Override in subclasses for agent-specific logic.

        Args:
            parsed_json: Partially parsed JSON
            confidence: Default confidence for missing values

        Returns:
            Agent-specific result object
        """
        # Default implementation - subclasses should override
        try:
            result_data = parsed_json.get('result', {})
            return self._parse_result(result_data)
        except Exception as e:
            logger.warning(f"Partial parsing failed: {e}")
            raise ValueError("Cannot create partial result")

    def _create_default_result(self, input_data: Dict[str, Any]) -> Any:
        """
        Create default result based on input data only.
        Override in subclasses for agent-specific defaults.

        Args:
            input_data: Original input data

        Returns:
            Agent-specific result with default values
        """
        # Default implementation - subclasses must override
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _create_default_result()"
        )

    async def analyze(self, input_data: Dict[str, Any], enable_fallback: bool = True) -> AgentResult:
        """
        Perform analysis on input data with multi-strategy fallback.

        Implements Layer 5 from groq_model_guide.md (lines 305-436):
        - Strategy 1: Strict (full Pydantic validation)
        - Strategy 2: Relaxed (partial validation)
        - Strategy 3: Default (rating-based fallback)

        Args:
            input_data: Dictionary containing input fields
            enable_fallback: Whether to use fallback strategies (default=True)

        Returns:
            AgentResult with analysis result and reasoning
        """
        analysis_id = f"ana_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Prepare prompt
        prompt_template = self._prompts.get(self.PROMPT_TEMPLATE_ID)
        prompt_variables = self._prepare_prompt_variables(input_data)
        prompt = prompt_template.render(**prompt_variables)

        # Extract JSON schema from Pydantic model if available
        json_schema = None
        if self.RESPONSE_SCHEMA is not None:
            try:
                json_schema = self.RESPONSE_SCHEMA.model_json_schema()
                logger.debug(f"Using Pydantic schema for {self.AGENT_TYPE}")
            except Exception as e:
                logger.warning(f"Failed to extract schema: {e}")

        # NEW: Multi-strategy fallback
        fallback_strategies = ["strict", "relaxed", "default"] if enable_fallback else ["strict"]

        last_error = None
        fallback_used = "none"
        response = None
        reasoning = None
        result = None
        confidence = 0.0

        for strategy in fallback_strategies:
            try:
                if strategy == "strict":
                    # EXISTING: Full validation path
                    response = await self._llm.generate_with_retry(
                        prompt=prompt,
                        task_type=self.TASK_TYPE,
                        parse_json=True,
                        json_schema=json_schema
                    )

                    if not response.parsed_json:
                        raise ValueError("LLM returned invalid JSON")

                    # Full Pydantic validation
                    from pydantic import ValidationError
                    from app.schemas.llm import Reasoning as ReasoningModel

                    reasoning_data = response.parsed_json.get('reasoning', {})
                    reasoning = ReasoningModel.model_validate(reasoning_data)

                    result = self._parse_result(response.parsed_json.get('result', {}))
                    confidence = self._extract_confidence(response.parsed_json)

                    # SUCCESS - strict validation passed
                    fallback_used = "none"
                    break

                elif strategy == "relaxed":
                    # NEW: Try partial validation
                    logger.warning(f"{self.AGENT_TYPE}: Strict validation failed, trying relaxed")

                    # Reuse response from strict attempt if available
                    if not response or not response.parsed_json:
                        response = await self._llm.generate_with_retry(
                            prompt=prompt,
                            task_type=self.TASK_TYPE,
                            parse_json=True,
                            json_schema=json_schema
                        )

                    if not response.parsed_json:
                        raise ValueError("No JSON in relaxed attempt")

                    # Try partial result creation
                    result = self._create_partial_result(response.parsed_json, confidence=0.5)
                    confidence = 0.5

                    # Create minimal reasoning
                    from app.schemas.llm import Reasoning as ReasoningModel, ReasoningStep
                    reasoning = ReasoningModel(
                        summary="Partial parsing fallback",
                        steps=[ReasoningStep(
                            step_number=1,
                            description="Used relaxed validation due to strict failure",
                            evidence="",
                            confidence=0.5
                        )],
                        key_factors=["fallback_validation"],
                        evidence_quotes=[],
                        alternative_interpretations=[],
                        confidence_factors={"negative": ["strict_validation_failed"]}
                    )

                    fallback_used = "partial"
                    break

                elif strategy == "default":
                    # NEW: Default value generation
                    logger.warning(f"{self.AGENT_TYPE}: All parsing failed, using defaults")

                    result = self._create_default_result(input_data)
                    confidence = 0.3

                    # Create minimal reasoning
                    from app.schemas.llm import Reasoning as ReasoningModel, ReasoningStep
                    reasoning = ReasoningModel(
                        summary="Default fallback based on input data",
                        steps=[ReasoningStep(
                            step_number=1,
                            description="Used default values due to all parsing failures",
                            evidence="",
                            confidence=0.3
                        )],
                        key_factors=["default_fallback"],
                        evidence_quotes=[],
                        alternative_interpretations=[],
                        confidence_factors={"negative": ["all_validation_failed"]}
                    )

                    fallback_used = "default"
                    break

            except Exception as e:
                last_error = e
                logger.warning(f"Strategy '{strategy}' failed: {e}")
                continue

        # If all strategies failed, raise last error
        if fallback_used == "none" and last_error:
            # Log failure before raising
            from app.utils.analysis_failure_logger import get_failure_logger
            failure_logger = get_failure_logger()
            failure_logger.log_failure(
                agent_type=self.AGENT_TYPE,
                error=last_error,
                review_data=input_data,
                fallback_strategy="none",
                llm_response=response.content if response else None,
                model=response.model if response else "unknown",
                provider=response.provider if response else "unknown",
                retry_count=3
            )
            raise last_error

        # Log if fallback was used
        if fallback_used != "none":
            from app.utils.analysis_failure_logger import get_failure_logger
            failure_logger = get_failure_logger()
            failure_logger.log_failure(
                agent_type=self.AGENT_TYPE,
                error=last_error or Exception("Fallback used"),
                review_data=input_data,
                fallback_strategy=fallback_used,
                llm_response=response.content if response else None,
                model=response.model if response else "unknown",
                provider=response.provider if response else "unknown",
                retry_count=3
            )
            logger.info(
                f"{self.AGENT_TYPE} analysis {analysis_id} used fallback: {fallback_used} "
                f"(confidence: {confidence:.2f})"
            )

        # Quality flags
        is_low_confidence = confidence < self._confidence_threshold
        needs_review = self._should_flag_for_review(confidence, result, reasoning)

        if needs_review:
            logger.info(
                f"{self.AGENT_TYPE} analysis {analysis_id} flagged for review "
                f"(confidence: {confidence:.2f}, fallback: {fallback_used})"
            )

        return AgentResult(
            analysis_id=analysis_id,
            agent_type=self.AGENT_TYPE,
            timestamp=response.timestamp if response else datetime.now(),
            input_data=input_data,
            result=result,
            raw_response=response.content if response else f"Fallback: {fallback_used}",
            model_used=response.model if response else "fallback",
            is_secondary_model=response.is_secondary_model if response else True,
            input_tokens=response.input_tokens if response else 0,
            output_tokens=response.output_tokens if response else 0,
            latency_ms=response.latency_ms if response else 0,
            reasoning=reasoning,
            confidence=confidence,
            is_low_confidence=is_low_confidence,
            needs_review=needs_review,
            prompt_template_id=self.PROMPT_TEMPLATE_ID,
            prompt_version=prompt_template.version
        )

    async def analyze_batch(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> List[AgentResult]:
        """
        Analyze multiple items with batching.

        Args:
            items: List of input data dictionaries
            batch_size: Number of items to process concurrently

        Returns:
            List of AgentResult
        """
        import asyncio

        results = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[self.analyze(item) for item in batch],
                return_exceptions=True
            )

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Batch analysis failed for item {i + j}: {result}")
                else:
                    results.append(result)

            logger.info(f"Processed batch {i // batch_size + 1}, total: {len(results)}")

        return results
