"""
Analysis API endpoints.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from flask import jsonify, request

from . import api_bp
from app.services.review_service import get_review_service
from app.services.word_analysis_service import get_word_analysis_service
from app.services.dedup_service import get_dedup_service
from app.agents.sentiment_agent import SentimentAgent
from app.api.models_extended import AnalyzeRequest, DashboardQueryParams
from app.utils.validation import validate_request_body, validate_query_params
from app.constants import ResponseStatus, success_response, error_response

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@api_bp.route('/analysis/analyze', methods=['POST'])
@validate_request_body(AnalyzeRequest)
def analyze_review(validated_data: AnalyzeRequest):
    """
    Analyze a single review using SentimentAgent.

    Body validated by AnalyzeRequest:
    - content: Review content (1-5000 chars, auto-truncated to 2000)
    - analyze_sentiment: bool (default: True)
    - analyze_category: bool (default: True)
    - analyze_complaint: bool (default: True)
    """
    try:
        # Use validated and truncated content
        content = validated_data.content  # Already truncated by validator

        # Prepare data for agent (legacy format)
        data = {'content': content}

        # Initialize agent with a FRESH client to avoid event loop issues
        # caused by global singletons in a run_async (ephemeral loop) context.
        from app.agents.llm_client import UnifiedLLMClient
        fresh_client = UnifiedLLMClient()
        agent = SentimentAgent(llm_client=fresh_client)
        
        # Run analysis
        # Note: agent.analyze is async, so we run it in sync context
        result = run_async(agent.analyze(data))

        return jsonify(success_response({
            'result': result.result.model_dump(mode='json'),
            'reasoning': result.reasoning.to_dict() if hasattr(result.reasoning, 'to_dict') else {}
        }))

    except Exception as e:
        logger.error(f"Error analyzing review: {e}")
        # If it's an LLM failure, return 503
        if "Generation failed" in str(e) or "Event loop" in str(e):
             return jsonify(error_response(
                message='Analysis service temporarily unavailable. Please try again.',
                error_code='SERVICE_UNAVAILABLE'
            )), 503

        return jsonify(error_response(
            message=str(e),
            error_code='ANALYSIS_ERROR'
        )), 500


@api_bp.route('/analysis/dashboard', methods=['GET'])
@validate_query_params(DashboardQueryParams)
def get_dashboard_data(validated_params: DashboardQueryParams):
    """
    Get dashboard summary data.

    Query params validated by DashboardQueryParams:
    - category: Filter by category (optional, max 50 chars)
    - days: Number of days for analysis (default: 30, range: 1-3650)
    - year: Filter by year (optional, range: 2020-2030)
    """
    try:
        days = validated_params.days

        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

        review_service = get_review_service()

        # Get sentiment aggregation (Use sync method)
        sentiment_stats = review_service.aggregate_sentiment_sync(
            app_id=app_id,
            days=days
        )

        # Get complaint stats (Use sync method)
        complaint_stats = review_service.get_complaint_stats_sync(
            app_id=app_id,
            date_range=(date_from, date_to)
        )

        # Get duplicate stats
        dedup_service = get_dedup_service()
        dedup_stats = run_async(dedup_service.get_duplicate_stats(app_id=app_id))

        # Get word rankings for negative reviews
        word_service = get_word_analysis_service()
        negative_words = run_async(word_service.get_word_ranking(
            app_id=app_id,
            sentiment_type="negative",
            date_from=date_from,
            date_to=date_to,
            top_n=20
        ))

        return jsonify(success_response({
            'period': {
                'from': date_from.isoformat(),
                'to': date_to.isoformat(),
                'days': days
            },
            'sentiment': {
                'distribution': sentiment_stats.get('sentiment_distribution', {}).get('buckets', []),
                'average_score': sentiment_stats.get('avg_sentiment_score', {}).get('value'),
                'rating_distribution': sentiment_stats.get('rating_distribution', {}).get('buckets', []),
                'trend': sentiment_stats.get('sentiment_over_time', {}).get('buckets', [])
            },
            'complaints': {
                'by_type': complaint_stats.get('by_type', {}).get('buckets', []),
                'by_dept': complaint_stats.get('by_dept', {}).get('buckets', []),
                'by_urgency': complaint_stats.get('by_urgency', {}).get('buckets', []),
                'escalation_count': complaint_stats.get('escalation_count', {}).get('doc_count', 0),
                'daily_trend': complaint_stats.get('daily_trend', {}).get('buckets', [])
            },
            'duplicates': dedup_stats,
            'top_negative_words': negative_words.to_dict() if negative_words else {}
        }))

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='DASHBOARD_ERROR'
        )), 500


@api_bp.route('/analysis/company/<company_code>', methods=['GET'])
def get_company_analysis(company_code: str):
    """
    Get analysis for a specific company.

    Query params:
    - days: Number of days for analysis (default: 30)
    """
    try:
        days = int(request.args.get('days', 30))

        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

        # 1. Resolve company_code to package_id
        from app.services.app_service import get_app_service
        app_service = get_app_service()
        app_info = app_service.get_app_by_code(company_code)
        
        if not app_info:
            return jsonify(error_response(
                message=f'Company not found: {company_code}',
                error_code='COMPANY_NOT_FOUND'
            )), 404
            
        package_id = app_info['package_id']

        review_service = get_review_service()

        # Get sentiment stats for this company (Use Sync method)
        sentiment_stats = review_service.aggregate_sentiment_sync(
            app_id=package_id,
            days=days
        )

        # Get complaint stats (Use Sync method)
        complaint_stats = review_service.get_complaint_stats_sync(
            app_id=package_id,
            date_range=(date_from, date_to)
        )

        # Get word rankings (Use Sync method if available, otherwise keep async wrapper if service is async)
        # Checking word_analysis_service... it seems to be async based on previous code.
        # Let's check if get_word_ranking is async. 
        # Based on previous file view, it was called with run_async.
        # We will keep run_async for word_service if it's truly async.
        
        word_service = get_word_analysis_service()

        negative_words = run_async(word_service.get_word_ranking(
            app_id=package_id,
            sentiment_type="negative",
            date_from=date_from,
            date_to=date_to,
            top_n=30
        ))

        positive_words = run_async(word_service.get_word_ranking(
            app_id=package_id,
            sentiment_type="positive",
            date_from=date_from,
            date_to=date_to,
            top_n=30
        ))

        return jsonify(success_response({
            'company_code': company_code,
            'package_id': package_id,
            'period': {
                'from': date_from.isoformat(),
                'to': date_to.isoformat()
            },
            'sentiment': {
                'distribution': sentiment_stats.get('raw_aggs', {}).get('sentiment_distribution', {}).get('buckets', []),
                'average_score': sentiment_stats.get('raw_aggs', {}).get('avg_sentiment_score', {}).get('value'),
                'trend': sentiment_stats.get('sentiment_trend', [])  # Use sentiment_trend directly
            },
            'complaints': {
                'total': complaint_stats.get('by_type', {}).get('buckets', []),
                'by_dept': complaint_stats.get('by_dept', {}).get('buckets', [])
            },
            'word_analysis': {
                'negative': negative_words.to_dict() if negative_words else {},
                'positive': positive_words.to_dict() if positive_words else {}
            }
        }))

    except Exception as e:
        logger.error(f"Error fetching company analysis: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='COMPANY_ANALYSIS_ERROR'
        )), 500


@api_bp.route('/analysis/trend', methods=['GET'])
def get_trend_analysis():
    """
    Get trend analysis data.

    Query params:
    - app_id: Filter by app ID (optional)
    - metric: Metric to analyze (sentiment, complaints, rating)
    - interval: Time interval (day, week, month)
    - days: Number of days (default: 90)
    """
    try:
        app_id = request.args.get('app_id')
        metric = request.args.get('metric', 'sentiment')
        interval = request.args.get('interval', 'day')
        days = int(request.args.get('days', 90))

        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

        # Map interval to OpenSearch calendar_interval
        interval_map = {
            'day': 'day',
            'week': 'week',
            'month': 'month'
        }
        os_interval = interval_map.get(interval, 'day')

        review_service = get_review_service()

        # Build query based on metric
        filters = [{"term": {"is_duplicate": False}}]
        if app_id:
            filters.append({"term": {"app_id": app_id}})

        filters.append({
            "range": {
                "review_date": {
                    "gte": date_from.isoformat(),
                    "lte": date_to.isoformat()
                }
            }
        })

        agg_config = {
            "time_buckets": {
                "date_histogram": {
                    "field": "review_date",
                    "calendar_interval": os_interval,
                    "format": "yyyy-MM-dd"
                },
                "aggs": {}
            }
        }

        if metric == 'sentiment':
            agg_config["time_buckets"]["aggs"] = {
                "avg_score": {"avg": {"field": "sentiment.score"}},
                "by_label": {"terms": {"field": "sentiment.label"}}
            }
        elif metric == 'complaints':
            agg_config["time_buckets"]["aggs"] = {
                "complaint_count": {
                    "filter": {"term": {"complaint.is_complaint": True}}
                },
                "by_type": {"terms": {"field": "complaint.type"}}
            }
        elif metric == 'rating':
            agg_config["time_buckets"]["aggs"] = {
                "avg_rating": {"avg": {"field": "rating"}},
                "by_rating": {"terms": {"field": "rating"}}
            }

        query = {
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggs": agg_config
        }

        response = review_service._os.sync_client.search(
            index=review_service._index,
            body=query
        )

        buckets = response['aggregations']['time_buckets']['buckets']

        return jsonify(success_response({
            'metric': metric,
            'interval': interval,
            'period': {
                'from': date_from.isoformat(),
                'to': date_to.isoformat()
            },
            'trend': buckets
        }))

    except Exception as e:
        logger.error(f"Error fetching trend analysis: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='TREND_ANALYSIS_ERROR'
        )), 500


@api_bp.route('/analysis/words', methods=['GET'])
def get_word_analysis():
    """
    Get word frequency analysis.

    Query params:
    - app_id: Filter by app ID (optional)
    - sentiment_type: negative, positive, or all (default: all)
    - top_n: Number of words (default: 50)
    - days: Number of days (default: 30)
    """
    try:
        app_id = request.args.get('app_id')
        sentiment_type = request.args.get('sentiment_type', 'all')
        top_n = min(int(request.args.get('top_n', 50)), 100)
        days = int(request.args.get('days', 30))

        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=days)

        word_service = get_word_analysis_service()

        result = run_async(word_service.get_word_ranking(
            app_id=app_id,
            sentiment_type=sentiment_type,
            date_from=date_from,
            date_to=date_to,
            top_n=top_n
        ))

        return jsonify(success_response(result.to_dict()))

    except Exception as e:
        logger.error(f"Error fetching word analysis: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='WORD_ANALYSIS_ERROR'
        )), 500


@api_bp.route('/analysis/words/<word>/trend', methods=['GET'])
def get_word_trend(word: str):
    """
    Get trend for a specific word.

    Query params:
    - app_id: Filter by app ID (optional)
    - days: Number of days (default: 30)
    """
    try:
        app_id = request.args.get('app_id')
        days = int(request.args.get('days', 30))

        word_service = get_word_analysis_service()

        trend = run_async(word_service.get_word_trend(
            word=word,
            app_id=app_id,
            days=days
        ))

        return jsonify(success_response({
            'word': word,
            'days': days,
            'trend': trend
        }))

    except Exception as e:
        logger.error(f"Error fetching word trend: {e}")
        return jsonify(error_response(
            message=str(e),
            error_code='WORD_TREND_ERROR'
        )), 500
