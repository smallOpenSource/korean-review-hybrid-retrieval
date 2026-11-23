"""
Helper method for getting apps by category/group.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


def _get_apps_by_group_code(group_code: str) -> List[Dict[str, Any]]:
    """
    Get all apps belonging to a specific group_code.
    
    Args:
        group_code: Group code like 'banks', 'cards', etc.
    
    Returns:
        List of app metadata dicts
    """
    from app.services.app_service import get_app_service
    app_service = get_app_service()
    all_apps = app_service.get_all_apps()
    
    return [app for app in all_apps if app.get('group_code') == group_code]


def _get_group_korean_name(group_code: str) -> str:
    """
    Get Korean name for a group code.
    
    Args:
        group_code: Group code like 'banks', 'cards', etc.
    
    Returns:
        Korean name like '은행', '카드', etc.
    """
    from app.services.category_service import get_category_service
    category_service = get_category_service()
    return category_service.GROUP_CODE_KOREAN_NAMES.get(group_code, group_code)
