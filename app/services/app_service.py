"""
App Service.
Handles retrieval of app metadata from the database.
"""

import logging
from typing import List, Optional, Dict, Any

from app.core.mysql_client import MySQLClient

logger = logging.getLogger(__name__)


class AppService:
    """
    Service for managing app metadata.
    """

    def __init__(self):
        self.mysql = MySQLClient()

    def get_all_apps(self) -> List[Dict[str, Any]]:
        """Get all apps ordered by name."""
        try:
            query = """
                SELECT * FROM app_metadata 
                ORDER BY company_name
            """
            return self.mysql.execute_all(query)
        except Exception as e:
            logger.error(f"Failed to get all apps: {e}")
            return []

    def get_app_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get app by company code."""
        try:
            query = """
                SELECT * FROM app_metadata 
                WHERE company_code = %s
            """
            return self.mysql.execute_one(query, (code,))
        except Exception as e:
            logger.error(f"Failed to get app by code {code}: {e}")
            return None
        
    def get_apps_by_group(self, group_code: str) -> List[Dict[str, Any]]:
        """Get apps by group code."""
        try:
            query = """
                SELECT * FROM app_metadata 
                WHERE group_code = %s
            """
            return self.mysql.execute_all(query, (group_code,))
        except Exception as e:
            logger.error(f"Failed to get apps by group {group_code}: {e}")
            return []

    def get_app_by_package_id(self, package_id: str) -> Optional[Dict[str, Any]]:
        """Get app by package ID."""
        try:
            query = """
                SELECT * FROM app_metadata 
                WHERE package_id = %s
            """
            return self.mysql.execute_one(query, (package_id,))
        except Exception as e:
            logger.error(f"Failed to get app by package_id {package_id}: {e}")
            return None

    def get_all_package_ids(self, identifier: str) -> List[str]:
        """
        Get all package IDs for an app (current + legacy IDs).
        
        Args:
            identifier: Either company_code or package_id
            
        Returns:
            List of package IDs [current_id, legacy_id_1, legacy_id_2, ...]
        """
        import json
        
        try:
            # Try by company_code first
            app = self.get_app_by_code(identifier)
            
            # If not found, try by package_id
            if not app:
                app = self.get_app_by_package_id(identifier)
            
            if not app:
                logger.warning(f"App not found for identifier: {identifier}")
                return []
            
            # Start with current package_id
            ids = [app['package_id']]
            
            # Add legacy_ids if present
            legacy_ids = app.get('legacy_ids')
            if legacy_ids:
                if isinstance(legacy_ids, str):
                    legacy_ids = json.loads(legacy_ids)
                if isinstance(legacy_ids, list):
                    ids.extend(legacy_ids)
            
            return ids
        except Exception as e:
            logger.error(f"Failed to get all package IDs for {identifier}: {e}")
            return []


# Singleton instance
_app_service: Optional[AppService] = None


def get_app_service() -> AppService:
    """Get singleton AppService instance."""
    global _app_service
    if _app_service is None:
        _app_service = AppService()
    return _app_service
