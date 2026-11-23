"""
Analysis Failure Logger
Tracks LLM analysis failures for debugging and improvement.
Based on groq_model_guide.md lines 562-576
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class AnalysisFailureRecord:
    """Record of a failed analysis attempt."""
    timestamp: str
    agent_type: str
    review_id: Optional[str]
    error_type: str
    error_message: str
    fallback_strategy: str  # "none", "partial", "default"
    review_snippet: str
    model: str
    provider: str
    retry_count: int
    original_content: Optional[str] = None


class AnalysisFailureLogger:
    """
    Logger for tracking analysis failures.
    Writes failures to JSONL file for analysis.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "analysis_failures.jsonl"

    def log_failure(
        self,
        agent_type: str,
        error: Exception,
        review_data: Dict[str, Any],
        fallback_strategy: str,
        llm_response: Optional[str] = None,
        model: str = "unknown",
        provider: str = "unknown",
        retry_count: int = 0
    ):
        """
        Log a failure to JSONL file.

        Args:
            agent_type: Type of agent (sentiment, category, complaint, unified)
            error: Exception that occurred
            review_data: Original review data
            fallback_strategy: Which fallback was used ("none", "partial", "default")
            llm_response: Full LLM response for debugging
            model: Model name
            provider: Provider name (groq, gemini, etc)
            retry_count: Number of retries attempted
        """
        record = AnalysisFailureRecord(
            timestamp=datetime.now().isoformat(),
            agent_type=agent_type,
            review_id=review_data.get('review_id'),
            error_type=type(error).__name__,
            error_message=str(error)[:500],
            fallback_strategy=fallback_strategy,
            review_snippet=str(review_data.get('content', ''))[:200],
            model=model,
            provider=provider,
            retry_count=retry_count,
            original_content=llm_response[:1000] if llm_response else None
        )

        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + '\n')
            logger.debug(f"Logged failure for {agent_type}: {record.error_type}")
        except Exception as e:
            logger.error(f"Failed to write failure log: {e}")

    def get_failure_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get failure statistics for the last N hours.

        Returns:
            dict with failure counts by agent_type, error_type, provider
        """
        from datetime import timedelta

        if not self.log_file.exists():
            return {"total": 0}

        cutoff = datetime.now() - timedelta(hours=hours)
        stats = {
            "total": 0,
            "by_agent": {},
            "by_error": {},
            "by_provider": {},
            "by_fallback": {}
        }

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    record = json.loads(line)
                    record_time = datetime.fromisoformat(record['timestamp'])

                    if record_time < cutoff:
                        continue

                    stats["total"] += 1
                    stats["by_agent"][record['agent_type']] = stats["by_agent"].get(record['agent_type'], 0) + 1
                    stats["by_error"][record['error_type']] = stats["by_error"].get(record['error_type'], 0) + 1
                    stats["by_provider"][record['provider']] = stats["by_provider"].get(record['provider'], 0) + 1
                    stats["by_fallback"][record['fallback_strategy']] = stats["by_fallback"].get(record['fallback_strategy'], 0) + 1
        except Exception as e:
            logger.error(f"Error computing failure stats: {e}")

        return stats


# Singleton instance
_failure_logger: Optional[AnalysisFailureLogger] = None


def get_failure_logger() -> AnalysisFailureLogger:
    """Get singleton failure logger instance."""
    global _failure_logger
    if _failure_logger is None:
        _failure_logger = AnalysisFailureLogger()
    return _failure_logger
