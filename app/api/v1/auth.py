"""
Authentication API Endpoints

Provides JWT-based authentication with login, token refresh, logout, and API key management.
"""

from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
import bcrypt
import secrets
import structlog

from app.services.user_service import UserService
from app.utils.errors import ValidationError, UnauthorizedError, ForbiddenError
from app.constants import ResponseStatus, success_response, error_response, UserRole

logger = structlog.get_logger()

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')
user_service = UserService()


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint - authenticate user and issue JWT tokens

    Request Body:
        {
            "username": "admin",
            "password": "<password>"
        }

    Response:
        {
            "status": "ok",
            "data": {
                "access_token": "eyJ...",
                "refresh_token": "eyJ...",
                "user": {
                    "id": 1,
                    "username": "admin",
                    "email": "admin@example.com",
                    "roles": ["admin"],
                    "is_active": true
                }
            }
        }
    """
    try:
        data = request.get_json()
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'required_fields': ['username', 'password']}
            )

        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            raise ValidationError(
                message="Username and password are required",
                details={'missing_fields': [
                    field for field in ['username', 'password']
                    if not data.get(field)
                ]}
            )

        # Get user from database
        user = user_service.get_user_by_username(username)

        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            logger.warning("Login failed: invalid credentials", username=username)
            raise UnauthorizedError(
                message="Invalid username or password"
            )

        if not user.is_active:
            logger.warning("Login failed: account disabled", username=username)
            raise ForbiddenError(
                message="Account is disabled. Please contact administrator."
            )

        # Create JWT tokens (identity must be string)
        # Convert UserRole enums to strings for JWT claims
        roles_as_strings = [
            role.value if isinstance(role, UserRole) else role
            for role in user.roles
        ]
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={'roles': roles_as_strings}
        )
        refresh_token = create_refresh_token(identity=str(user.id))

        # Update last login timestamp
        user_service.update_last_login(user.id)

        logger.info("Login successful", user_id=user.id, username=username)

        return jsonify(success_response({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        })), 200

    except (ValidationError, UnauthorizedError, ForbiddenError):
        raise


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh token endpoint - issue new access token using refresh token

    Headers:
        Authorization: Bearer <refresh_token>

    Response:
        {
            "status": "ok",
            "data": {
                "access_token": "eyJ..."
            }
        }
    """
    try:
        identity = get_jwt_identity()
        user = user_service.get_user_by_id(int(identity))

        if not user:
            logger.error("Refresh failed: user not found", user_id=identity)
            raise UnauthorizedError(message="User not found")

        if not user.is_active:
            logger.warning("Refresh failed: account disabled", user_id=identity)
            raise ForbiddenError(message="Account is disabled")

        # Create new access token (identity is already string from get_jwt_identity)
        # Convert UserRole enums to strings for JWT claims
        roles_as_strings = [
            role.value if isinstance(role, UserRole) else role
            for role in user.roles
        ]
        access_token = create_access_token(
            identity=identity,
            additional_claims={'roles': roles_as_strings}
        )

        logger.info("Token refresh successful", user_id=identity)

        return jsonify(success_response({
            'access_token': access_token
        })), 200

    except (UnauthorizedError, ForbiddenError):
        raise


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout endpoint - invalidate current token

    Note: Currently returns success immediately.
    TODO: Implement token blacklist using Redis for proper token invalidation.

    Headers:
        Authorization: Bearer <access_token>

    Response:
        {
            "status": "ok",
            "message": "Successfully logged out"
        }
    """
    try:
        identity = get_jwt_identity()
        jti = get_jwt().get('jti')  # JWT ID for blacklist

        # TODO: Add token to Redis blacklist
        # redis_client.setex(f"blacklist:{jti}", ttl=3600, value="1")

        logger.info("Logout successful", user_id=identity, jti=jti)

        return jsonify(success_response({
            'message': 'Successfully logged out'
        })), 200

    except Exception as e:
        logger.error("Logout failed", error=str(e), exc_info=True)
        # Don't fail logout on errors
        return jsonify(success_response({
            'message': 'Successfully logged out'
        })), 200


@auth_bp.route('/api-key', methods=['POST'])
@jwt_required()
def generate_api_key():
    """
    Generate API key for external integrations

    Requires admin role.

    Headers:
        Authorization: Bearer <access_token>

    Request Body (optional):
        {
            "user_id": 2  # Admin can generate API key for other users
        }

    Response:
        {
            "status": "ok",
            "data": {
                "api_key": "sk_..."
            }
        }
    """
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        current_user_roles_str = claims.get('roles', [])

        # Convert strings to UserRole enums
        current_user_roles = [
            UserRole(role) if isinstance(role, str) else role
            for role in current_user_roles_str
        ]

        # Check admin role
        if UserRole.ADMIN not in current_user_roles:
            logger.warning(
                "API key generation failed: insufficient permissions",
                user_id=identity,
                roles=[r.value for r in current_user_roles]
            )
            raise ForbiddenError(
                message="Admin role required to generate API keys"
            )

        # Get target user ID (default to current user)
        data = request.get_json() or {}
        target_user_id = data.get('user_id', identity)

        # Verify target user exists
        target_user = user_service.get_user_by_id(target_user_id)
        if not target_user:
            raise ValidationError(
                message=f"User with ID {target_user_id} not found",
                details={'user_id': target_user_id}
            )

        # Generate secure API key
        api_key = f"sk_{secrets.token_urlsafe(32)}"

        # Store API key in database
        user_service.set_api_key(target_user_id, api_key)

        logger.info(
            "API key generated",
            admin_id=identity,
            target_user_id=target_user_id
        )

        return jsonify(success_response({
            'api_key': api_key,
            'user_id': target_user_id,
            'message': 'API key generated successfully. Store it securely - it will not be shown again.'
        })), 200

    except (ForbiddenError, ValidationError):
        raise


@auth_bp.route('/api-key', methods=['DELETE'])
@jwt_required()
def revoke_api_key():
    """
    Revoke API key

    Requires admin role or own user ID.

    Headers:
        Authorization: Bearer <access_token>

    Request Body (optional):
        {
            "user_id": 2  # Admin can revoke API key for other users
        }

    Response:
        {
            "status": "ok",
            "message": "API key revoked successfully"
        }
    """
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        current_user_roles_str = claims.get('roles', [])

        # Convert strings to UserRole enums
        current_user_roles = [
            UserRole(role) if isinstance(role, str) else role
            for role in current_user_roles_str
        ]

        # Get target user ID
        data = request.get_json() or {}
        target_user_id = data.get('user_id', identity)

        # Check permissions
        is_admin = UserRole.ADMIN in current_user_roles
        is_own_key = target_user_id == identity

        if not (is_admin or is_own_key):
            logger.warning(
                "API key revocation failed: insufficient permissions",
                user_id=identity,
                target_user_id=target_user_id
            )
            raise ForbiddenError(
                message="Can only revoke your own API key or admin role required"
            )

        # Revoke API key
        user_service.revoke_api_key(target_user_id)

        logger.info(
            "API key revoked",
            revoker_id=identity,
            target_user_id=target_user_id
        )

        return jsonify(success_response({
            'message': 'API key revoked successfully'
        })), 200

    except ForbiddenError:
        raise


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get current authenticated user information

    Headers:
        Authorization: Bearer <access_token>

    Response:
        {
            "status": "ok",
            "data": {
                "id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "roles": ["admin"],
                "is_active": true
            }
        }
    """
    try:
        identity = get_jwt_identity()
        user = user_service.get_user_by_id(int(identity))

        if not user:
            raise UnauthorizedError(message="User not found")

        return jsonify(success_response(user.to_dict())), 200

    except UnauthorizedError:
        raise
