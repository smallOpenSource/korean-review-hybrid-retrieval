"""
Sentiment Analysis Agent.
Analyzes review text to determine sentiment and emotions.
"""

from typing import Dict, Any, List, Optional

from app.agents.base_agent import BaseAgent
from app.schemas.llm import SentimentResult, SentimentLabel, SENTIMENT_LABEL_MAPPINGS


class SentimentAgent(BaseAgent):
    """
    Agent for analyzing sentiment in app reviews.

    Uses Gemini LLM to analyze:
    - Sentiment classification (5 levels)
    - Sentiment score (1-5)
    - Detected emotions
    - Confidence score
    """

    AGENT_TYPE = "sentiment"
    TASK_TYPE = "sentiment_analysis"
    PROMPT_TEMPLATE_ID = "sentiment_analysis"
    CONFIDENCE_THRESHOLD = 0.7

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare variables for sentiment analysis prompt."""
        return {
            'app_name': input_data.get('app_name', 'Unknown App'),
            'rating': input_data.get('rating', 'N/A'),
            'content': input_data.get('content', ''),
            'additional_context': input_data.get('additional_context', '')
        }

    def _parse_result(self, parsed_json: Dict[str, Any]) -> SentimentResult:
        """Parse sentiment result from LLM response."""
        result_data = parsed_json if isinstance(parsed_json, dict) else {}

        # Parse sentiment label
        label_str = result_data.get('sentiment_label', 'neutral').lower()

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

        # Parse sentiment score
        sentiment_score = int(result_data.get('sentiment_score', 3))
        sentiment_score = max(1, min(5, sentiment_score))  # Clamp to 1-5

        # Parse emotions (pass-through, trust LLM output)
        emotions = result_data.get('emotions', [])

        confidence = float(result_data.get('confidence', 0.5))

        # Create Pydantic model
        return SentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            emotions=emotions,
            confidence=confidence
        )

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract confidence from parsed response."""
        result = parsed_json.get('result', {})
        return float(result.get('confidence', 0.5))

    def _should_flag_for_review(
        self,
        confidence: float,
        result: SentimentResult,
        reasoning
    ) -> bool:
        """Determine if sentiment result needs human review."""
        # Low confidence
        if confidence < self.CONFIDENCE_THRESHOLD:
            return True

        # Mismatch between label and score
        label_score_map = {
            SentimentLabel.VERY_NEGATIVE: (1, 2),
            SentimentLabel.NEGATIVE: (2,),
            SentimentLabel.NEUTRAL: (3,),
            SentimentLabel.POSITIVE: (4,),
            SentimentLabel.VERY_POSITIVE: (4, 5)
        }
        expected_scores = label_score_map.get(result.sentiment_label, (3,))
        if result.sentiment_score not in expected_scores:
            return True

        # Contradictory emotions (e.g., anger + gratitude)
        positive_emotions = {EmotionType.SATISFACTION, EmotionType.GRATITUDE, EmotionType.EXCITEMENT}
        negative_emotions = {EmotionType.ANGER, EmotionType.FRUSTRATION, EmotionType.DISAPPOINTMENT}

        has_positive = bool(set(result.emotions) & positive_emotions)
        has_negative = bool(set(result.emotions) & negative_emotions)

        if has_positive and has_negative:
            return True

        return super()._should_flag_for_review(confidence, result, reasoning)


def get_sentiment_agent() -> SentimentAgent:
    """Get singleton SentimentAgent instance."""
    return SentimentAgent()
