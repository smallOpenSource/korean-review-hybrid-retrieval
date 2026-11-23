"""
Insight Generation Agent.
Generates actionable insights from aggregated review data.
"""

from typing import Dict, Any, List, Optional

from app.agents.base_agent import BaseAgent
from app.schemas.llm import (
    InsightResult, KeyInsight, RootCause, Recommendation,
    ImpactLevel, TrendDirection
)


class InsightAgent(BaseAgent):
    """
    Agent for generating insights from aggregated review data.

    Provides:
    - Executive summary for management
    - Key insights with trends
    - Root cause analysis
    - Prioritized recommendations
    """

    AGENT_TYPE = "insight"
    TASK_TYPE = "insight_generation"
    PROMPT_TEMPLATE_ID = "insight_generation"
    CONFIDENCE_THRESHOLD = 0.6  # Lower threshold as insights are aggregated

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare variables for insight generation prompt."""
        return {
            'app_name': input_data.get('app_name', 'Unknown App'),
            'period': input_data.get('period', '최근 30일'),
            'review_summary': self._format_summary(input_data.get('review_summary', {})),
            'sentiment_distribution': self._format_distribution(
                input_data.get('sentiment_distribution', {})
            ),
            'top_issues': self._format_issues(input_data.get('top_issues', [])),
            'top_praises': self._format_praises(input_data.get('top_praises', [])),
            'comparison_period': input_data.get('comparison_period', ''),
            'competitor_data': input_data.get('competitor_data', '')
        }

    def _format_summary(self, summary: Dict[str, Any]) -> str:
        """Format review summary for prompt."""
        total = summary.get('total_reviews', 0)
        avg_rating = summary.get('average_rating', 0)
        complaint_rate = summary.get('complaint_rate', 0)

        return f"""
총 리뷰 수: {total}
평균 평점: {avg_rating:.1f}/5
민원 비율: {complaint_rate:.1%}
""".strip()

    def _format_distribution(self, distribution: Dict[str, Any]) -> str:
        """Format sentiment distribution for prompt."""
        lines = []
        for label, count in distribution.items():
            lines.append(f"- {label}: {count}")
        return "\n".join(lines) if lines else "데이터 없음"

    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        """Format top issues for prompt."""
        lines = []
        for i, issue in enumerate(issues[:10], 1):
            topic = issue.get('topic', '')
            count = issue.get('count', 0)
            example = issue.get('example', '')
            lines.append(f"{i}. {topic} ({count}건)")
            if example:
                lines.append(f"   예시: \"{example[:50]}...\"")
        return "\n".join(lines) if lines else "데이터 없음"

    def _format_praises(self, praises: List[Dict[str, Any]]) -> str:
        """Format top praises for prompt."""
        lines = []
        for i, praise in enumerate(praises[:10], 1):
            topic = praise.get('topic', '')
            count = praise.get('count', 0)
            lines.append(f"{i}. {topic} ({count}건)")
        return "\n".join(lines) if lines else "데이터 없음"

    def _parse_result(self, parsed_json: Dict[str, Any]) -> InsightResult:
        """Parse insight result from LLM response."""
        result_data = parsed_json if isinstance(parsed_json, dict) else {}

        # Parse executive summary
        executive_summary = result_data.get('executive_summary', '')

        # Parse key insights
        insights_data = result_data.get('key_insights', [])
        key_insights = [
            self._parse_insight(i) for i in insights_data
        ]

        # Parse root causes
        causes_data = result_data.get('root_causes', [])
        root_causes = [
            self._parse_root_cause(c) for c in causes_data
        ]

        # Parse recommendations
        recs_data = result_data.get('recommendations', [])
        recommendations = [
            self._parse_recommendation(r) for r in recs_data
        ]

        return InsightResult(
            executive_summary=executive_summary,
            key_insights=key_insights,
            root_causes=root_causes,
            recommendations=recommendations
        )

    def _parse_insight(self, data: Dict[str, Any]) -> KeyInsight:
        """Parse key insight from response."""
        impact_str = data.get('impact', 'medium').lower()
        try:
            impact = ImpactLevel(impact_str)
        except ValueError:
            impact = ImpactLevel.MEDIUM

        trend_str = data.get('trend', 'stable').lower()
        try:
            trend = TrendDirection(trend_str)
        except ValueError:
            trend = TrendDirection.STABLE

        return KeyInsight(
            title=data.get('title', ''),
            description=data.get('description', ''),
            impact=impact,
            trend=trend
        )

    def _parse_root_cause(self, data: Dict[str, Any]) -> RootCause:
        """Parse root cause from response."""
        return RootCause(
            issue=data.get('issue', ''),
            cause=data.get('cause', ''),
            evidence=data.get('evidence', '')
        )

    def _parse_recommendation(self, data: Dict[str, Any]) -> Recommendation:
        """Parse recommendation from response."""
        priority = int(data.get('priority', 3))
        priority = max(1, min(5, priority))

        return Recommendation(
            title=data.get('title', ''),
            description=data.get('description', ''),
            priority=priority,
            expected_impact=data.get('expected_impact', ''),
            responsible_dept=data.get('responsible_dept', '')
        )

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract confidence - insights use reasoning-based confidence."""
        reasoning = parsed_json.get('reasoning', {})
        limitations = reasoning.get('limitations', [])

        # Base confidence
        confidence = 0.7

        # Reduce confidence based on limitations
        confidence -= len(limitations) * 0.05

        return max(0.3, min(1.0, confidence))

    def _should_flag_for_review(
        self,
        confidence: float,
        result: InsightResult,
        reasoning
    ) -> bool:
        """Determine if insight result needs human review."""
        # Flag if executive summary is too short
        if len(result.executive_summary) < 50:
            return True

        # Flag if no insights generated
        if not result.key_insights:
            return True

        # Flag if no recommendations
        if not result.recommendations:
            return True

        # Flag high-priority recommendations
        high_priority_recs = [r for r in result.recommendations if r.priority >= 4]
        if high_priority_recs:
            return True

        return super()._should_flag_for_review(confidence, result, reasoning)


def get_insight_agent() -> InsightAgent:
    """Get singleton InsightAgent instance."""
    return InsightAgent()
