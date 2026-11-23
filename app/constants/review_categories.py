"""
리뷰 카테고리 정의.

모든 카테고리 분류 로직은 이 Enum을 사용해야 합니다.
"""

from enum import Enum


class ReviewCategory(str, Enum):
    """리뷰 카테고리"""

    LOGIN = "login"
    """로그인 및 인증"""

    TRANSFER = "transfer"
    """이체 및 송금"""

    PAYMENT = "payment"
    """결제"""

    ACCOUNT = "account"
    """계좌 관리"""

    CARD = "card"
    """카드 관련"""

    LOAN = "loan"
    """대출"""

    INVESTMENT = "investment"
    """투자 및 자산관리"""

    UI_UX = "ui_ux"
    """UI/UX"""

    PERFORMANCE = "performance"
    """성능 및 안정성"""

    SECURITY = "security"
    """보안"""

    CUSTOMER_SERVICE = "customer_service"
    """고객 서비스"""

    NOTIFICATION = "notification"
    """알림"""

    FEATURE_REQUEST = "feature_request"
    """기능 요청"""

    ETC = "etc"
    """기타"""


# 카테고리별 한글 레이블
CATEGORY_LABELS = {
    ReviewCategory.LOGIN: "로그인/인증",
    ReviewCategory.TRANSFER: "이체/송금",
    ReviewCategory.PAYMENT: "결제",
    ReviewCategory.ACCOUNT: "계좌관리",
    ReviewCategory.CARD: "카드",
    ReviewCategory.LOAN: "대출",
    ReviewCategory.INVESTMENT: "투자/자산관리",
    ReviewCategory.UI_UX: "UI/UX",
    ReviewCategory.PERFORMANCE: "성능/안정성",
    ReviewCategory.SECURITY: "보안",
    ReviewCategory.CUSTOMER_SERVICE: "고객서비스",
    ReviewCategory.NOTIFICATION: "알림",
    ReviewCategory.FEATURE_REQUEST: "기능요청",
    ReviewCategory.ETC: "기타",
}


# 카테고리별 설명
CATEGORY_DESCRIPTIONS = {
    ReviewCategory.LOGIN: "로그인, 회원가입, 인증 관련 이슈",
    ReviewCategory.TRANSFER: "계좌이체, 송금 기능",
    ReviewCategory.PAYMENT: "결제, 간편결제, QR결제",
    ReviewCategory.ACCOUNT: "계좌 조회, 잔액 확인, 계좌 관리",
    ReviewCategory.CARD: "카드 등록, 카드 사용, 카드 혜택",
    ReviewCategory.LOAN: "대출 신청, 대출 관리, 상환",
    ReviewCategory.INVESTMENT: "주식, 펀드, 자산관리 서비스",
    ReviewCategory.UI_UX: "화면 디자인, 사용성, 접근성",
    ReviewCategory.PERFORMANCE: "앱 속도, 안정성, 오류",
    ReviewCategory.SECURITY: "보안, 개인정보 보호",
    ReviewCategory.CUSTOMER_SERVICE: "고객센터, 상담, 문의 응대",
    ReviewCategory.NOTIFICATION: "푸시 알림, 알림 설정",
    ReviewCategory.FEATURE_REQUEST: "신규 기능 제안",
    ReviewCategory.ETC: "기타 사항",
}


def get_category_label(category: ReviewCategory) -> str:
    """카테고리의 한글 레이블 반환."""
    return CATEGORY_LABELS.get(category, category.value)


def get_category_description(category: ReviewCategory) -> str:
    """카테고리 설명 반환."""
    return CATEGORY_DESCRIPTIONS.get(category, "")


def get_all_categories() -> list[ReviewCategory]:
    """모든 카테고리 목록 반환."""
    return list(ReviewCategory)
