#!/usr/bin/env python3
"""
분석 진행 상황 실시간 모니터링 스크립트

미분석 문서 수와 분석 속도를 실시간으로 표시합니다.
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.opensearch_client import get_opensearch_client


def get_analysis_stats():
    """OpenSearch에서 분석 통계 조회"""
    try:
        os_client = get_opensearch_client()
        client = os_client.sync_client
        index = "app_reviews"
        
        # 전체 문서 수
        total_query = {"query": {"match_all": {}}}
        total_resp = client.count(index=index, body=total_query)
        total_docs = total_resp['count']
        
        # 분석 완료된 문서 수
        analyzed_query = {"query": {"exists": {"field": "sentiment"}}}
        analyzed_resp = client.count(index=index, body=analyzed_query)
        analyzed_docs = analyzed_resp['count']
        
        unanalyzed = total_docs - analyzed_docs
        progress = (analyzed_docs / total_docs * 100) if total_docs > 0 else 0
        
        return {
            'total': total_docs,
            'analyzed': analyzed_docs,
            'unanalyzed': unanalyzed,
            'progress': progress
        }
    except Exception as e:
        print(f"조회 실패: {e}", file=sys.stderr)
        return None


def main():
    """실시간 모니터링"""
    print("분석 진행 상황 모니터링 (Ctrl+C로 종료)\n")
    
    prev_analyzed = None
    start_time = time.time()
    
    try:
        while True:
            stats = get_analysis_stats()
            
            if stats:
                now = datetime.now().strftime('%H:%M:%S')
                
                # 분석 속도 계산
                speed_info = ""
                if prev_analyzed is not None:
                    diff = stats['analyzed'] - prev_analyzed
                    if diff > 0:
                        speed_info = f" (+{diff} in 30s, ~{diff*2}/min)"
                
                # 진행률 바
                bar_length = 40
                filled = int(bar_length * stats['progress'] / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                print(f"\r[{now}] {bar} {stats['progress']:.1f}% | "
                      f"분석완료: {stats['analyzed']:,} | "
                      f"미분석: {stats['unanalyzed']:,}{speed_info}", 
                      end='', flush=True)
                
                prev_analyzed = stats['analyzed']
            
            time.sleep(30)
            
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n모니터링 종료 (실행 시간: {elapsed/60:.1f}분)")


if __name__ == "__main__":
    main()
