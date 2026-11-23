"""
Extended Pydantic models for API input validation

This module provides comprehensive request/query parameter validation for all API endpoints.
All models enforce strict type checking, value ranges, and business logic constraints.

Created: 2025-12-31 (Session 2: Input Validation Infrastructure)
"""

from pydantic import BaseModel, Field, validator, constr
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

# Import Enums from their canonical locations
from app.schemas.llm import SentimentLabel
from app.constants.complaint_status import ComplaintStatus


# ========================================
# Enum Definitions
# ========================================


class SortOrder(str, Enum):
    """Sort direction"""
    ASC = "asc"
    DESC = "desc"


# ========================================
# Query Parameter Models
# ========================================

class ReviewQueryParams(BaseModel):
    """리뷰 조회 쿼리 파라미터

    Validates all query parameters for review list endpoints.
    Enforces pagination limits, date ranges, and filter constraints.
    """
    # Pagination
    page: int = Field(default=1, ge=1, le=10000, description="페이지 번호")
    size: int = Field(default=20, ge=1, le=100, description="페이지 크기")

    # Filters
    app_id: Optional[constr(min_length=1, max_length=100)] = None
    sentiment: Optional[SentimentLabel] = None
    category: Optional[str] = Field(default=None, max_length=50)
    is_complaint: Optional[bool] = None

    # Date range
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    # Sorting
    sort_by: Optional[str] = Field(
        default="created_at",
        pattern="^(created_at|rating|sentiment_score)$"
    )
    sort_order: Optional[SortOrder] = SortOrder.DESC

    @validator('date_to')
    def date_to_must_be_after_date_from(cls, v, values):
        """Ensure date range is valid"""
        if v and 'date_from' in values and values['date_from']:
            if v < values['date_from']:
                raise ValueError('date_to must be after date_from')
        return v

    @validator('size')
    def size_must_be_reasonable(cls, v):
        """Enforce performance limits"""
        if v > 100:
            raise ValueError('size cannot exceed 100 for performance reasons')
        return v


class DashboardQueryParams(BaseModel):
    """대시보드 조회 파라미터

    Validates dashboard analytics query parameters.
    Enforces reasonable time ranges and year constraints.
    """
    days: int = Field(default=30, ge=1, le=3650, description="조회 기간 (일)")
    category: Optional[str] = Field(default=None, max_length=50)
    year: Optional[int] = Field(default=None, ge=2020, le=2030)

    @validator('year')
    def year_must_be_valid(cls, v):
        """Ensure year is within supported range"""
        if v and (v < 2020 or v > 2030):
            raise ValueError('year must be between 2020 and 2030')
        return v


# ========================================
# Request Body Models
# ========================================

class SimilarReviewRequest(BaseModel):
    """유사 리뷰 검색 요청

    Validates semantic search requests.
    Enforces content length and result count limits.
    Supports legacy field names (k, min_similarity) via aliases.
    """
    content: constr(min_length=10, max_length=2000) = Field(
        ...,
        description="검색할 리뷰 내용"
    )
    app_id: Optional[str] = Field(default=None, max_length=100, description="앱 ID 필터")
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="반환할 유사 리뷰 개수",
        alias='k'
    )
    threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="유사도 임계값",
        alias='min_similarity'
    )

    class Config:
        populate_by_name = True  # Accept both alias and field name

    @validator('content')
    def content_must_not_be_empty(cls, v):
        """Ensure content is not just whitespace"""
        if not v.strip():
            raise ValueError('content cannot be empty or whitespace only')
        return v.strip()


class AnalyzeRequest(BaseModel):
    """리뷰 분석 요청

    Validates LLM analysis requests.
    Automatically truncates content if too long (legacy compatibility).
    """
    content: constr(min_length=1, max_length=5000) = Field(
        ...,
        description="분석할 리뷰 내용"
    )
    analyze_sentiment: bool = Field(default=True)
    analyze_category: bool = Field(default=True)
    analyze_complaint: bool = Field(default=True)

    @validator('content')
    def truncate_if_too_long(cls, v):
        """Auto-truncate content to 2000 chars (legacy behavior)"""
        if len(v) > 2000:
            return v[:2000]
        return v


class ComplaintUpdateRequest(BaseModel):
    """민원 상태 업데이트 요청

    Validates complaint management updates.
    All fields are optional (partial updates supported).
    """
    status: Optional[ComplaintStatus] = None
    assigned_to: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @validator('notes')
    def notes_must_not_be_only_whitespace(cls, v):
        """Ensure notes contain actual content"""
        if v and not v.strip():
            raise ValueError('notes cannot be empty or whitespace only')
        return v.strip() if v else None


class SearchRequest(BaseModel):
    """하이브리드 검색 요청 (키워드 + 벡터)

    Validates hybrid search requests.
    Supports optional query (returns empty results if not provided).
    """
    query: str = Field(default="", max_length=500, description="검색 쿼리")
    k: int = Field(default=10, ge=1, le=100, description="반환할 결과 개수")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="최소 점수")
    filters: Optional[dict] = Field(default=None, description="추가 필터")


class NaturalLanguageQueryRequest(BaseModel):
    """자연어 쿼리 요청

    Validates natural language query requests.
    Query is required and must not be empty.
    """
    query: constr(min_length=1, max_length=1000) = Field(
        ...,
        description="자연어 쿼리"
    )

    @validator('query')
    def query_must_not_be_empty(cls, v):
        """Ensure query is not just whitespace"""
        if not v.strip():
            raise ValueError('query cannot be empty or whitespace only')
        return v.strip()
