"""
Reviews API endpoints.
"""

import asyncio
import logging
from datetime import datetime
from flask import jsonify, request

from . import api_bp
from app.services.review_service import get_review_service
from app.services.similar_review_service import get_similar_review_service
from app.api.models_extended import ReviewQueryParams, SimilarReviewRequest
from app.utils.validation import validate_query_params, validate_request_body
from app.constants import ResponseStatus, success_response, error_response

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async coroutine in sync context"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)





@api_bp.route('/reviews', methods=['GET'])
@validate_query_params(ReviewQueryParams)
def get_reviews(validated_params: ReviewQueryParams):
    """
    Get list of reviews with filtering and pagination.

    Query params validated by ReviewQueryParams:
    - app_id: Filter by app ID
    - sentiment: Filter by sentiment label
    - is_complaint: Filter complaints only (true/false)
    - date_from: Start date (ISO format)
    - date_to: End date (ISO format)
    - page: Page number (default: 1, range: 1-10000)
    - size: Page size (default: 20, range: 1-100)
    """
    try:
        # Use validated parameters
        app_id = validated_params.app_id
        sentiment = validated_params.sentiment
        is_complaint = validated_params.is_complaint
        date_from = validated_params.date_from
        date_to = validated_params.date_to
        page = validated_params.page
        size = validated_params.size

        # Build OpenSearch query
        filters = [{"term": {"is_duplicate": False}}]

        if app_id:
            filters.append({"term": {"app_id": app_id}})
        if sentiment:
            filters.append({"term": {"sentiment.label": sentiment.value}})
        if is_complaint is not None:
            filters.append({"term": {"complaint.is_complaint": is_complaint}})
        if date_from or date_to:
            date_filter = {"range": {"review_date": {}}}
            if date_from:
                date_filter["range"]["review_date"]["gte"] = date_from.isoformat()
            if date_to:
                date_filter["range"]["review_date"]["lte"] = date_to.isoformat()
            filters.append(date_filter)

        query = {
            "from": (page - 1) * size,
            "size": size,
            "query": {"bool": {"filter": filters}},
            "sort": [{"review_date": {"order": "desc"}}],
            "_source": {
                "excludes": ["content_embedding", "word_counts"]
            }
        }

        # Execute query
        service = get_review_service()
        response = service._os.sync_client.search(index=service._index, body=query)

        total = response['hits']['total']['value']
        reviews = [hit['_source'] for hit in response['hits']['hits']]

        return jsonify(success_response({
            'reviews': reviews,
            'pagination': {
                'page': page,
                'size': size,
                'total': total,
                'total_pages': (total + size - 1) // size
            }
        }))

    except Exception as e:
        logger.error(f"Error fetching reviews: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='FETCH_REVIEWS_ERROR'
        )), 500


@api_bp.route('/reviews/<review_id>', methods=['GET'])
def get_review(review_id: str):
    """Get a single review by ID."""
    try:
        service = get_review_service()
        review = run_async(service.get_review(review_id))

        if not review:
            return jsonify(error_response(
                message='Review not found',
                error_code='REVIEW_NOT_FOUND'
            )), 404

        # Remove large fields from response
        review.pop('content_embedding', None)
        review.pop('word_counts', None)

        return jsonify(success_response(review))

    except Exception as e:
        logger.error(f"Error fetching review {review_id}: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='FETCH_REVIEW_ERROR'
        )), 500


@api_bp.route('/reviews/<review_id>/similar', methods=['GET'])
def get_similar_reviews(review_id: str):
    """
    Get reviews similar to the specified review.

    Query params:
    - k: Number of similar reviews (default: 10, max: 50)
    - include_trend: Include daily trend (default: true)
    - trend_days: Days for trend analysis (default: 30)
    """
    try:
        k = min(int(request.args.get('k', 10)), 50)
        include_trend = request.args.get('include_trend', 'true').lower() == 'true'
        trend_days = int(request.args.get('trend_days', 30))

        service = get_similar_review_service()
        result = run_async(service.find_similar_by_review_id(
            review_id=review_id,
            k=k,
            include_trend=include_trend,
            trend_days=trend_days
        ))

        return jsonify(success_response(result.to_dict()))

    except ValueError as e:
        return jsonify(error_response(
            message=str(e),
            error_code='INVALID_REVIEW_ID'
        )), 404
    except Exception as e:
        logger.error(f"Error finding similar reviews: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='SIMILAR_REVIEWS_ERROR'
        )), 500


@api_bp.route('/reviews/search/similar', methods=['POST'])
@validate_request_body(SimilarReviewRequest)
def search_similar_reviews(validated_data: SimilarReviewRequest):
    """
    Search for similar reviews by content.

    Request body validated by SimilarReviewRequest:
    {
        "content": "리뷰 내용 (10-2000자)",
        "app_id": "optional app filter",
        "k" or "top_k": 10 (range: 1-50),
        "min_similarity" or "threshold": 0.75 (range: 0.0-1.0)
    }
    """
    try:
        # Use validated data
        content = validated_data.content
        app_id = validated_data.app_id
        k = validated_data.top_k
        min_similarity = validated_data.threshold

        service = get_similar_review_service()
        result = run_async(service.find_similar(
            content=content,
            app_id=app_id,
            k=k,
            min_similarity=min_similarity
        ))

        return jsonify(success_response(result.to_dict()))

    except Exception as e:
        logger.error(f"Error searching similar reviews: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='SEARCH_SIMILAR_ERROR'
        )), 500
