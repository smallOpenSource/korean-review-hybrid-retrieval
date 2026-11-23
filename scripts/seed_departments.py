#!/usr/bin/env python3
"""
Seed initial department data.
Based on user's uploaded images showing: 은행본부, 은행본부2, 디지털본부, 보안본부
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import MySQLClient
from app.services.app_service import get_app_service

def seed_departments():
    """Seed department data."""
    client = MySQLClient()
    
    # Define initial departments
    departments = [
        {'code': 'BANK_DEPT1', 'name': '은행본부', 'name_en': 'Banking Department 1', 'parent': None, 'order': 1},
        {'code': 'BANK_DEPT2', 'name': '은행본부2', 'name_en': 'Banking Department 2', 'parent': None, 'order': 2},
        {'code': 'DIGITAL_DEPT', 'name': '디지털본부', 'name_en': 'Digital Department', 'parent': None, 'order': 3},
        {'code': 'SECURITY_DEPT', 'name': '보안본부', 'name_en': 'Security Department', 'parent': None, 'order': 4},
    ]
    
    print("=== Seeding Departments ===")
    for dept in departments:
        try:
            client.execute(
                """
                INSERT INTO departments (dept_code, dept_name, dept_name_en, parent_dept_code, display_order)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                dept_name = VALUES(dept_name),
                dept_name_en = VALUES(dept_name_en),
                parent_dept_code = VALUES(parent_dept_code),
                display_order = VALUES(display_order)
                """,
                (dept['code'], dept['name'], dept['name_en'], dept['parent'], dept['order'])
            )
            print(f"✓ {dept['name']} ({dept['code']})")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # Verify
    print("\n=== Verifying Departments ===")
    depts = client.execute_all("SELECT dept_code, dept_name, dept_name_en, display_order FROM departments ORDER BY display_order")
    for d in depts:
        print(f"  {d['display_order']}. {d['dept_name']} ({d['dept_code']}) - {d['dept_name_en']}")
    
    print(f"\nTotal departments: {len(depts)}")
    
    # Map some apps to departments (example)
    # For now, just map banks group to BANK_DEPT1
    print("\n=== Mapping Apps to Departments (Sample) ===")
    app_service = get_app_service()
    all_apps = app_service.get_all_apps()
    
    # Get all bank apps
    bank_apps = [app for app in all_apps if app.get('group_code') == 'banks']
    
    # Map first half to BANK_DEPT1, second half to BANK_DEPT2
    mid_point = len(bank_apps) // 2
    
    for i, app in enumerate(bank_apps):
        dept_code = 'BANK_DEPT1' if i < mid_point else 'BANK_DEPT2'
        try:
            client.execute(
                """INSERT INTO app_department_mapping (package_id, dept_code) 
                   VALUES (%s, %s) 
                   ON DUPLICATE KEY UPDATE dept_code = VALUES(dept_code)""",
                (app['package_id'], dept_code)
            )
            print(f"✓ Mapped {app['company_name']} → {dept_code}")
        except Exception as e:
            print(f"✗ Error mapping {app['company_name']}: {e}")
    
    # Verify mappings
    print("\n=== Verifying Mappings ===")
    mappings = client.execute_all("""
        SELECT d.dept_name, COUNT(*) as app_count
        FROM app_department_mapping adm
        JOIN departments d ON adm.dept_code = d.dept_code
        GROUP BY d.dept_name
        ORDER BY d.display_order
    """)
    for m in mappings:
        print(f"  {m['dept_name']}: {m['app_count']} apps")

if __name__ == '__main__':
    seed_departments()
