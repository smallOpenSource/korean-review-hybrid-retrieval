"""
Database connection factory for scheduler.
Provides SQLAlchemy session management with connection pooling.
"""

import logging
import os
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration from environment variables."""
    
    def __init__(self):
        self.host = os.getenv('SCHEDULER_DB_HOST', '127.0.0.1')
        self.port = int(os.getenv('SCHEDULER_DB_PORT', '3306'))
        self.user = os.getenv('SCHEDULER_DB_USER', os.getenv('MYSQL_USER', ''))
        self.password = os.getenv('SCHEDULER_DB_PASSWORD', os.getenv('MYSQL_PASSWORD', ''))
        self.database = os.getenv('SCHEDULER_DB_NAME', 'app_reviews_scheduler')
        self.charset = os.getenv('SCHEDULER_DB_CHARSET', 'utf8mb4')
        
        # Connection pool settings
        self.pool_size = int(os.getenv('SCHEDULER_DB_POOL_SIZE', '5'))
        self.max_overflow = int(os.getenv('SCHEDULER_DB_MAX_OVERFLOW', '10'))
        self.pool_timeout = int(os.getenv('SCHEDULER_DB_POOL_TIMEOUT', '30'))
        self.pool_recycle = int(os.getenv('SCHEDULER_DB_POOL_RECYCLE', '3600'))
    
    @property
    def connection_url(self) -> str:
        """Generate SQLAlchemy connection URL."""
        return (
            f"mysql+pymysql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
            f"?charset={self.charset}"
        )
    
    def validate(self) -> bool:
        """Validate required configuration."""
        if not self.user:
            logger.error("Database user not configured (SCHEDULER_DB_USER or MYSQL_USER)")
            return False
        if not self.password:
            logger.error("Database password not configured (SCHEDULER_DB_PASSWORD or MYSQL_PASSWORD)")
            return False
        return True


class DatabaseSessionFactory:
    """
    Database session factory with connection pooling.
    Thread-safe singleton pattern.
    """
    
    _instance: Optional['DatabaseSessionFactory'] = None
    _engine = None
    _session_factory = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._engine is None:
            self._initialize()
    
    def _initialize(self):
        """Initialize database engine and session factory."""
        config = DatabaseConfig()
        
        if not config.validate():
            raise ValueError("Invalid database configuration")
        
        logger.info(f"Initializing database connection to {config.host}:{config.port}/{config.database}")
        
        # Create engine with connection pooling
        self._engine = create_engine(
            config.connection_url,
            poolclass=QueuePool,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL debugging
        )
        
        # Create session factory
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
        )
        
        logger.info("Database session factory initialized")
    
    def get_session(self) -> Session:
        """
        Get a new database session.
        
        Returns:
            SQLAlchemy Session instance
        """
        if self._session_factory is None:
            raise RuntimeError("Session factory not initialized")
        return self._session_factory()
    
    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope around a series of operations.
        
        Usage:
            with db_factory.session_scope() as session:
                session.execute(...)
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            session.close()
    
    def health_check(self) -> bool:
        """
        Check database connection health.
        
        Returns:
            True if database is accessible, False otherwise
        """
        try:
            with self.session_scope() as session:
                result = session.execute(text("SELECT 1"))
                result.fetchone()
            logger.debug("Database health check: OK")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close(self):
        """Close database engine and dispose of connections."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database engine disposed")


# Singleton instance
_db_factory: Optional[DatabaseSessionFactory] = None


def get_db_session_factory() -> DatabaseSessionFactory:
    """Get singleton database session factory instance."""
    global _db_factory
    if _db_factory is None:
        _db_factory = DatabaseSessionFactory()
    return _db_factory


def get_db_session() -> Session:
    """
    Convenience function to get a new database session.
    
    Returns:
        SQLAlchemy Session instance
    """
    factory = get_db_session_factory()
    return factory.get_session()
