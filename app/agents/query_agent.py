"""
Query Agent for Natural Language Processing.
"""

import logging
from typing import Dict, Any, List, Optional

from pydantic import ValidationError

from app.agents.base_agent import BaseAgent, AgentResult
from app.schemas.llm import QueryResult

logger = logging.getLogger(__name__)


class QueryAgent(BaseAgent):
    """
    Agent for processing natural language queries about review data.
    """
    
    AGENT_TYPE = "query_agent"
    TASK_TYPE = "natural_language_query"
    PROMPT_TEMPLATE_ID = "natural_language_query"
    
    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare variables for the prompt.
        
        Args:
            input_data: Dictionary containing:
                - user_query: The user's question
                - available_data: Description of available data/schema
                - context: Additional context (optional)
                
        Returns:
            Dictionary of prompt variables
        """
        return {
            "user_query": input_data.get("user_query", ""),
            "available_data": input_data.get("available_data", "Review data including rating, content, sentiment, category, and date."),
            "context": input_data.get("context", "No additional context provided."),
            "previous_queries": input_data.get("previous_queries", [])
        }

    def _parse_result(self, result_data: Dict[str, Any]) -> QueryResult:
        """
        Parse the result from LLM response using Pydantic validation.

        Args:
            result_data: The 'result' part of the LLM response

        Returns:
            QueryResult Pydantic model instance
        """
        try:
            query_result = QueryResult.model_validate(result_data)
        except ValidationError as e:
            logger.error(
                f"QueryResult validation failed: {e.error_count()} errors"
            )
            logger.error(f"Validation errors: {e.errors()}")
            raise ValueError(f"Invalid query result from LLM: {e.error_count()} validation errors")

        return query_result

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract confidence score."""
        return float(parsed_json.get("result", {}).get("confidence", 0.0))
