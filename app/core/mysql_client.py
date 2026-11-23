"""
MySQL client with connection pooling support.
Provides both sync and async interfaces.
"""

import logging
from typing import Optional, Any, List, Dict
from functools import lru_cache
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class MySQLClient:
    """
    MySQL client with connection pooling.
    Uses DBUtils for efficient connection management.
    """

    def __init__(self):
        self._settings = get_settings().mysql
        self._pool: Optional[PooledDB] = None

    def _get_pool(self) -> PooledDB:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = PooledDB(
                creator=pymysql,
                maxconnections=20,
                mincached=2,
                maxcached=10,
                maxshared=5,
                blocking=True,
                maxusage=None,
                setsession=[],
                ping=1,
                host=self._settings.host,
                port=self._settings.port,
                user=self._settings.user,
                password=self._settings.password,
                database=self._settings.database,
                charset=self._settings.charset,
                cursorclass=DictCursor,
                autocommit=True
            )
            logger.info(f"MySQL connection pool created for {self._settings.host}:{self._settings.port}")
        return self._pool

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)."""
        conn = self._get_pool().connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def get_cursor(self):
        """Get a cursor from the pool (context manager)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check MySQL connection health."""
        try:
            with self.get_cursor() as cursor:
                sql = """/* sql_id: healthCheck */ SELECT 1"""
                cursor.execute(sql)
                return True
        except pymysql.Error as e:
            logger.error(f"MySQL health check failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------

    def execute(self, query: str, args: tuple = None) -> int:
        """Execute a query without returning results."""
        try:
            with self.get_cursor() as cursor:
                result = cursor.execute(query, args)
                return result
        except pymysql.Error as e:
            logger.error(f"MySQL execute failed: {e}")
            raise

    def execute_one(self, query: str, args: tuple = None) -> Optional[Dict[str, Any]]:
        """Execute a query and return a single row."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, args)
                return cursor.fetchone()
        except pymysql.Error as e:
            logger.error(f"MySQL execute_one failed: {e}")
            raise

    def execute_all(self, query: str, args: tuple = None) -> List[Dict[str, Any]]:
        """Execute a query and return all rows."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, args)
                return cursor.fetchall()
        except pymysql.Error as e:
            logger.error(f"MySQL execute_all failed: {e}")
            raise

    def execute_many(self, query: str, args_list: List[tuple]) -> int:
        """Execute a query with multiple parameter sets."""
        try:
            with self.get_cursor() as cursor:
                result = cursor.executemany(query, args_list)
                return result
        except pymysql.Error as e:
            logger.error(f"MySQL execute_many failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Transaction Support
    # -------------------------------------------------------------------------

    @contextmanager
    def transaction(self):
        """
        Transaction context manager.
        Commits on success, rolls back on exception.
        """
        conn = self._get_pool().connection()
        conn.autocommit(False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise
        finally:
            conn.autocommit(True)
            conn.close()

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a single row and return last insert ID."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"""/* sql_id: dynamicInsert_{table} */ INSERT INTO {table} ({columns}) VALUES ({placeholders})"""

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, tuple(data.values()))
                    return cursor.lastrowid
        except pymysql.Error as e:
            logger.error(f"MySQL insert failed: {e}")
            raise

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        where_args: tuple = None
    ) -> int:
        """Update rows and return affected count."""
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        sql = f"""/* sql_id: dynamicUpdate_{table} */ UPDATE {table} SET {set_clause} WHERE {where}"""
        args = tuple(data.values()) + (where_args or ())

        try:
            with self.get_cursor() as cursor:
                return cursor.execute(sql, args)
        except pymysql.Error as e:
            logger.error(f"MySQL update failed: {e}")
            raise

    def delete(self, table: str, where: str, where_args: tuple = None) -> int:
        """Delete rows and return affected count."""
        sql = f"""/* sql_id: dynamicDelete_{table} */ DELETE FROM {table} WHERE {where}"""

        try:
            with self.get_cursor() as cursor:
                return cursor.execute(sql, where_args)
        except pymysql.Error as e:
            logger.error(f"MySQL delete failed: {e}")
            raise

    def count(self, table: str, where: str = None, where_args: tuple = None) -> int:
        """Count rows in a table."""
        sql = f"""/* sql_id: dynamicCount_{table} */ SELECT COUNT(*) as cnt FROM {table}"""
        if where:
            sql += f" WHERE {where}"

        try:
            result = self.execute_one(sql, where_args)
            return result['cnt'] if result else 0
        except pymysql.Error as e:
            logger.error(f"MySQL count failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def close(self):
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
            logger.info("MySQL connection pool closed")


# Singleton instance
_mysql_client: Optional[MySQLClient] = None


def get_mysql_client() -> MySQLClient:
    """Get singleton MySQL client instance."""
    global _mysql_client
    if _mysql_client is None:
        _mysql_client = MySQLClient()
    return _mysql_client
