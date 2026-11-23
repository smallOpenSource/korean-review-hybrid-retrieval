"""
API 응답 상태 표준 정의.

모든 API 엔드포인트는 이 Enum을 사용하여 응답 상태를 반환해야 합니다.
"""

from enum import Enum


class ResponseStatus(str, Enum):
    """API 응답 상태"""

    OK = "ok"
    """성공적인 응답"""

    ERROR = "error"
    """오류 발생"""

    CREATED = "created"
    """리소스 생성 성공 (201)"""

    ACCEPTED = "accepted"
    """요청 수락됨 (202)"""

    PARTIAL = "partial"
    """부분적 성공 (일부 실패)"""


def success_response(data: dict, status: ResponseStatus = ResponseStatus.OK) -> dict:
    """
    성공 응답 헬퍼 함수.

    Args:
        data: 응답 데이터
        status: 응답 상태 (기본: OK)

    Returns:
        표준화된 성공 응답
    """
    return {
        'status': status.value,
        'data': data
    }


def error_response(message: str, details: dict = None, error_code: str = None) -> dict:
    """
    에러 응답 헬퍼 함수.

    Args:
        message: 에러 메시지
        details: 추가 상세 정보
        error_code: 에러 코드

    Returns:
        표준화된 에러 응답
    """
    response = {
        'status': ResponseStatus.ERROR.value,
        'message': message
    }

    if error_code:
        response['error_code'] = error_code

    if details:
        response['details'] = details

    return response
