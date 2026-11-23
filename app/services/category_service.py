"""
Category Service for providing category-based statistics.
"""
from typing import Dict, List
from app.core.mysql_client import MySQLClient


class CategoryService:
    """Service for category-based statistics and analytics."""
    
    # Korean name mapping for group codes
    GROUP_CODE_KOREAN_NAMES = {
        'banks': '은행',
        'cards': '카드',
        'fintech': '핀테크',
        'securities': '증권',
        'life_insurance': '생명보험',
        'non_life_insurance': '손해보험',
    }
    
    def __init__(self):
        self.mysql = MySQLClient()
    
    def get_category_stats(self) -> Dict[str, int]:
        """
        Get app count by category.
        
        Returns:
            Dict mapping group_code to count
        """
        query = """
            SELECT group_code, COUNT(*) as count
            FROM app_metadata
            WHERE group_code IS NOT NULL
            GROUP BY group_code
            ORDER BY count DESC
        """
        
        results = self.mysql.execute_all(query)
        return {row['group_code']: row['count'] for row in results}
    
    def get_category_stats_korean(self) -> List[Dict[str, any]]:
        """
        Get app count by category with Korean names.
        
        Returns:
            List of dicts with korean_name and count,sorted by count desc
        """
        stats = self.get_category_stats()
        
        result = []
        for group_code, count in stats.items():
            korean_name = self.GROUP_CODE_KOREAN_NAMES.get(group_code, group_code)
            result.append({
                'group_code': group_code,
                'korean_name': korean_name,
                'count': count
            })
        
        # Sort by count descending
        result.sort(key=lambda x: x['count'], reverse=True)
        return result
    
    def format_category_summary(self) -> str:
        """
        Format category statistics as summary text.
        
        Returns:
            String like "은행(20), 증권(14), 카드(9), 생명보험(9), 핀테크(8), 손해보험(8)"
        """
        stats = self.get_category_stats_korean()
        parts = [f"{s['korean_name']}({s['count']})" for s in stats]
        return ", ".join(parts) + " 종합분석"


# Singleton instance
_category_service = None

def get_category_service() -> CategoryService:
    """Get singleton instance of CategoryService."""
    global _category_service
    if _category_service is None:
        _category_service = CategoryService()
    return _category_service
