"""
API Error Classes for Standardized Error Responses

This module provides a hierarchy of exception classes for consistent API error handling.
All errors inherit from APIError and provide standardized JSON responses with error codes.

Usage:
    from app.utils.errors import NotFoundError, ValidationError

    if not review:
        raise NotFoundError(
            message=f"Review with ID '{review_id}' not found",
            details={'review_id': review_id}
        )
"""

from flask import jsonify
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()


class APIError(Exception):
    """Base API Error

    All custom API exceptions inherit from this class.
    Provides consistent error response format and logging.

    Attributes:
        status_code (int): HTTP status code
        error_code (str): Machine-readable error identifier
        message (str): Human-readable error message
        details (dict): Additional context for debugging
    """
    status_code = 500
    error_code = "INTERNAL_SERVER_ERROR"
    message = "An internal server error occurred"

    def __init__(self, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__()
        if message:
            self.message = message
        self.details = details or {}

    def to_dict(self):
        """Convert error to JSON-serializable dictionary"""
        return {
            'status': 'error',
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details
        }


# ============================================================================
# 4xx Client Errors
# ============================================================================

class NotFoundError(APIError):
    """404 Not Found - Requested resource does not exist"""
    status_code = 404
    error_code = "NOT_FOUND"
    message = "The requested resource was not found"


class ValidationError(APIError):
    """400 Bad Request - Request validation failed"""
    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"


class UnauthorizedError(APIError):
    """401 Unauthorized - Authentication required"""
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication is required"


class ForbiddenError(APIError):
    """403 Forbidden - Insufficient permissions"""
    status_code = 403
    error_code = "FORBIDDEN"
    message = "You don't have permission to access this resource"


class ConflictError(APIError):
    """409 Conflict - Resource conflict (e.g., duplicate entry)"""
    status_code = 409
    error_code = "CONFLICT"
    message = "The request conflicts with the current state"


class RateLimitError(APIError):
    """429 Too Many Requests - Rate limit exceeded"""
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests. Please try again later"


# ============================================================================
# 5xx Server Errors
# ============================================================================

class ServiceUnavailableError(APIError):
    """503 Service Unavailable - Temporary service disruption"""
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class OpenSearchError(APIError):
    """500 Internal Server Error - OpenSearch operation failed"""
    status_code = 500
    error_code = "SEARCH_ERROR"
    message = "Search service error occurred"


class DatabaseError(APIError):
    """500 Internal Server Error - Database operation failed"""
    status_code = 500
    error_code = "DATABASE_ERROR"
    message = "Database operation failed"


class LLMError(APIError):
    """500 Internal Server Error - LLM/AI analysis failed"""
    status_code = 500
    error_code = "LLM_ERROR"
    message = "AI analysis service error occurred"
