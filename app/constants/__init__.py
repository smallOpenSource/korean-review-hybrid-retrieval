"""Constants package."""

from app.constants.response_status import ResponseStatus, success_response, error_response
from app.constants.user_roles import UserRole, ROLE_PERMISSIONS, has_permission
from app.constants.complaint_status import (
    ComplaintStatus,
    ComplaintPriority,
    COMPLAINT_STATUS_LABELS,
    COMPLAINT_PRIORITY_LABELS,
    STATUS_TRANSITIONS,
    can_transition,
    get_status_label,
    get_priority_label
)
from app.constants.review_categories import (
    ReviewCategory,
    CATEGORY_LABELS,
    CATEGORY_DESCRIPTIONS,
    get_category_label,
    get_category_description,
    get_all_categories
)
from app.constants.db_status import (
    ReviewAnalysisStatus,
    ReviewSyncStatus,
    ReviewCollectionStatus,
    is_analysis_pending,
    is_analysis_completed,
    is_synced,
    needs_sync
)

__all__ = [
    # Response
    'ResponseStatus',
    'success_response',
    'error_response',
    # User Roles
    'UserRole',
    'ROLE_PERMISSIONS',
    'has_permission',
    # Complaint Status
    'ComplaintStatus',
    'ComplaintPriority',
    'COMPLAINT_STATUS_LABELS',
    'COMPLAINT_PRIORITY_LABELS',
    'STATUS_TRANSITIONS',
    'can_transition',
    'get_status_label',
    'get_priority_label',
    # Review Categories
    'ReviewCategory',
    'CATEGORY_LABELS',
    'CATEGORY_DESCRIPTIONS',
    'get_category_label',
    'get_category_description',
    'get_all_categories',
    # DB Status
    'ReviewAnalysisStatus',
    'ReviewSyncStatus',
    'ReviewCollectionStatus',
    'is_analysis_pending',
    'is_analysis_completed',
    'is_synced',
    'needs_sync',
]
