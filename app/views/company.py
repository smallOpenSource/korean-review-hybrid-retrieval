"""
Company-related views.
"""
import logging

from flask import render_template, request, abort

logger = logging.getLogger(__name__)

from . import views_bp
from app.services.review_service import get_review_service
from app.services.app_service import get_app_service


@views_bp.route('/company_list')
def company_list():
    """Company selection page."""
    app_service = get_app_service()
    apps = app_service.get_all_apps()
    return render_template('pages/company_list.html', title='비교분석', apps=apps)


@views_bp.route('/company_info/<string:company_slug>/')
def company_info(company_slug: str):
    """Company detail analysis page."""
    app_service = get_app_service()
    company = app_service.get_app_by_code(company_slug)
    
    if not company:
        abort(404)
        
    review_service = get_review_service()
    
    # Global Filters
    year = request.args.get('year')
    year_int = int(year) if year else None
    
    try:
        stats = review_service.aggregate_sentiment_sync(
            app_id=company['package_id'],
            days=3650,  # ~10 years to show all historical data if no year filter
            year=year_int
        )
        
        total_reviews = stats.get('total_reviews', 0)
        average_rating = stats.get('average_rating', 0.0)
        positive_rate = stats.get('positive_rate', 0.0)
        
    except Exception as e:
        logger.error(f"Error fetching company data: {e}")
        total_reviews = 0
        average_rating = 0.0
        positive_rate = 0.0

    return render_template(
        'pages/company_detail.html',
        title=f'{company["company_name"]} 분석',
        company_name=company["company_name"],
        company_code=company["company_code"], # For wordcloud images
        total_reviews=total_reviews,
        avg_rating=average_rating,
        positive_rate=positive_rate
    )
