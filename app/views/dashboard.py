"""
Dashboard views for main page rendering.
"""
import logging

from flask import render_template, request

from . import views_bp
from app.services.review_service import get_review_service
from app.services.category_service import get_category_service

logger = logging.getLogger(__name__)



@views_bp.route('/')
def index():
    """Main dashboard page."""
    review_service = get_review_service()
    
    # Global Filters
    year = request.args.get('year')
    category = request.args.get('category')
    
    year_int = int(year) if year else None
    
    try:
        # 0. Category Stats
        category_service = get_category_service()
        category_summary = category_service.format_category_summary()
        
        # 1. Sentiment Stats
        # If year is None, it implies "All Time" (or default view). 
        # If we want "All Time" to show 10 years, we should set days=3650.
        # However, the original code defaulted to days=30. 
        # Given the user wants "All Time" view improvements, we assume year=None means "All Time".
        query_days = 30
        if year_int is None:
            query_days = 3650 # 10 years

        sentiment_stats = review_service.aggregate_sentiment_sync(
            days=query_days, 
            year=year_int, 
            category=category
        )
        
        # 2. Complaint Stats
        complaint_stats = review_service.get_complaint_stats_sync(
            days=query_days,  # Changed from hardcoded 30 to dynamic query_days
            year=year_int, 
            category=category
        )
        
        # 3. App Rankings
        rankings = review_service.get_app_rankings_sync(
            days=query_days, 
            year=year_int, 
            category=category
        )
        
        # Extract values
        total_reviews = sentiment_stats.get('total_reviews', 0)
        average_rating = sentiment_stats.get('average_rating', 0.0)
        positive_rate = sentiment_stats.get('positive_rate', 0.0)
        
        reviews_change = sentiment_stats.get('reviews_change', 0.0)
        rating_change = sentiment_stats.get('rating_change', 0.0)
        pos_rate_change = sentiment_stats.get('pos_rate_change', 0.0)
        
        complaint_rate = complaint_stats.get('complaint_rate', 0.0)
        complaint_rate_change = complaint_stats.get('rate_change', 0.0)
        
        top_apps = rankings.get('top', [])
        bottom_apps = rankings.get('bottom', [])
        
    except Exception as e:
        # Fallback to 0 if OpenSearch is down or empty
        logger.error(f"Error fetching dashboard data: {e}")
        category_summary = "데이터 로딩 중..."
        total_reviews = 0
        average_rating = 0.0
        positive_rate = 0.0
        reviews_change = 0.0
        rating_change = 0.0
        pos_rate_change = 0.0
        complaint_rate = 0.0
        complaint_rate_change = 0.0
        top_apps = []
        bottom_apps = []

    return render_template(
        'pages/dashboard.html',
        title='종합 분석',
        category_summary=category_summary,
        total_reviews=total_reviews,
        average_rating=average_rating,
        positive_rate=positive_rate,
        complaint_rate=complaint_rate,
        reviews_change=reviews_change,
        rating_change=rating_change,
        pos_rate_change=pos_rate_change,
        complaint_rate_change=complaint_rate_change,
        top_apps=top_apps,
        bottom_apps=bottom_apps,
        year_filter=year  # Pass year filter to template for conditional display
    )

