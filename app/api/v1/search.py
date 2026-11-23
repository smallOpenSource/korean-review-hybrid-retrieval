"""
Search and Query API endpoints.
"""

from flask import jsonify, request
from . import api_bp
from app.api.models_extended import SearchRequest, NaturalLanguageQueryRequest
from app.utils.validation import validate_request_body
from app.constants import ResponseStatus, success_response, error_response


@api_bp.route('/search', methods=['POST'])
@validate_request_body(SearchRequest)
def search_reviews(validated_data: SearchRequest):
    """Hybrid search (keyword + vector) for reviews.

    Body validated by SearchRequest:
    - query: str (optional, max 500 chars)
    - k: int (1-100, default: 10)
    - min_score: float (0.0-1.0, default: 0.0)
    - filters: dict (optional)
    """
    try:
        query = validated_data.query
        k = validated_data.k
        min_score = validated_data.min_score
        filters = validated_data.filters

        if not query:
            # Graceful handling for empty query
            return jsonify(success_response({
                'query': '',
                'results': []
            }))

        from app.services.review_service import get_review_service

        service = get_review_service()
        results = service.search_similar(
            query_text=query,
            k=k,
            min_score=min_score,
            filters=filters
        )

        return jsonify(success_response({
            'query': query,
            'results': results
        }))
    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='SEARCH_ERROR'
        )), 500


@api_bp.route('/query', methods=['POST'])
@validate_request_body(NaturalLanguageQueryRequest)
async def natural_language_query(validated_data: NaturalLanguageQueryRequest):
    """Process natural language query.

    Body validated by NaturalLanguageQueryRequest:
    - query: str (required, 1-1000 chars, whitespace validated)
    """
    try:
        query = validated_data.query

        from app.agents.query_agent import QueryAgent
        
        # Initialize agent
        agent = QueryAgent()
        
        # Prepare input
        input_data = {
            "user_query": query,
            "available_data": "App reviews with fields: rating (1-5), content, sentiment (positive/neutral/negative), category (login, transfer, etc.), date.",
            "context": "You are an AI assistant analyzing app reviews for a banking application."
        }
        
        # Execute analysis
        result = await agent.analyze(input_data)

        return jsonify(success_response({
            'query': query,
            'answer': result.result.get('answer'),
            'data_used': result.result.get('data_used', []),
            'confidence': result.confidence
        }))

    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='QUERY_ERROR'
        )), 500
