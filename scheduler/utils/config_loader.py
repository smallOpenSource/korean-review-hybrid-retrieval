"""
Scheduler Configuration Loader.
Loads scheduler settings from YAML with environment variable substitution.
"""

import os
import re
import yaml
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)


class SchedulerConfigLoader:
    """
    Loads and manages scheduler configuration.

    Supports environment variable substitution in the format:
    ${VAR_NAME:default_value}
    """

    ENV_VAR_PATTERN = re.compile(r'\$\{([^:}]+)(?::([^}]*))?\}')

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config loader.

        Args:
            config_path: Path to scheduler_config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'scheduler_config.yaml'
        self._config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _substitute_env_vars(self, value: Any) -> Any:
        """Recursively substitute environment variables in config values."""
        if isinstance(value, str):
            def replace_env_var(match):
                var_name = match.group(1)
                default_value = match.group(2) if match.group(2) is not None else ''
                return os.environ.get(var_name, default_value)

            return self.ENV_VAR_PATTERN.sub(replace_env_var, value)
        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        return value

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self._config_path.exists():
            logger.warning(f"Config file not found: {self._config_path}, using defaults")
            self._config = self._get_default_config()
            return

        with open(self._config_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)

        self._config = self._substitute_env_vars(raw_config)
        
        # Post-process Redis Sentinel configuration
        self._configure_redis_sentinels()
        
        logger.info(f"Loaded scheduler configuration from {self._config_path}")

    def _configure_redis_sentinels(self) -> None:
        """Parse REDIS_SENTINEL_HOSTS and update config."""
        sentinel_hosts = os.environ.get('REDIS_SENTINEL_HOSTS')
        if sentinel_hosts and self._config.get('redis', {}).get('sentinel', {}).get('enabled') == 'true':
            sentinels = []
            for host_port in sentinel_hosts.split(','):
                host_port = host_port.strip()
                if not host_port:
                    continue
                if ':' in host_port:
                    host, port = host_port.rsplit(':', 1)
                    sentinels.append({'host': host, 'port': int(port)})
                else:
                    sentinels.append({'host': host_port, 'port': 26379})
            
            if sentinels:
                self._config['redis']['sentinel']['sentinels'] = sentinels
                logger.info(f"Configured {len(sentinels)} Redis Sentinels from environment")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'scheduler': {
                'timezone': 'Asia/Seoul',
                'max_workers': 4,
                'job_store': {'type': 'memory'},
                'executor': {'type': 'threadpool', 'max_workers': 10}
            },
            'jobs': {},
            'database': {
                'main': {
                    'type': 'mysql',
                    'host': 'localhost',
                    'port': 3306,
                    'database': 'appreviews'
                }
            },
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 0
            },
            'logging': {
                'version': 1,
                'disable_existing_loggers': False
            },
            'alerts': {'enabled': False}
        }

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def scheduler(self) -> Dict[str, Any]:
        """Get scheduler settings."""
        return self._config.get('scheduler', {})

    @property
    def jobs(self) -> Dict[str, Any]:
        """Get job configurations."""
        return self._config.get('jobs', {})

    @property
    def database(self) -> Dict[str, Any]:
        """Get database settings."""
        return self._config.get('database', {})

    @property
    def redis(self) -> Dict[str, Any]:
        """Get redis settings."""
        return self._config.get('redis', {})

    @property
    def logging(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return self._config.get('logging', {})

    @property
    def alerts(self) -> Dict[str, Any]:
        """Get alert settings."""
        return self._config.get('alerts', {})

    def get_job_config(self, job_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific job."""
        return self.jobs.get(job_name)

    def is_job_enabled(self, job_name: str) -> bool:
        """Check if a job is enabled."""
        job_config = self.get_job_config(job_name)
        if job_config:
            return job_config.get('enabled', False)
        return False

    def get_database_url(self, db_name: str = 'main') -> str:
        """Get database URL for SQLAlchemy."""
        db_config = self.database.get(db_name, {})
        db_type = db_config.get('type', 'mysql')
        host = db_config.get('host', 'localhost')
        port = db_config.get('port', 3306)
        database = db_config.get('database', 'appreviews')
        username = db_config.get('username', 'root')
        password = db_config.get('password', '')

        if db_type == 'mysql':
            driver = 'pymysql'
            return f"mysql+{driver}://{username}:{password}@{host}:{port}/{database}"
        elif db_type == 'postgresql':
            return f"postgresql://{username}:{password}@{host}:{port}/{database}"
        else:
            return f"{db_type}://{username}:{password}@{host}:{port}/{database}"

    def get_redis_url(self) -> str:
        """Get Redis URL."""
        host = self.redis.get('host', 'localhost')
        port = self.redis.get('port', 6379)
        db = self.redis.get('db', 0)
        password = self.redis.get('password', '')

        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        return f"redis://{host}:{port}/{db}"


# Singleton instance
_scheduler_config: Optional[SchedulerConfigLoader] = None


def get_scheduler_config(config_path: Optional[str] = None) -> SchedulerConfigLoader:
    """Get singleton SchedulerConfigLoader instance."""
    global _scheduler_config
    if _scheduler_config is None:
        _scheduler_config = SchedulerConfigLoader(config_path)
    return _scheduler_config
