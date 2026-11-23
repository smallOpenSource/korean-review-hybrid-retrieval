import logging
from typing import Dict, Any, Optional
from app.core.mysql_client import get_mysql_client

logger = logging.getLogger(__name__)

class SettingsService:
    """Service for managing system settings."""

    def __init__(self):
        self.mysql = get_mysql_client()

    def get_all_settings(self) -> Dict[str, str]:
        """Get all settings as a dictionary."""
        sql = "SELECT `key`, `value` FROM system_config"
        settings = {}
        
        try:
            with self.mysql.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    for row in rows:
                        settings[row['key']] = row['value']
        except Exception as e:
            logger.error(f"Failed to get settings: {e}")
            
        return settings

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a single setting value."""
        sql = "SELECT `value` FROM system_config WHERE `key` = %s"
        
        try:
            with self.mysql.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (key,))
                    result = cursor.fetchone()
                    if result:
                        return result['value']
        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            
        return default

    def update_setting(self, key: str, value: str) -> bool:
        """Update or insert a setting."""
        sql = """
        INSERT INTO system_config (`key`, `value`) 
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
        """
        
        try:
            with self.mysql.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (key, value))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update setting {key}: {e}")
            return False

    def update_settings(self, settings: Dict[str, str]) -> bool:
        """Update multiple settings at once."""
        sql = """
        INSERT INTO system_config (`key`, `value`) 
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
        """
        data = [(k, v) for k, v in settings.items()]
        
        try:
            with self.mysql.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(sql, data)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
            return False

# Singleton instance
_settings_service: Optional[SettingsService] = None

def get_settings_service() -> SettingsService:
    """Get singleton SettingsService instance."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service
