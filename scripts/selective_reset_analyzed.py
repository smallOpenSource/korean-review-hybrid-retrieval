#!/usr/bin/env python
"""
OpenSearch 미분석 목록과 MariaDB를 비교하여
MariaDB에서 analyzed=1인데 실제로는 미분석인 문서만 선별적으로 리셋.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mysql_client import get_mysql_client

def selective_reset_analyzed_flag():
    """OpenSearch 미분석 목록 기반으로 MariaDB 선별 업데이트"""
    
    # 1. 미분석 ID 목록 로드
    unanalyzed_file = '/tmp/unanalyzed_review_ids.txt'
    
    print('=== 미분석 ID 목록 로드 ===')
    try:
        with open(unanalyzed_file, 'r') as f:
            unanalyzed_ids = [line.strip() for line in f if line.strip()]
        print(f'로드 완료: {len(unanalyzed_ids):,}개')
    except FileNotFoundError:
        print(f'에러: {unanalyzed_file} 파일이 없습니다.')
        print('먼저 extract_unanalyzed_ids.py를 실행하세요.')
        return
    
    if not unanalyzed_ids:
        print('미분석 문서가 없습니다.')
        return
    
    mysql = get_mysql_client()
    
    # 2. MariaDB에서 analyzed=1인 문서 중 매칭되는 것만 찾기
    print('\n=== MariaDB에서 매칭 확인 ===')
    
    # 배치 처리 (1000개씩)
    batch_size = 1000
    total_to_reset = 0
    reset_ids = []
    
    for i in range(0, len(unanalyzed_ids), batch_size):
        batch = unanalyzed_ids[i:i+batch_size]
        
        # IN 절로 한번에 조회
        placeholders = ','.join(['%s'] * len(batch))
        query = f'''
            SELECT review_id 
            FROM reviews 
            WHERE review_id IN ({placeholders})
            AND analyzed = 1
        '''
        
        result = mysql.execute_all(query, tuple(batch))
        
        for row in result:
            reset_ids.append(row['review_id'])
        
        if result:
            print(f'배치 {i//batch_size + 1}: {len(result)}개 발견')
    
    total_to_reset = len(reset_ids)
    
    print(f'\n총 리셋 대상: {total_to_reset:,}개')
    
    if total_to_reset == 0:
        print('리셋할 문서가 없습니다.')
        return
    
    # 3. 리셋 대상 목록 저장
    reset_list_file = '/tmp/to_reset_review_ids.txt'
    with open(reset_list_file, 'w') as f:
        for rid in reset_ids:
            f.write(f'{rid}\n')
    
    print(f'리셋 목록 저장: {reset_list_file}')
    
    # 4. 사용자 확인
    print(f'\n⚠️  {total_to_reset:,}개 문서의 analyzed 플래그를 0으로 리셋합니다.')
    print('계속하려면 "YES"를 입력하세요: ', end='')
    
    confirmation = input().strip()
    
    if confirmation != 'YES':
        print('취소되었습니다.')
        return
    
    # 5. 배치 업데이트
    print('\n=== MariaDB 업데이트 시작 ===')
    
    updated_count = 0
    
    for i in range(0, len(reset_ids), batch_size):
        batch = reset_ids[i:i+batch_size]
        
        placeholders = ','.join(['%s'] * len(batch))
        update_query = f'''
            UPDATE reviews 
            SET analyzed = 0
            WHERE review_id IN ({placeholders})
            AND analyzed = 1
        '''
        
        mysql.execute(update_query, tuple(batch))
        updated_count += len(batch)
        
        if (i + batch_size) % 5000 == 0:
            print(f'진행: {updated_count:,}/{total_to_reset:,}')
    
    print(f'\n✅ 완료: {updated_count:,}개 업데이트됨')
    
    # 6. 검증
    verify_query = '''
        SELECT COUNT(*) as count
        FROM reviews
        WHERE analyzed = 1 AND sentiment_label IS NULL
    '''
    
    result = mysql.execute_one(verify_query)
    remaining = result['count']
    
    print(f'\n검증: analyzed=1 AND sentiment_label=NULL 남은 개수: {remaining:,}')

if __name__ == '__main__':
    selective_reset_analyzed_flag()
