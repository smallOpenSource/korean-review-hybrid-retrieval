"""
Complaint-related views.
"""
import logging

from flask import render_template, request

from . import views_bp
from app.services.review_service import get_review_service
from app.services.department_routing_service import get_department_routing_service

logger = logging.getLogger(__name__)



@views_bp.route('/dept_review/<string:dept_code>')
def dept_review(dept_code: str):
    """Department review page."""
    routing_service = get_department_routing_service()
    teams = routing_service.get_all_teams()
    
    # Global Filters
    year = request.args.get('year')
    category = request.args.get('category')
    year_int = int(year) if year else None
    
    # Build department map for tabs
    # We'll group by division for better UI, but for now flat list is fine or simple grouping
    # Let's just pass the full teams dict to template and let it render
    
    # Get current department name
    current_dept_name = "전체"
    if dept_code != "ALL":
        team = routing_service.get_team_info(dept_code)
        if team:
            current_dept_name = team.name
        else:
            # Try finding by division if code is division code (optional feature)
            pass

    # Get App Service for filter
    from app.services.app_service import get_app_service
    app_service = get_app_service()
    apps = app_service.get_all_apps()
    
    # App Filter
    app_id = request.args.get('app_id')

    review_service = get_review_service()
    
    reviews = []  # Initialize here, not in except
    current_app_id = app_id  # Rename for consistency
    
    try:
        # Pass dept_code and app_id to filter
        hits = review_service.get_recent_reviews_sync(
            limit=20, 
            dept_code=dept_code,
            year=year_int,
            category=category,
            app_id=app_id
        )
        for hit in hits:
            source = hit['_source']
            dept = source.get('complaint', {}).get('escalated_to', '-')
            
            # If dept is a code, try to get name
            if dept in teams:
                dept = teams[dept].name
                
            reviews.append([
                source.get('review_date', '')[:10],
                source.get('app_name', ''),
                source.get('original_content', ''),
                dept
            ])
            
    except Exception as e:
        logger.error(f"Error fetching reviews: {e}")
        reviews = []

    # Get filter counts from mart table (fast)
    filter_counts = review_service.get_filter_counts_from_mart(
        dept_code=dept_code,
        app_id=current_app_id
    )

    return render_template(
        'pages/dept_review.html',
        dept_code=dept_code,
        dept_dis=current_dept_name,
        reviews=reviews,
        teams=teams,
        apps=apps,
        current_app_id=current_app_id,
        app_counts=filter_counts['app_counts'],
        dept_counts=filter_counts['dept_counts']
    )


@views_bp.route('/complaint_board')
def complaint_board():
    """Complaint dashboard page."""
    review_service = get_review_service()
    routing_service = get_department_routing_service()
    teams = routing_service.get_all_teams()
    
    # Global Filters
    year = request.args.get('year')
    category = request.args.get('category')
    year_int = int(year) if year else None
    
    # Dynamic days based on filter like dashboard
    query_days = 30
    if year_int is None:
        query_days = 3650  # All Time: 10 years
    
    try:
        stats = review_service.get_complaint_stats_sync(
            days=query_days,  # Changed from hardcoded 30 to dynamic
            year=year_int,
            category=category
        )
        hits = review_service.get_recent_complaints_sync(
            limit=50,
            year=year_int,
            category=category
        )
        
        total_complaints = stats.get('total_complaints', 0)
        
        pending_complaints = 0
        resolved_complaints = 0
        status_breakdown = stats.get('status_breakdown', {})
        # status_breakdown is now a dict {status: count}
        for status_key, count in status_breakdown.items():
            if status_key in ['new', 'in_progress', 'escalated']:
                pending_complaints += count
            elif status_key == 'resolved':
                resolved_complaints += count
                
        complaints_list = []
        for hit in hits:
            source = hit['_source']
            complaint_data = source.get('complaint', {})
            
            # Get department name from code
            dept_code = complaint_data.get('primary_dept', '-')
            dept_name = dept_code
            if dept_code in teams:
                dept_name = teams[dept_code].name
            
            # Handle None values with defaults
            c_type = complaint_data.get('type')
            if not c_type or c_type == 'None':
                c_type = 'unknown'
                
            c_sub_type = complaint_data.get('sub_type')
            if not c_sub_type or c_sub_type == 'None':
                c_sub_type = '-'
                
            c_dept = dept_name
            if not c_dept or c_dept == 'None':
                c_dept = '미분류'

            complaints_list.append({
                'date': source.get('review_date', '')[:10],
                'app_name': source.get('app_name') or '',
                'content': source.get('original_content') or '',
                'department': c_dept,
                'type': c_type,
                'sub_type': c_sub_type,
                'severity': complaint_data.get('severity') or 1,
                'urgency': complaint_data.get('urgency') or 1,
                'status': complaint_data.get('status') or 'new'
            })
            
    except Exception as e:
        logger.error(f"Error fetching complaint data: {e}")
        total_complaints = 0
        pending_complaints = 0
        resolved_complaints = 0
        complaints_list = []

    COMPLAINT_TYPES = {
        'error_report': '오류신고',
        'improvement_request': '개선요청',
        'dissatisfaction': '불만접수',
        'inquiry': '문의',
        'compliment': '칭찬',
        'suggestion': '제안',
        'unknown': '미분류'
    }
    
    STATUS_LABELS = {
        'new': '신규',
        'in_progress': '처리중',
        'resolved': '완료',
        'escalated': '이관됨'
    }

    return render_template(
        'pages/complaint_board.html', 
        title='민원 현황',
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        resolved_complaints=resolved_complaints,
        complaints=complaints_list,
        COMPLAINT_TYPES=COMPLAINT_TYPES,
        STATUS_LABELS=STATUS_LABELS
    )
