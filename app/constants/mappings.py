"""
Localization mappings for the application.

IMPORTANT: This file imports from Enum-based constants.
Prefer using Enums directly in new code. This file maintains backward
compatibility for legacy code and provides template context.
"""

from app.schemas.llm import SentimentLabel, SENTIMENT_LABELS  # EmotionType enum was removed (emotions are free text)
from app.constants.complaint_status import ComplaintStatus, ComplaintPriority, COMPLAINT_STATUS_LABELS, COMPLAINT_PRIORITY_LABELS
from app.constants.review_categories import ReviewCategory, CATEGORY_LABELS

# Re-export Enum-based labels for template context
# Use these in Jinja2 templates, but prefer Enums in Python code

# Sentiment Labels (5-level classification)
SENTIMENT_LABELS = {k.value: v for k, v in SENTIMENT_LABELS.items()}

# Complaint Status Labels
STATUS_LABELS = {k.value: v for k, v in COMPLAINT_STATUS_LABELS.items()}

# Review Category Labels
CATEGORIES = {k.value: v for k, v in CATEGORY_LABELS.items()}

# Legacy mappings - keep for backward compatibility

# Complaint Types (not yet migrated to Enum)
COMPLAINT_TYPES = {
    'system_error': '시스템 오류',
    'usability': '사용성',
    'feature_request': '기능 요청',
    'service_policy': '서비스 정책',
    'performance': '성능',
    'security': '보안',
    'other': '기타'
}

# Departments (TODO: migrate to Enum in future)
DEPARTMENTS = {
    'CS_TEAM': 'CS팀',
    'DEV_TEAM': '개발팀',
    'DESIGN_TEAM': '디자인팀',
    'PLANNING_TEAM': '기획팀',
    'QA_TEAM': 'QA팀',
    'MARKETING_TEAM': '마케팅팀',
    'ALL': '전체'
}

# Urgency Levels (maps to ComplaintPriority, but kept for numeric compatibility)
URGENCY_LEVELS = {
    1: '낮음',
    2: '보통',
    3: '높음',
    4: '긴급',
    5: '긴급'  # Map 5 to urgent as well
}
