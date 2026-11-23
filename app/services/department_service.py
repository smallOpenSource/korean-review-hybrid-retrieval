"""
Department Management Service.
"""
from typing import List, Dict, Optional
from app.core.mysql_client import MySQLClient


class DepartmentService:
    """Service for managing departments and app-department mappings."""
    
    def __init__(self):
        self.mysql = MySQLClient()
    
    def get_all_departments(self) -> List[Dict]:
        """Get all departments ordered by display_order."""
        query = """
            SELECT dept_code, dept_name, dept_name_en, parent_dept_code, display_order,
                   created_at, updated_at
            FROM departments
            ORDER BY display_order, dept_code
        """
        return self.mysql.execute_all(query)
    
    def get_department_by_code(self, dept_code: str) -> Optional[Dict]:
        """Get a single department by code."""
        query = """
            SELECT dept_code, dept_name, dept_name_en, parent_dept_code, display_order,
                   created_at, updated_at
            FROM departments
            WHERE dept_code = %s
        """
        return self.mysql.execute_one(query, (dept_code,))
    
    def create_department(self, dept_data: Dict) -> bool:
        """Create a new department."""
        query = """
            INSERT INTO departments
            (dept_code, dept_name, dept_name_en, parent_dept_code, display_order)
            VALUES (%s, %s, %s, %s, %s)
        """
        try:
            self.mysql.execute(
                query,
                (
                    dept_data['dept_code'],
                    dept_data['dept_name'],
                    dept_data.get('dept_name_en'),
                    dept_data.get('parent_dept_code'),
                    dept_data.get('display_order', 0)
                )
            )
            return True
        except Exception as e:
            logger.error(f"Error creating department: {e}")
            return False
    
    def update_department(self, dept_code: str, dept_data: Dict) -> bool:
        """Update an existing department."""
        query = """
            UPDATE departments
            SET dept_name = %s,
                dept_name_en = %s,
                parent_dept_code = %s,
                display_order = %s
            WHERE dept_code = %s
        """
        try:
            self.mysql.execute(
                query,
                (
                    dept_data['dept_name'],
                    dept_data.get('dept_name_en'),
                    dept_data.get('parent_dept_code'),
                    dept_data.get('display_order', 0),
                    dept_code
                )
            )
            return True
        except Exception as e:
            logger.error(f"Error updating department: {e}")
            return False
    
    def delete_department(self, dept_code: str) -> bool:
        """Delete a department (will cascade delete mappings)."""
        query = "DELETE FROM departments WHERE dept_code = %s"
        try:
            self.mysql.execute(query, (dept_code,))
            return True
        except Exception as e:
            logger.error(f"Error deleting department: {e}")
            return False
    
    def get_department_apps(self, dept_code: str) -> List[Dict]:
        """Get all apps mapped to a department."""
        query = """
            SELECT adm.package_id, am.company_name, am.group_code
            FROM app_department_mapping adm
            JOIN app_metadata am ON adm.package_id = am.package_id
            WHERE adm.dept_code = %s
        """
        return self.mysql.execute_all(query, (dept_code,))
    
    def add_app_to_department(self, package_id: str, dept_code: str) -> bool:
        """Map an app to a department."""
        query = """
            INSERT INTO app_department_mapping (package_id, dept_code)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE dept_code = VALUES(dept_code)
        """
        try:
            self.mysql.execute(query, (package_id, dept_code))
            return True
        except Exception as e:
            logger.error(f"Error adding app to department: {e}")
            return False
    
    def remove_app_from_department(self, package_id: str, dept_code: str) -> bool:
        """Remove app-department mapping."""
        query = "DELETE FROM app_department_mapping WHERE package_id = %s AND dept_code = %s"
        try:
            self.mysql.execute(query, (package_id, dept_code))
            return True
        except Exception as e:
            logger.error(f"Error removing app from department: {e}")
            return False
    
    def get_department_stats(self) -> List[Dict]:
        """Get statistics for all departments (app count)."""
        query = """
            SELECT d.dept_code, d.dept_name, COUNT(adm.package_id) as app_count
            FROM departments d
            LEFT JOIN app_department_mapping adm ON d.dept_code = adm.dept_code
            GROUP BY d.dept_code, d.dept_name
            ORDER BY d.display_order
        """
        return self.mysql.execute_all(query)


# Singleton instance
_department_service = None

def get_department_service() -> DepartmentService:
    """Get singleton instance of DepartmentService."""
    global _department_service
    if _department_service is None:
        _department_service = DepartmentService()
    return _department_service
