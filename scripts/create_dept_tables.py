#!/usr/bin/env python3
"""
Create department management tables in MariaDB.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import MySQLClient

def create_tables():
    """Create department tables."""
    client = MySQLClient()
    
    # Define statements directly
    statements = [
        """
        CREATE TABLE IF NOT EXISTS departments (
            dept_code VARCHAR(50) PRIMARY KEY COMMENT '부서 코드',
            dept_name VARCHAR(100) NOT NULL COMMENT '부서명',
            dept_name_en VARCHAR(100) COMMENT '부서명(영문)',
            parent_dept_code VARCHAR(50) COMMENT '상위 부서 코드',
            display_order INT DEFAULT 0 COMMENT '표시 순서',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
            FOREIGN KEY (parent_dept_code) REFERENCES departments(dept_code) ON DELETE SET NULL,
            INDEX idx_parent (parent_dept_code),
            INDEX idx_order (display_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='부서 정보 테이블'
        """,
        """
        CREATE TABLE IF NOT EXISTS app_department_mapping (
            package_id VARCHAR(255) COMMENT '앱 패키지 ID',
            dept_code VARCHAR(50) COMMENT '부서 코드',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '매핑 생성 일시',
            PRIMARY KEY (package_id, dept_code),
            FOREIGN KEY (package_id) REFERENCES app_metadata(package_id) ON DELETE CASCADE,
            FOREIGN KEY (dept_code) REFERENCES departments(dept_code) ON DELETE CASCADE,
            INDEX idx_dept (dept_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='앱-부서 매핑 테이블'
        """
    ]
    
    for i, stmt in enumerate(statements, 1):
        print(f"\n[{i}/{len(statements)}] Executing statement...")
        try:
            client.execute(stmt)
            print("✓ Success")
        except Exception as e:
            print(f"✗ Error: {e}")
            if "already exists" not in str(e).lower():
                raise
    
    # Verify tables created
    print("\n--- Verifying tables ---")
    tables = client.execute_all('SHOW TABLES')
    table_names = [list(t.values())[0] for t in tables]
    print(f"Current tables: {table_names}")
    
    if 'departments' in table_names:
        print("\n--- departments table schema ---")
        schema = client.execute_all('DESCRIBE departments')
        for col in schema:
            print(f"  {col['Field']}: {col['Type']}")
    
    if 'app_department_mapping' in table_names:
        print("\n--- app_department_mapping table schema ---")
        schema = client.execute_all('DESCRIBE app_department_mapping')
        for col in schema:
            print(f"  {col['Field']}: {col['Type']}")


if __name__ == '__main__':
    create_tables()
