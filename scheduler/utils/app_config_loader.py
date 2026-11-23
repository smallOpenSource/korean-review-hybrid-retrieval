"""
App Configuration Loader.
Loads and manages Korean financial app configurations from database or YAML.
"""

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
from functools import lru_cache
from enum import Enum
from sqlalchemy import text

logger = logging.getLogger(__name__)


class Priority(str, Enum):
    """App priority levels for scheduling."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class AppInfo:
    """Information about a single app."""
    package_id: str
    name: str
    company: str
    category: str
    type: str
    priority: Priority
    fetch_interval_hours: int = 6
    review_fetch_count: int = 200
    review_languages: List[str] = field(default_factory=lambda: ["ko", "en"])
    legacy_ids: List[str] = field(default_factory=list)  # Historical package IDs

    @classmethod
    def from_dict(cls, data: Dict[str, Any], category: str, defaults: Dict[str, Any], legacy_ids_map: Optional[Dict[str, List[str]]] = None) -> 'AppInfo':
        """Create AppInfo from dictionary."""
        priority_str = data.get('priority', 'medium')
        try:
            priority = Priority(priority_str)
        except ValueError:
            priority = Priority.MEDIUM

        package_id = data['package_id']
        legacy_ids = []
        if legacy_ids_map and package_id in legacy_ids_map:
            legacy_ids = legacy_ids_map[package_id]

        return cls(
            package_id=package_id,
            name=data['name'],
            company=data['company'],
            category=category,
            type=data.get('type', 'unknown'),
            priority=priority,
            fetch_interval_hours=defaults.get('fetch_interval_hours', 6),
            review_fetch_count=defaults.get('review_fetch_count', 200),
            review_languages=defaults.get('review_languages', ['ko', 'en']),
            legacy_ids=legacy_ids
        )


@dataclass
class CategoryInfo:
    """Information about an app category."""
    name: str
    display_name: str
    description: str
    apps: List[AppInfo]


class AppConfigLoader:
    """
    Loads and manages app configurations from YAML.

    Provides methods to:
    - Get all apps
    - Get apps by category
    - Get apps by priority
    - Get app by package ID
    """

    def __init__(self, config_path: Optional[str] = None, use_database: bool = True):
        """
        Initialize the config loader.

        Args:
            config_path: Path to apps_config.yaml. If None, uses default location.
            use_database: If True, load from app_metadata table. If False, use YAML.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'apps_config.yaml'
        self._config_path = Path(config_path)
        self._use_database = use_database
        self._config: Dict[str, Any] = {}
        self._apps: Dict[str, AppInfo] = {}
        self._categories: Dict[str, CategoryInfo] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from database or YAML file."""
        if self._use_database:
            self._load_from_database()
        else:
            self._load_from_yaml()

    def _load_from_database(self) -> None:
        """Load app configuration from app_metadata table."""
        from scheduler.utils.database import get_db_session
        
        try:
            with get_db_session() as session:
                query = text("""
                    SELECT 
                        package_id,
                        company_name,
                        company_code,
                        group_code,
                        legacy_ids
                    FROM app_metadata
                    ORDER BY group_code, company_name
                """)
                
                result = session.execute(query)
                rows = result.fetchall()
                
                # Group by category
                category_map = {
                    'banks': '은행',
                    'securities': '증권',
                    'cards': '카드',
                    'life_insurance': '생명보험',
                    'non_life_insurance': '손해보험',
                    'fintech': '핀테크'
                }
                
                categories_data = {}
                
                for row in rows:
                    package_id = row[0]
                    company_name = row[1]
                    company_code = row[2]
                    group_code = row[3] or 'unknown'
                    legacy_ids_raw = row[4] if len(row) > 4 else None
                    
                    # Parse legacy_ids JSON
                    import json
                    legacy_ids = []
                    if legacy_ids_raw:
                        try:
                            if isinstance(legacy_ids_raw, str):
                                legacy_ids = json.loads(legacy_ids_raw)
                            elif isinstance(legacy_ids_raw, list):
                                legacy_ids = legacy_ids_raw
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    # Create AppInfo
                    app_info = AppInfo(
                        package_id=package_id,
                        name=company_name,
                        company=company_name,
                        category=group_code,
                        type='financial_app',
                        priority=Priority.MEDIUM,  # Default priority
                        fetch_interval_hours=6,
                        review_fetch_count=200,
                        review_languages=['ko', 'en'],
                        legacy_ids=legacy_ids
                    )
                    
                    self._apps[package_id] = app_info
                    
                    # Group by category
                    if group_code not in categories_data:
                        categories_data[group_code] = []
                    categories_data[group_code].append(app_info)
                
                # Create CategoryInfo objects
                for category_name, apps in categories_data.items():
                    display_name = category_map.get(category_name, category_name)
                    self._categories[category_name] = CategoryInfo(
                        name=category_name,
                        display_name=display_name,
                        description=f'{display_name} 앱',
                        apps=apps
                    )
                
                logger.info(f"Loaded {len(self._apps)} apps from database ({len(self._categories)} categories)")
                
        except Exception as e:
            logger.error(f"Failed to load apps from database: {e}")
            # Fallback to YAML if database fails
            logger.warning("Falling back to YAML configuration")
            self._load_from_yaml()

    def _load_from_yaml(self) -> None:
        """Load configuration from YAML file."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self._config_path}")

        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

        defaults = self._config.get('defaults', {})
        categories = self._config.get('categories', {})
        
        # Build legacy_ids_map from app_id_history
        legacy_ids_map = {}
        for history_entry in self._config.get('app_id_history', []):
            current_id = history_entry.get('current')
            previous_ids = [p.get('id') for p in history_entry.get('previous', []) if p.get('id')]
            if current_id and previous_ids:
                legacy_ids_map[current_id] = previous_ids

        for category_name, category_data in categories.items():
            apps = []
            for app_data in category_data.get('apps', []):
                try:
                    app_info = AppInfo.from_dict(app_data, category_name, defaults, legacy_ids_map)
                    apps.append(app_info)
                    self._apps[app_info.package_id] = app_info
                except KeyError as e:
                    logger.warning(f"Skipping app due to missing field: {e}")
                    continue

            self._categories[category_name] = CategoryInfo(
                name=category_name,
                display_name=category_data.get('display_name', category_name),
                description=category_data.get('description', ''),
                apps=apps
            )

        logger.info(f"Loaded {len(self._apps)} apps from YAML ({len(self._categories)} categories)")

    def reload(self) -> None:
        """Reload configuration from file."""
        self._apps.clear()
        self._categories.clear()
        self._load_config()

    def get_all_apps(self) -> List[AppInfo]:
        """Get all configured apps."""
        return list(self._apps.values())

    def get_app(self, package_id: str) -> Optional[AppInfo]:
        """Get app by package ID."""
        return self._apps.get(package_id)

    def get_apps_by_category(self, category: str) -> List[AppInfo]:
        """Get all apps in a category."""
        category_info = self._categories.get(category)
        if category_info:
            return category_info.apps
        return []

    def get_apps_by_priority(self, priority: Priority) -> List[AppInfo]:
        """Get all apps with a specific priority."""
        return [app for app in self._apps.values() if app.priority == priority]

    def get_categories(self) -> List[CategoryInfo]:
        """Get all categories."""
        return list(self._categories.values())

    def get_category(self, category: str) -> Optional[CategoryInfo]:
        """Get category info."""
        return self._categories.get(category)

    def get_priority_settings(self, priority: Priority) -> Dict[str, Any]:
        """Get settings for a priority level."""
        return self._config.get('priority_settings', {}).get(priority.value, {})

    def get_fetch_interval(self, priority: Priority) -> int:
        """Get fetch interval hours for a priority level."""
        settings = self.get_priority_settings(priority)
        return settings.get('fetch_interval_hours', 6)

    def get_app_count(self) -> int:
        """Get total number of configured apps."""
        return len(self._apps)

    def get_app_count_by_priority(self) -> Dict[str, int]:
        """Get app count by priority."""
        counts = {p.value: 0 for p in Priority}
        for app in self._apps.values():
            counts[app.priority.value] += 1
        return counts

    def get_package_ids(self) -> List[str]:
        """Get all package IDs."""
        return list(self._apps.keys())

    def validate_package_id(self, package_id: str) -> bool:
        """Check if a package ID is configured."""
        return package_id in self._apps

    def get_config_version(self) -> str:
        """Get configuration version."""
        return self._config.get('version', 'unknown')


# Singleton instance
_app_config_loader: Optional[AppConfigLoader] = None


def get_app_config_loader(config_path: Optional[str] = None) -> AppConfigLoader:
    """Get singleton AppConfigLoader instance."""
    global _app_config_loader
    if _app_config_loader is None:
        _app_config_loader = AppConfigLoader(config_path)
    return _app_config_loader
