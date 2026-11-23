"""
API Request/Response Models using Pydantic.
Provides validation for all API endpoints.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


# ===================================================================
# Request Models
# ===================================================================

class ReviewSearchRequest(BaseModel):
    """Request model for review search."""
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    k: int = Field(10, ge=1, le=100, description="Number of results")
    app_ids: List[str] = Field(default_factory=list, description="Filter by app IDs")
    min_score: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")
    date_from: Optional[datetime] = Field(None, description="Filter from date")
    date_to: Optional[datetime] = Field(None, description="Filter to date")
    
    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError('Query cannot be empty or whitespace only')
        return v.strip()


class SimilarReviewRequest(BaseModel):
    """Request model for similar review search."""
    review_id: Optional[str] = Field(None, description="Find similar to this review ID")
    query_text: Optional[str] = Field(None, min_length=1, max_length=1000, description="Or find similar to this text")
    k: int = Field(10, ge=1, le=100, description="Number of results")
    app_ids: List[str] = Field(default_factory=list, description="Filter by app IDs")
    use_rerank: bool = Field(True, description="Apply reranking")
    
    @validator('review_id', 'query_text')
    def validate_input(cls, v, values):
        # At least one of review_id or query_text must be provided
        if 'review_id' in values and not values['review_id'] and not v:
            raise ValueError('Either review_id or query_text must be provided')
        return v


class AnalysisRequest(BaseModel):
    """Request model for review analysis."""
    review_ids: List[str] = Field(..., min_items=1, max_items=100, description="Review IDs to analyze")
    analysis_types: List[str] = Field(
        default_factory=lambda: ['sentiment', 'category', 'complaint'],
        description="Types of analysis to perform"
    )
    force_reanalyze: bool = Field(False, description="Force re-analysis even if already analyzed")
    
    @validator('analysis_types')
    def validate_analysis_types(cls, v):
        allowed_types = {'sentiment', 'category', 'complaint', 'insight'}
        invalid = set(v) - allowed_types
        if invalid:
            raise ValueError(f"Invalid analysis types: {invalid}. Allowed: {allowed_types}")
        return v


class KeywordAnalysisRequest(BaseModel):
    """Request model for keyword analysis."""
    app_id: str = Field(..., description="App ID")
    date_from: Optional[datetime] = Field(None, description="From date")
    date_to: Optional[datetime] = Field(None, description="To date")
    top_k: int = Field(50, ge=10, le=500, description="Number of top keywords")
    min_frequency: int = Field(5, ge=1, le=100, description="Minimum keyword frequency")
    sentiment_filter: Optional[str] = Field(None, description="Filter by sentiment (positive/negative/neutral)")
    
    @validator('sentiment_filter')
    def validate_sentiment(cls, v):
        if v and v not in ('positive', 'negative', 'neutral'):
            raise ValueError("Sentiment must be one of: positive, negative, neutral")
        return v


class ComplaintRoutingRequest(BaseModel):
    """Request model for complaint routing."""
    review_id: str = Field(..., description="Review ID")
    override_dept: Optional[str] = Field(None, description="Override department assignment")
    escalation_level: Optional[str] = Field(None, description="Set escalation level")
    
    @validator('escalation_level')
    def validate_escalation(cls, v):
        if v and v not in ('none', 'low', 'medium', 'high', 'critical'):
            raise ValueError("Invalid escalation level")
        return v


# ===================================================================
# Response Models (using Generic for type safety)
# ===================================================================

class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int = Field(..., ge=1)
    per_page: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


class ApiResponseMeta(BaseModel):
    """API response metadata."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    latency_ms: Optional[int] = None
    pagination: Optional[PaginationMeta] = None


class ApiResponse(BaseModel):
    """Standard API response format."""
    success: bool = Field(..., description="Whether the request succeeded")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code for client handling")
    meta: ApiResponseMeta = Field(default_factory=ApiResponseMeta, description="Response metadata")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    @classmethod
    def ok(cls, data: Any = None, meta: Dict[str, Any] = None):
        """Create success response."""
        meta_obj = ApiResponseMeta(**meta) if meta else ApiResponseMeta()
        return cls(
            success=True,
            data=data,
            error=None,
            error_code=None,
            meta=meta_obj
        )
    
    @classmethod
    def error(cls, message: str, code: str = None, meta: Dict[str, Any] = None):
        """Create error response."""
        meta_obj = ApiResponseMeta(**meta) if meta else ApiResponseMeta()
        return cls(
            success=False,
            data=None,
            error=message,
            error_code=code or 'INTERNAL_ERROR',
            meta=meta_obj
        )
    
    @classmethod
    def validation_error(cls, message: str):
        """Create validation error response."""
        return cls.error(message=message, code='VALIDATION_ERROR')
    
    @classmethod
    def not_found(cls, message: str = "Resource not found"):
        """Create not found error response."""
        return cls.error(message=message, code='NOT_FOUND')
    
    @classmethod
    def unauthorized(cls, message: str = "Unauthorized"):
        """Create unauthorized error response."""
        return cls.error(message=message, code='UNAUTHORIZED')


# ===================================================================
# Helper Functions
# ===================================================================

def validate_request(model_class: type[BaseModel], data: dict) -> tuple[Optional[BaseModel], Optional[ApiResponse]]:
    """
    Validate request data against Pydantic model.
    
    Returns:
        (validated_model, error_response)
        If validation succeeds: (model_instance, None)
        If validation fails: (None, ApiResponse with error)
    """
    try:
        validated = model_class(**data)
        return validated, None
    except ValueError as e:
        error_msg = str(e)
        return None, ApiResponse.validation_error(error_msg)
    except Exception as e:
        error_msg = f"Invalid request data: {str(e)}"
        return None, ApiResponse.validation_error(error_msg)
