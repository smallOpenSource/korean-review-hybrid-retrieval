"""
User Service for Authentication System

Handles user CRUD operations, password verification, and API key management.
"""

from typing import Optional
from datetime import datetime
import json
import structlog

from app.core.mysql_client import MySQLClient
from app.models.user import User
from app.utils.errors import DatabaseError, NotFoundError, ConflictError

logger = structlog.get_logger()


class UserService:
    """Service layer for user management operations"""

    def __init__(self):
        self.db = MySQLClient()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID

        Args:
            user_id: User ID

        Returns:
            User object or None if not found
        """
        try:
            query = """
                SELECT id, username, email, password_hash, roles,
                       is_active, api_key, created_at, last_login, updated_at
                FROM users
                WHERE id = %s
            """
            result = self.db.execute_one(query, (user_id,))

            if not result:
                return None

            return self._row_to_user(result)

        except Exception as e:
            logger.error("Failed to get user by ID", user_id=user_id, error=str(e))
            raise DatabaseError(message="Failed to retrieve user")

    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username

        Args:
            username: Username

        Returns:
            User object or None if not found
        """
        try:
            query = """
                SELECT id, username, email, password_hash, roles,
                       is_active, api_key, created_at, last_login, updated_at
                FROM users
                WHERE username = %s
            """
            result = self.db.execute_one(query, (username,))

            if not result:
                return None

            return self._row_to_user(result)

        except Exception as e:
            logger.error("Failed to get user by username", username=username, error=str(e))
            raise DatabaseError(message="Failed to retrieve user")

    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email

        Args:
            email: Email address

        Returns:
            User object or None if not found
        """
        try:
            query = """
                SELECT id, username, email, password_hash, roles,
                       is_active, api_key, created_at, last_login, updated_at
                FROM users
                WHERE email = %s
            """
            result = self.db.execute_one(query, (email,))

            if not result:
                return None

            return self._row_to_user(result)

        except Exception as e:
            logger.error("Failed to get user by email", email=email, error=str(e))
            raise DatabaseError(message="Failed to retrieve user")

    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """
        Get user by API key

        Args:
            api_key: API key

        Returns:
            User object or None if not found
        """
        try:
            query = """
                SELECT id, username, email, password_hash, roles,
                       is_active, api_key, created_at, last_login, updated_at
                FROM users
                WHERE api_key = %s
            """
            result = self.db.execute_one(query, (api_key,))

            if not result:
                return None

            return self._row_to_user(result)

        except Exception as e:
            logger.error(
                "Failed to get user by API key",
                api_key_prefix=api_key[:8] if len(api_key) > 8 else "***",
                error=str(e)
            )
            raise DatabaseError(message="Failed to retrieve user")

    def update_last_login(self, user_id: int) -> None:
        """
        Update user's last login timestamp

        Args:
            user_id: User ID
        """
        try:
            query = """
                UPDATE users
                SET last_login = %s
                WHERE id = %s
            """
            self.db.execute(query, (datetime.now(), user_id))
            logger.info("Updated last login", user_id=user_id)

        except Exception as e:
            logger.error("Failed to update last login", user_id=user_id, error=str(e))
            # Don't raise - last login update failure shouldn't block login

    def set_api_key(self, user_id: int, api_key: str) -> None:
        """
        Set or update user's API key

        Args:
            user_id: User ID
            api_key: New API key

        Raises:
            NotFoundError: If user not found
            ConflictError: If API key already exists
            DatabaseError: If database operation fails
        """
        try:
            # Check if user exists
            user = self.get_user_by_id(user_id)
            if not user:
                raise NotFoundError(
                    message=f"User with ID {user_id} not found",
                    details={'user_id': user_id}
                )

            query = """
                UPDATE users
                SET api_key = %s
                WHERE id = %s
            """
            self.db.execute(query, (api_key, user_id))
            logger.info("API key set for user", user_id=user_id)

        except NotFoundError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if 'duplicate' in error_msg or 'unique' in error_msg:
                raise ConflictError(
                    message="API key already exists",
                    details={'api_key_prefix': api_key[:8]}
                )
            logger.error("Failed to set API key", user_id=user_id, error=str(e))
            raise DatabaseError(message="Failed to update API key")

    def revoke_api_key(self, user_id: int) -> None:
        """
        Revoke user's API key

        Args:
            user_id: User ID
        """
        try:
            query = """
                UPDATE users
                SET api_key = NULL
                WHERE id = %s
            """
            self.db.execute(query, (user_id,))
            logger.info("API key revoked", user_id=user_id)

        except Exception as e:
            logger.error("Failed to revoke API key", user_id=user_id, error=str(e))
            raise DatabaseError(message="Failed to revoke API key")

    def deactivate_user(self, user_id: int) -> None:
        """
        Deactivate user account

        Args:
            user_id: User ID
        """
        try:
            query = """
                UPDATE users
                SET is_active = FALSE
                WHERE id = %s
            """
            self.db.execute(query, (user_id,))
            logger.info("User deactivated", user_id=user_id)

        except Exception as e:
            logger.error("Failed to deactivate user", user_id=user_id, error=str(e))
            raise DatabaseError(message="Failed to deactivate user")

    def activate_user(self, user_id: int) -> None:
        """
        Activate user account

        Args:
            user_id: User ID
        """
        try:
            query = """
                UPDATE users
                SET is_active = TRUE
                WHERE id = %s
            """
            self.db.execute(query, (user_id,))
            logger.info("User activated", user_id=user_id)

        except Exception as e:
            logger.error("Failed to activate user", user_id=user_id, error=str(e))
            raise DatabaseError(message="Failed to activate user")

    def _row_to_user(self, row: dict) -> User:
        """
        Convert database row to User object

        Args:
            row: Database row as dictionary

        Returns:
            User object
        """
        return User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            password_hash=row['password_hash'],
            roles=json.loads(row['roles']) if isinstance(row['roles'], str) else row['roles'],
            is_active=bool(row['is_active']),
            created_at=row['created_at'],
            last_login=row.get('last_login'),
            api_key=row.get('api_key'),
            updated_at=row.get('updated_at')
        )
