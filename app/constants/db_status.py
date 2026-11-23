"""
데이터베이스 상태 플래그 정의.

MySQL 리뷰 테이블의 상태 컬럼에 사용되는 Enum입니다.
"""

from enum import IntEnum


class ReviewAnalysisStatus(IntEnum):
    """리뷰 분석 상태"""

    PENDING = 0
    """분석 대기 중"""

    COMPLETED = 1
    """분석 완료"""


class ReviewSyncStatus(IntEnum):
    """OpenSearch 동기화 상태"""

    NOT_SYNCED = 0
    """동기화 안됨"""

    SYNCED = 1
    """동기화 완료"""


class ReviewCollectionStatus(IntEnum):
    """리뷰 수집 상태"""

    ACTIVE = 1
    """활성 리뷰"""

    DELETED = 0
    """삭제된 리뷰"""


def is_analysis_pending(status: int) -> bool:
    """분석 대기 중인지 확인."""
    return status == ReviewAnalysisStatus.PENDING


def is_analysis_completed(status: int) -> bool:
    """분석 완료되었는지 확인."""
    return status == ReviewAnalysisStatus.COMPLETED


def is_synced(status: int) -> bool:
    """동기화 완료되었는지 확인."""
    return status == ReviewSyncStatus.SYNCED


def needs_sync(analyzed: int, synced: int) -> bool:
    """
    동기화가 필요한지 확인.

    Args:
        analyzed: analyzed 컬럼 값
        synced: synced_to_opensearch 컬럼 값

    Returns:
        동기화 필요 여부 (분석 완료 + 미동기화)
    """
    return (
        analyzed == ReviewAnalysisStatus.COMPLETED and
        synced == ReviewSyncStatus.NOT_SYNCED
    )
