"""
Authentication Decorators and Utilities

Provides JWT and API Key authentication decorators for Flask routes.
Supports role-based access control (RBAC).
"""

from functools import wraps
from flask import jsonify, request, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from typing import List, Callable, Union
import structlog
from app.constants import UserRole, error_response

logger = structlog.get_logger()


def jwt_or_api_key_required(fn: Callable) -> Callable:
    """
    Decorator requiring either JWT token or API Key authentication

    Checks for JWT token first, then falls back to X-API-Key header.
    Sets g.current_user if authenticated via API key.

    Usage:
        @api_bp.route('/reviews')
        @jwt_or_api_key_required
        def get_reviews():
            pass
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1. Try JWT authentication first
        try:
            verify_jwt_in_request()
            # JWT is valid, proceed with the request
            return fn(*args, **kwargs)
        except Exception as jwt_error:
            logger.debug("JWT verification failed, checking API key", error=str(jwt_error))

        # 2. Fall back to API Key authentication
        api_key = request.headers.get('X-API-Key')
        if api_key:
            from app.services.user_service import UserService
            user_service = UserService()

            try:
                user = user_service.get_user_by_api_key(api_key)
                if user and user.is_active:
                    g.current_user = user
                    logger.info(
                        "API key authentication successful",
                        user_id=user.id,
                        username=user.username
                    )
                    return fn(*args, **kwargs)
                else:
                    logger.warning(
                        "Invalid or inactive API key",
                        api_key_prefix=api_key[:8] if len(api_key) > 8 else "***"
                    )
            except Exception as e:
                logger.error("API key validation error", error=str(e), exc_info=True)

        # 3. Both authentication methods failed
        return jsonify({
            'status': 'error',
            'error_code': 'UNAUTHORIZED',
            'message': 'Valid JWT token or API key required'
        }), 401

    return wrapper


def role_required(*required_roles: UserRole) -> Callable:
    """
    Decorator requiring specific roles for access

    Must be used AFTER @jwt_or_api_key_required decorator.
    Checks JWT claims for roles or g.current_user.roles for API key auth.

    Args:
        *required_roles: One or more UserRole enum values (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)

    Usage:
        @api_bp.route('/reviews/<id>', methods=['DELETE'])
        @jwt_or_api_key_required
        @role_required(UserRole.ADMIN)
        def delete_review(id):
            pass

        @api_bp.route('/analysis/analyze', methods=['POST'])
        @jwt_or_api_key_required
        @role_required(UserRole.ANALYST, UserRole.ADMIN)  # Either role allowed
        def analyze():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_roles = []

            # Check JWT claims first
            try:
                claims = get_jwt()
                user_roles_str = claims.get('roles', [])
                # Convert strings to UserRole enums
                user_roles = [
                    UserRole(role) if isinstance(role, str) else role
                    for role in user_roles_str
                ]
            except Exception:
                # No JWT, check API key authentication
                if hasattr(g, 'current_user') and g.current_user:
                    user_roles = g.current_user.roles
                else:
                    logger.warning("Role check failed: no authentication context")
                    return jsonify(error_response(
                        message='Authentication required for role verification',
                        error_code='UNAUTHORIZED'
                    )), 401

            # Check if user has any of the required roles
            if not any(role in user_roles for role in required_roles):
                required_roles_str = ', '.join([r.value for r in required_roles])
                user_roles_str = ', '.join([r.value if isinstance(r, UserRole) else str(r) for r in user_roles])

                logger.warning(
                    "Insufficient permissions",
                    user_roles=user_roles_str,
                    required_roles=required_roles_str
                )
                return jsonify(error_response(
                    message=f'One of these roles required: {required_roles_str}',
                    error_code='FORBIDDEN'
                )), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user_id() -> int:
    """
    Get current authenticated user ID

    Returns:
        User ID from JWT identity or g.current_user

    Raises:
        RuntimeError: If called outside authenticated context
    """
    try:
        # Try JWT first
        return get_jwt_identity()
    except Exception:
        # Fall back to API key auth
        if hasattr(g, 'current_user') and g.current_user:
            return g.current_user.id

    raise RuntimeError("get_current_user_id called outside authenticated context")


def get_current_user_roles() -> List[UserRole]:
    """
    Get current authenticated user's roles as UserRole enums

    Returns:
        List of UserRole enums

    Raises:
        RuntimeError: If called outside authenticated context
    """
    try:
        # Try JWT claims first
        claims = get_jwt()
        roles_str = claims.get('roles', [])
        # Convert strings to UserRole enums
        return [
            UserRole(role) if isinstance(role, str) else role
            for role in roles_str
        ]
    except Exception:
        # Fall back to API key auth
        if hasattr(g, 'current_user') and g.current_user:
            return g.current_user.roles

    raise RuntimeError("get_current_user_roles called outside authenticated context")
