#!/usr/bin/env python3
"""
파이프라인 통계 표시 스크립트

수집된 리뷰 수, 분석 완료 수, OpenSearch 동기화 수, 워드클라우드 생성시간을 표 형태로 출력합니다.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scheduler.utils.database import get_db_session
from sqlalchemy import text
from app.core.opensearch_client import get_opensearch_client


def get_mysql_stats() -> Dict[str, int]:
    """MySQL에서 리뷰 통계 조회"""
    try:
        session = get_db_session()
        
        # 전체 리뷰 수
        result = session.execute(text("SELECT COUNT(*) as count FROM reviews"))
        total_reviews = result.fetchone()[0]
        
        # 동기화된 리뷰 수
        result = session.execute(text("SELECT COUNT(*) as count FROM reviews WHERE synced_to_opensearch = 1"))
        synced_reviews = result.fetchone()[0]
        
        session.close()
        
        return {
            'total_reviews': total_reviews,
            'synced_reviews': synced_reviews
        }
    except Exception as e:
        print(f"MySQL 조회 실패: {e}", file=sys.stderr)
        return {
            'total_reviews': 0,
            'synced_reviews': 0
        }


def get_opensearch_stats() -> Dict[str, int]:
    """OpenSearch에서 통계 조회"""
    try:
        os_client = get_opensearch_client()
        client = os_client.sync_client
        index = "app_reviews"
        
        # 전체 문서 수
        total_query = {
            "query": {"match_all": {}}
        }
        total_resp = client.count(index=index, body=total_query)
        total_docs = total_resp['count']
        
        # 분석 완료된 문서 수 (sentiment 필드 존재)
        analyzed_query = {
            "query": {
                "exists": {"field": "sentiment"}
            }
        }
        analyzed_resp = client.count(index=index, body=analyzed_query)
        analyzed_docs = analyzed_resp['count']
        
        return {
            'total_docs': total_docs,
            'analyzed_docs': analyzed_docs
        }
    except Exception as e:
        print(f"OpenSearch 조회 실패: {e}", file=sys.stderr)
        return {
            'total_docs': 0,
            'analyzed_docs': 0
        }


def get_wordcloud_stats() -> List[Dict[str, Any]]:
    """워드클라우드 파일 통계 조회"""
    try:
        wordcloud_dir = Path("/var/data/wordclouds")
        
        if not wordcloud_dir.exists():
            return []
        
        files = []
        for file_path in wordcloud_dir.glob("*.png"):
            stat = file_path.stat()
            files.append({
                'filename': file_path.name,
                'created_at': datetime.fromtimestamp(stat.st_mtime)
            })
        
        # 최신순 정렬
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return files
    except Exception as e:
        print(f"워드클라우드 조회 실패: {e}", file=sys.stderr)
        return []


def print_stats():
    """통계를 표 형태로 출력"""
    print("\n" + "=" * 80)
    print("파이프라인 통계")
    print("=" * 80)
    
    # MySQL 통계
    mysql_stats = get_mysql_stats()
    print("\n[ MySQL - 리뷰 데이터 ]")
    print("-" * 80)
    print(f"{'항목':<30} {'개수':>15}")
    print("-" * 80)
    print(f"{'수집된 리뷰 (총)':<30} {mysql_stats['total_reviews']:>15,}")
    print(f"{'동기화된 리뷰 (MySQL → OS)':<30} {mysql_stats['synced_reviews']:>15,}")
    
    # OpenSearch 통계
    os_stats = get_opensearch_stats()
    print("\n[ OpenSearch - 인덱스 ]")
    print("-" * 80)
    print(f"{'항목':<30} {'개수':>15}")
    print("-" * 80)
    print(f"{'전체 문서 수':<30} {os_stats['total_docs']:>15,}")
    print(f"{'분석 완료된 문서':<30} {os_stats['analyzed_docs']:>15,}")
    print(f"{'미분석 문서':<30} {os_stats['total_docs'] - os_stats['analyzed_docs']:>15,}")
    
    # 워드클라우드 통계
    wordcloud_files = get_wordcloud_stats()
    print("\n[ 워드클라우드 - 생성된 파일 ]")
    print("-" * 80)
    
    if wordcloud_files:
        print(f"{'파일명':<50} {'생성 시간':>28}")
        print("-" * 80)
        for file_info in wordcloud_files[:10]:  # 최대 10개만 표시
            filename = file_info['filename']
            created_at = file_info['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"{filename:<50} {created_at:>28}")
        
        if len(wordcloud_files) > 10:
            print(f"\n... 외 {len(wordcloud_files) - 10}개 파일")
    else:
        print("생성된 워드클라우드가 없습니다.")
    
    print("\n" + "=" * 80)
    print(f"조회 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        print_stats()
    except KeyboardInterrupt:
        print("\n\n중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
