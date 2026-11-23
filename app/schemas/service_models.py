"""
서비스 레이어용 Pydantic 스키마.

Redis 캐시, 설정 파일 등에서 읽어온 JSON 데이터를 검증합니다.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class WordRankingItem(BaseModel):
    """단어 순위 아이템"""

    word: str = Field(..., description="단어")
    count: int = Field(..., ge=0, description="출현 횟수")
    rank: int = Field(..., ge=1, description="순위")
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0, description="비율 (%)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "word": "로그인",
                "count": 150,
                "rank": 1,
                "percentage": 12.5
            }
        }
    )


class WordRankingResult(BaseModel):
    """단어 분석 결과"""

    total_reviews: int = Field(..., ge=0, description="전체 리뷰 수")
    total_words: int = Field(..., ge=0, description="전체 단어 수")
    unique_words: int = Field(..., ge=0, description="고유 단어 수")
    rankings: List[WordRankingItem] = Field(default_factory=list, description="단어 순위 목록")
    generated_at: Optional[str] = Field(None, description="생성 시각")

    @field_validator('rankings')
    @classmethod
    def validate_rankings_order(cls, v: List[WordRankingItem]) -> List[WordRankingItem]:
        """순위가 올바르게 정렬되어 있는지 확인"""
        if len(v) > 1:
            for i in range(len(v) - 1):
                if v[i].rank >= v[i + 1].rank:
                    raise ValueError(f"Rankings must be in ascending order: {v[i].rank} >= {v[i + 1].rank}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_reviews": 1000,
                "total_words": 50000,
                "unique_words": 5000,
                "rankings": [
                    {"word": "로그인", "count": 150, "rank": 1, "percentage": 12.5},
                    {"word": "편리", "count": 120, "rank": 2, "percentage": 10.0}
                ],
                "generated_at": "2024-01-01T00:00:00"
            }
        }
    )


class TeamInfo(BaseModel):
    """부서 정보"""

    code: str = Field(..., description="부서 코드")
    name: str = Field(..., description="부서명")
    description: Optional[str] = Field(None, description="설명")
    division_code: Optional[str] = Field(None, description="본부 코드")
    division_name: Optional[str] = Field(None, description="본부명")
    keywords: List[str] = Field(default_factory=list, description="키워드 목록")
    representative_sentences: List[str] = Field(default_factory=list, description="대표 문장")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "CALL_CENTER",
                "name": "콜센터운영부",
                "description": "고객 응대 및 상담",
                "division_code": "CUSTOMER_SERVICE",
                "division_name": "고객서비스본부",
                "keywords": ["전화", "상담", "문의"],
                "representative_sentences": ["고객센터에 문의했는데..."]
            }
        }
    )


class RoutingRule(BaseModel):
    """부서 라우팅 규칙"""

    rule_id: str = Field(..., description="규칙 ID")
    priority: int = Field(..., ge=1, description="우선순위")
    conditions: Dict[str, Any] = Field(..., description="조건")
    target_team: str = Field(..., description="대상 부서 코드")
    enabled: bool = Field(True, description="활성화 여부")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rule_id": "rule_001",
                "priority": 1,
                "conditions": {
                    "keywords": ["로그인", "인증"],
                    "categories": ["login"]
                },
                "target_team": "IT_SECURITY",
                "enabled": True
            }
        }
    )


class DepartmentRoutingConfig(BaseModel):
    """부서 라우팅 설정"""

    version: str = Field(..., description="설정 버전")
    teams: List[TeamInfo] = Field(..., description="부서 목록")
    rules: List[RoutingRule] = Field(default_factory=list, description="라우팅 규칙")
    fallback_team: Optional[str] = Field(None, description="기본 부서 코드")

    @field_validator('teams')
    @classmethod
    def validate_unique_team_codes(cls, v: List[TeamInfo]) -> List[TeamInfo]:
        """부서 코드 중복 체크"""
        codes = [team.code for team in v]
        if len(codes) != len(set(codes)):
            duplicates = [code for code in codes if codes.count(code) > 1]
            raise ValueError(f"Duplicate team codes found: {set(duplicates)}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.0.0",
                "teams": [
                    {"code": "CALL_CENTER", "name": "콜센터운영부", "keywords": []}
                ],
                "rules": [],
                "fallback_team": "CALL_CENTER"
            }
        }
    )


class SimilarReviewItem(BaseModel):
    """유사 리뷰 아이템"""

    review_id: str = Field(..., description="리뷰 ID")
    content: str = Field(..., description="리뷰 내용")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="유사도 점수")
    rerank_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="재순위 점수")
    app_name: str = Field(..., description="앱 이름")
    rating: int = Field(..., ge=1, le=5, description="평점")
    review_date: str = Field(..., description="리뷰 날짜")
    sentiment_label: str = Field(..., description="감정 라벨")
    complaint_type: Optional[str] = Field(None, description="민원 유형")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "review_id": "rev_123",
                "content": "앱이 정말 좋습니다",
                "similarity_score": 0.95,
                "rerank_score": 0.98,
                "app_name": "테스트앱",
                "rating": 5,
                "review_date": "2024-01-01T00:00:00",
                "sentiment_label": "very_positive",
                "complaint_type": None
            }
        }
    )


class DailyCount(BaseModel):
    """일별 카운트"""

    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    count: int = Field(..., ge=0, description="카운트")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2024-01-01",
                "count": 150
            }
        }
    )


class SimilarReviewResult(BaseModel):
    """유사 리뷰 검색 결과"""

    query_review_id: Optional[str] = Field(None, description="쿼리 리뷰 ID")
    query_content: str = Field(..., description="쿼리 내용")
    similar_reviews: List[SimilarReviewItem] = Field(default_factory=list, description="유사 리뷰 목록")
    daily_trend: List[DailyCount] = Field(default_factory=list, description="일별 추세")
    total_similar_count: int = Field(..., ge=0, description="전체 유사 리뷰 수")
    search_method: str = Field(..., description="검색 방법")
    reranked: bool = Field(False, description="재순위 여부")
    generated_at: Optional[str] = Field(None, description="생성 시각")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query_review_id": "rev_123",
                "query_content": "앱이 좋습니다",
                "similar_reviews": [],
                "daily_trend": [],
                "total_similar_count": 10,
                "search_method": "vector+rerank",
                "reranked": True,
                "generated_at": "2024-01-01T00:00:00"
            }
        }
    )


class SentimentStats(BaseModel):
    """감정 통계"""

    sentiment_label: str = Field(..., description="감정 라벨")
    count: int = Field(..., ge=0, description="카운트")
    percentage: float = Field(..., ge=0.0, le=100.0, description="비율 (%)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sentiment_label": "very_positive",
                "count": 150,
                "percentage": 35.5
            }
        }
    )


class ComplaintStats(BaseModel):
    """민원 통계"""

    total_complaints: int = Field(..., ge=0, description="전체 민원 수")
    resolved: int = Field(..., ge=0, description="해결된 민원 수")
    pending: int = Field(..., ge=0, description="대기 중인 민원 수")
    escalated: int = Field(..., ge=0, description="에스컬레이션 민원 수")
    avg_resolution_hours: Optional[float] = Field(None, ge=0.0, description="평균 해결 시간 (시간)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_complaints": 500,
                "resolved": 450,
                "pending": 40,
                "escalated": 10,
                "avg_resolution_hours": 24.5
            }
        }
    )


class ReviewAggregationResult(BaseModel):
    """리뷰 집계 결과"""

    total_reviews: int = Field(..., ge=0, description="전체 리뷰 수")
    avg_rating: float = Field(..., ge=1.0, le=5.0, description="평균 평점")
    sentiment_distribution: List[SentimentStats] = Field(default_factory=list, description="감정 분포")
    date_range: Dict[str, str] = Field(default_factory=dict, description="날짜 범위")
    generated_at: Optional[str] = Field(None, description="생성 시각")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_reviews": 1000,
                "avg_rating": 4.2,
                "sentiment_distribution": [
                    {"sentiment_label": "very_positive", "count": 300, "percentage": 30.0}
                ],
                "date_range": {"from": "2024-01-01", "to": "2024-01-31"},
                "generated_at": "2024-01-01T00:00:00"
            }
        }
    )
