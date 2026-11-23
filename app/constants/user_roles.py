"""
사용자 역할 정의.

모든 인증 및 권한 체크는 이 Enum을 사용해야 합니다.
"""

from enum import Enum


class UserRole(str, Enum):
    """사용자 역할"""

    ADMIN = "admin"
    """시스템 관리자 - 모든 권한"""

    ANALYST = "analyst"
    """데이터 분석가 - 분석 및 리포트 권한"""

    VIEWER = "viewer"
    """뷰어 - 읽기 전용 권한"""


# 역할별 권한 매핑
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        'can_create_user': True,
        'can_delete_user': True,
        'can_modify_settings': True,
        'can_view_analytics': True,
        'can_export_data': True,
        'can_manage_complaints': True,
    },
    UserRole.ANALYST: {
        'can_create_user': False,
        'can_delete_user': False,
        'can_modify_settings': False,
        'can_view_analytics': True,
        'can_export_data': True,
        'can_manage_complaints': True,
    },
    UserRole.VIEWER: {
        'can_create_user': False,
        'can_delete_user': False,
        'can_modify_settings': False,
        'can_view_analytics': True,
        'can_export_data': False,
        'can_manage_complaints': False,
    }
}


def has_permission(role: UserRole, permission: str) -> bool:
    """
    역할이 특정 권한을 가지는지 확인.

    Args:
        role: 사용자 역할
        permission: 권한명

    Returns:
        권한 보유 여부
    """
    return ROLE_PERMISSIONS.get(role, {}).get(permission, False)
