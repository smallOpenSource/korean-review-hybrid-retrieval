"""
Dashboard API endpoints.
"""

from flask import jsonify, request
from . import api_bp
from app.services.review_service import get_review_service
from app.api.models_extended import DashboardQueryParams
from app.utils.validation import validate_query_params
from app.constants import ResponseStatus, success_response, error_response
from datetime import datetime, timedelta

@api_bp.route('/dashboard/summary', methods=['GET'])
@validate_query_params(DashboardQueryParams)
def get_dashboard_summary(validated_params: DashboardQueryParams):
    """Get dashboard summary statistics.

    Query params validated by DashboardQueryParams:
    - days: Number of days (default: 30, range: 1-3650)
    - category: Category filter (optional, max 50 chars)
    - year: Year filter (optional, range: 2020-2030)
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Entering get_dashboard_summary")
    try:
        days = validated_params.days
        category = validated_params.category
        year = validated_params.year

        logger.info(f"Fetching dashboard summary for days={days}, category={category}, year={year}")
        
        # Date range calculation
        if year:
            try:
                start_date = datetime(int(year), 1, 1)
                end_date = datetime(int(year), 12, 31, 23, 59, 59)
            except ValueError:
                # Invalid year, fallback to days
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
        else:
            # If year is not provided, it implies "All Time".
            # We override days to 3650 (10 years) to show long-term trend.
            days = 3650
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        
        logger.info("Getting review service...")
        service = get_review_service()
        logger.info("Review service obtained.")
        
        # Sentiment Stats - use category method for multi-line chart
        logger.info("=" * 80)
        logger.info(f"*** CALLING aggregate_sentiment_by_category ***")
        logger.info(f"  category={category}, year={year}")
        logger.info(f"  start_date={start_date}, end_date={end_date}, days={days}")
        
        # Use layered storage strategy
        logger.info(f"*** CALLING get_dashboard_stats_layered ***")
        logger.info(f"  category={category}, year={year}, days={days}")
        
        sentiment_stats = service.get_dashboard_stats_layered(
            year=int(year) if year else None,
            days=days,
            category=category
        )
        
        logger.info(f"*** RETURNED from aggregate_sentiment_by_category ***")
        logger.info(f"  series count: {len(sentiment_stats.get('series', []))}")
        logger.info(f"  dates count: {len(sentiment_stats.get('dates', []))}")
        if sentiment_stats.get('series'):
            for s in sentiment_stats['series']:
                logger.info(f"    - {s.get('name')}: {len(s.get('data', []))} points")
        logger.info("=" * 80)
        
        # Also get basic stats for KPIs
        basic_stats = service.aggregate_sentiment_sync(
            app_id=app_id,
            days=days,
            year=int(year) if year else None,
            category=category
        )
        
        # Complaint Stats
        complaint_stats = service.get_complaint_stats_sync(
            app_id=app_id,
            days=days,
            year=int(year) if year else None,
            category=category
        )
        
        # Merge basic stats with series data
        sentiment_stats.update(basic_stats)

        return jsonify(success_response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days
            },
            'sentiment': sentiment_stats,
            'complaints': complaint_stats
        }))

    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='DASHBOARD_SUMMARY_ERROR'
        )), 500

@api_bp.route('/dashboard/trends', methods=['GET'])
def get_dashboard_trends():
    """Get daily trends."""
    # This is covered by aggregate_sentiment (sentiment_over_time)
    # and get_complaint_stats (daily_trend)
    # But we can expose a specific endpoint if needed.
    # For now, summary endpoint provides enough data.
    return get_dashboard_summary()
