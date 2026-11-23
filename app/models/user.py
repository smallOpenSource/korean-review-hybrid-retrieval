"""
User Model for Authentication System

Dataclass-based model representing users with JWT authentication support.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Union
from app.constants import UserRole


@dataclass
class User:
    """User model with role-based access control"""

    id: int
    username: str
    email: str
    password_hash: str
    roles: List[Union[str, UserRole]]  # Supports both string and UserRole for backward compatibility
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    api_key: Optional[str] = None  # For external integrations
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Convert string roles to UserRole enums after initialization"""
        if self.roles:
            normalized_roles = []
            for role in self.roles:
                if isinstance(role, str):
                    try:
                        normalized_roles.append(UserRole(role))
                    except ValueError:
                        # Keep invalid roles as strings for backward compatibility
                        normalized_roles.append(role)
                elif isinstance(role, UserRole):
                    normalized_roles.append(role)
            self.roles = normalized_roles

    def has_role(self, role: Union[str, UserRole]) -> bool:
        """
        Check if user has a specific role

        Args:
            role: Role to check (UserRole enum or string)

        Returns:
            True if user has the role
        """
        check_role = UserRole(role) if isinstance(role, str) else role
        return check_role in self.roles

    def has_any_role(self, *roles: Union[str, UserRole]) -> bool:
        """
        Check if user has any of the specified roles

        Args:
            *roles: Roles to check (UserRole enums or strings)

        Returns:
            True if user has any of the roles
        """
        return any(self.has_role(role) for role in roles)

    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.has_role(UserRole.ADMIN)

    def is_analyst(self) -> bool:
        """Check if user has analyst role"""
        return self.has_role(UserRole.ANALYST)

    def is_viewer(self) -> bool:
        """Check if user has viewer role"""
        return self.has_role(UserRole.VIEWER)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """
        Convert user to dictionary for API responses

        Args:
            include_sensitive: Include sensitive fields like api_key

        Returns:
            Dictionary representation of user
        """
        # Convert UserRole enums to strings for JSON serialization
        roles_as_strings = [
            role.value if isinstance(role, UserRole) else role
            for role in self.roles
        ]

        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'roles': roles_as_strings,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

        if include_sensitive and self.api_key:
            data['api_key'] = self.api_key

        return data

    def __repr__(self) -> str:
        return f"User(id={self.id}, username='{self.username}', roles={self.roles})"
