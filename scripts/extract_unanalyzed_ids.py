#!/usr/bin/env python
"""
OpenSearch에서 미분석 문서의 review_id 목록을 추출하여 파일로 저장.
sentiment 또는 category 필드가 없는 문서들을 찾음.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.review_service import get_review_service
import json

def extract_unanalyzed_review_ids():
    """OpenSearch에서 미분석 문서의 review_id 추출"""
    rs = get_review_service()
    
    print('=== OpenSearch 미분석 문서 추출 ===')
    
    # sentiment가 없는 문서 찾기
    query = {
        'size': 10000,  # 최대 10,000개
        '_source': ['review_id'],  # review_id만 가져오기
        'query': {
            'bool': {
                'must_not': [
                    {'exists': {'field': 'sentiment'}}
                ]
            }
        }
    }
    
    unanalyzed_ids = []
    
    # Scroll API로 모든 데이터 가져오기
    resp = rs._os.sync_client.search(
        index=rs._index,
        body=query,
        scroll='5m'
    )
    
    scroll_id = resp['_scroll_id']
    hits = resp['hits']['hits']
    
    print(f'첫 배치: {len(hits)}개')
    
    for hit in hits:
        review_id = hit['_source'].get('review_id') or hit['_id']
        unanalyzed_ids.append(review_id)
    
    # 나머지 데이터 가져오기
    while len(hits) > 0:
        resp = rs._os.sync_client.scroll(
            scroll_id=scroll_id,
            scroll='5m'
        )
        
        hits = resp['hits']['hits']
        if not hits:
            break
            
        print(f'추가 배치: {len(hits)}개, 총: {len(unanalyzed_ids)}개')
        
        for hit in hits:
            review_id = hit['_source'].get('review_id') or hit['_id']
            unanalyzed_ids.append(review_id)
    
    # Scroll 정리
    rs._os.sync_client.clear_scroll(scroll_id=scroll_id)
    
    print(f'\n총 미분석 문서: {len(unanalyzed_ids):,}개')
    
    # 파일로 저장
    output_file = '/tmp/unanalyzed_review_ids.txt'
    with open(output_file, 'w') as f:
        for rid in unanalyzed_ids:
            f.write(f'{rid}\n')
    
    print(f'저장 완료: {output_file}')
    
    # 통계 저장
    stats_file = '/tmp/unanalyzed_stats.json'
    stats = {
        'total_unanalyzed': len(unanalyzed_ids),
        'output_file': output_file,
        'sample_ids': unanalyzed_ids[:10]
    }
    
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f'통계 저장: {stats_file}')
    
    return unanalyzed_ids

if __name__ == '__main__':
    extract_unanalyzed_review_ids()
