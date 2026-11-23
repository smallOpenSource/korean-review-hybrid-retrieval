"""
Department configuration helper.
Loads department hierarchy from YAML and provides helper functions.
"""

import yaml
import os
from typing import Dict, List, Optional
from functools import lru_cache


@lru_cache(maxsize=1)
def load_department_hierarchy() -> dict:
    """Load department hierarchy from YAML file."""
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        'department_hierarchy.yaml'
    )
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_department_names() -> Dict[int, str]:
    """
    Get department ID to name mapping for backward compatibility.
    
    Returns:
        Dictionary mapping department IDs to names.
        ID 0 is reserved for "전체" (All).
    """
    hierarchy = load_department_hierarchy()
    divisions = hierarchy.get('divisions', {})
    
    # ID 0: 전체 (All)
    dept_mapping = {0: "전체"}
    
    # Map division names to IDs starting from 1
    for idx, (code, division_info) in enumerate(divisions.items(), start=1):
        dept_mapping[idx] = division_info['name']
    
    return dept_mapping


def get_division_by_id(dept_id: int) -> Optional[dict]:
    """
    Get division information by department ID.
    
    Args:
        dept_id: Department ID (0 for all, 1+ for specific divisions)
        
    Returns:
        Division info dict or None if not found
    """
    if dept_id == 0:
        return {'name': '전체', 'description': '모든 부서'}
    
    hierarchy = load_department_hierarchy()
    divisions = list(hierarchy.get('divisions', {}).values())
    
    # dept_id 1 = first division, 2 = second, etc.
    if 1 <= dept_id <= len(divisions):
        return divisions[dept_id - 1]
    
    return None


def get_all_divisions() -> List[Dict]:
    """Get list of all divisions with metadata."""
    hierarchy = load_department_hierarchy()
    divisions = hierarchy.get('divisions', {})
    
    result = []
    for idx, (code, division_info) in enumerate(divisions.items(), start=1):
        result.append({
            'id': idx,
            'code': code,
            'name': division_info['name'],
            'description': division_info.get('description', ''),
            'teams': list(division_info.get('teams', {}).keys())
        })
    
    return result


def get_division_teams(dept_id: int) -> List[Dict]:
    """
    Get teams for a specific division.
    
    Args:
        dept_id: Department ID
        
    Returns:
        List of team info dicts
    """
    division = get_division_by_id(dept_id)
    if not division or dept_id == 0:
        return []
    
    teams = division.get('teams', {})
    result = []
    
    for team_code, team_info in teams.items():
        result.append({
            'code': team_code,
            'name': team_info['name'],
            'description': team_info.get('description', ''),
            'keywords': team_info.get('keywords', [])
        })
    
    return result


# For debugging
if __name__ == '__main__':
    print("=== Department Names ===")
    dept_names = get_department_names()
    for dept_id, dept_name in dept_names.items():
        print(f"{dept_id}: {dept_name}")
    
    print("\n=== All Divisions ===")
    divisions = get_all_divisions()
    for div in divisions:
        print(f"[{div['id']}] {div['name']} ({len(div['teams'])} teams)")
