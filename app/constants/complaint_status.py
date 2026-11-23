"""
민원 상태 정의.

모든 민원 관리 로직은 이 Enum을 사용해야 합니다.
"""

from enum import Enum


class ComplaintStatus(str, Enum):
    """민원 처리 상태"""

    NEW = "new"
    """신규 접수"""

    IN_PROGRESS = "in_progress"
    """처리 중"""

    RESOLVED = "resolved"
    """해결 완료"""

    CLOSED = "closed"
    """종결"""


class ComplaintPriority(str, Enum):
    """민원 우선순위"""

    LOW = "low"
    """낮음"""

    MEDIUM = "medium"
    """보통"""

    HIGH = "high"
    """높음"""

    URGENT = "urgent"
    """긴급"""


# 상태 한글 레이블
COMPLAINT_STATUS_LABELS = {
    ComplaintStatus.NEW: "신규",
    ComplaintStatus.IN_PROGRESS: "처리중",
    ComplaintStatus.RESOLVED: "해결",
    ComplaintStatus.CLOSED: "종결",
}


# 우선순위 한글 레이블
COMPLAINT_PRIORITY_LABELS = {
    ComplaintPriority.LOW: "낮음",
    ComplaintPriority.MEDIUM: "보통",
    ComplaintPriority.HIGH: "높음",
    ComplaintPriority.URGENT: "긴급",
}


# 상태 전이 규칙
STATUS_TRANSITIONS = {
    ComplaintStatus.NEW: [ComplaintStatus.IN_PROGRESS, ComplaintStatus.CLOSED],
    ComplaintStatus.IN_PROGRESS: [ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED],
    ComplaintStatus.RESOLVED: [ComplaintStatus.CLOSED],
    ComplaintStatus.CLOSED: [],  # 종결 후 변경 불가
}


def get_status_label(status: ComplaintStatus) -> str:
    """상태 한글 레이블 반환."""
    return COMPLAINT_STATUS_LABELS.get(status, status.value)


def get_priority_label(priority: ComplaintPriority) -> str:
    """우선순위 한글 레이블 반환."""
    return COMPLAINT_PRIORITY_LABELS.get(priority, priority.value)


def can_transition(from_status: ComplaintStatus, to_status: ComplaintStatus) -> bool:
    """
    상태 전이가 가능한지 확인.

    Args:
        from_status: 현재 상태
        to_status: 목표 상태

    Returns:
        전이 가능 여부
    """
    allowed_transitions = STATUS_TRANSITIONS.get(from_status, [])
    return to_status in allowed_transitions
