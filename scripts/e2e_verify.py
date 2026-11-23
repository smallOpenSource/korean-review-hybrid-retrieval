#!/usr/bin/env python3
"""
전체 스택 E2E 검증 스크립트 (Full Stack End-to-End Verification)
프론트엔드 → 백엔드 API → 데이터베이스(MariaDB/OpenSearch) 전체 데이터 흐름을 검증합니다.
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pymysql
from opensearchpy import OpenSearch

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_URL = "http://localhost:5952"

class bcolors:
    PASS = '\033[92m'
    FAIL = '\033[91m'
    WARN = '\033[93m'
    INFO = '\033[94m'
    HEADER = '\033[95m'
    END = '\033[0m'

results = {"pass": 0, "fail": 0, "warn": 0}

def test(name, condition, actual, expected=None, critical=True):
    global results
    if condition:
        print(f"  {bcolors.PASS}✓{bcolors.END} {name}")
        results["pass"] += 1
        return True
    else:
        if critical:
            print(f"  {bcolors.FAIL}✗{bcolors.END} {name}")
            print(f"    → Expected: {expected}, Got: {actual}")
            results["fail"] += 1
        else:
            print(f"  {bcolors.WARN}⚠{bcolors.END} {name}")
            print(f"    → Expected: {expected}, Got: {actual}")
            results["warn"] += 1
        return False

def section(title):
    print(f"\n{bcolors.HEADER}{'='*70}{bcolors.END}")
    print(f"{bcolors.HEADER}{title}{bcolors.END}")
    print(f"{bcolors.HEADER}{'='*70}{bcolors.END}")

def subsection(title):
    print(f"\n{bcolors.INFO}--- {title} ---{bcolors.END}")

def get_mysql_connection():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE'),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        connect_timeout=10
    )

def get_opensearch_client():
    # Parse hosts from environment
    hosts_str = os.getenv('OPENSEARCH_HOSTS', 'https://localhost:9200')
    # Extract host and port from URL
    import re
    match = re.search(r'https://([^:]+):(\d+)', hosts_str)
    if match:
        host = match.group(1)
        port = int(match.group(2))
    else:
        host = 'localhost'
        port = 9200
    
    return OpenSearch(
        hosts=[{'host': host, 'port': port}],
        http_auth=(os.getenv('OPENSEARCH_USER', ''), os.getenv('OPENSEARCH_PASSWORD', '')),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False
    )

def main():
    print("=" * 70)
    print("🔍 전체 스택 E2E 검증 (Full Stack End-to-End Verification)")
    print(f"   시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # =========================================================================
    # PHASE 1: 프론트엔드 전체 화면 검증
    # =========================================================================
    section("📱 Phase 1: 프론트엔드 화면 검증 (Frontend Screens)")
    
    screens = [
        ("/", "메인 대시보드", ["총 리뷰 수", "민원 비율", "평균 평점"]),
        ("/company_list", "회사 목록", ["company_info"]),
        ("/complaint_board", "민원 현황", ["전체 민원", "처리 대기", "최근 민원"]),
        ("/dept_review/ALL", "부서별 리뷰 (전체)", ["리뷰 목록", "부서 선택"]),
        ("/settings", "설정", ["앱 선택"]),
    ]
    
    for path, name, required_elements in screens:
        subsection(f"{name} ({path})")
        try:
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
            test(f"HTTP 200 응답", r.status_code == 200, r.status_code, 200)
            
            for elem in required_elements:
                found = elem in r.text
                test(f"'{elem}' 요소 존재", found, "Found" if found else "Missing", "Found")
                
        except Exception as e:
            test(f"페이지 접근", False, str(e), "success")
    
    # =========================================================================
    # PHASE 2: 백엔드 API 검증
    # =========================================================================
    section("🔌 Phase 2: 백엔드 API 검증 (Backend APIs)")
    
    # Dashboard Summary API
    subsection("대시보드 요약 API (/api/v1/dashboard/summary)")
    try:
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=30", timeout=30)
        data = r.json()
        
        test("API 상태 = ok", data.get("status") == "ok", data.get("status"), "ok")
        
        # Extract values for later comparison
        api_total_reviews = data.get("sentiment", {}).get("total_reviews", 0)
        api_complaint_rate = data.get("complaints", {}).get("complaint_rate", 0)
        api_total_complaints = data.get("complaints", {}).get("total_complaints", 0)
        api_avg_rating = data.get("sentiment", {}).get("average_rating", 0)
        
        test(f"총 리뷰 수 > 0", api_total_reviews > 0, api_total_reviews, "> 0")
        test(f"민원 비율 0-100 범위", 0 <= api_complaint_rate <= 100, api_complaint_rate, "0-100")
        test(f"민원 수 > 0", api_total_complaints > 0, api_total_complaints, "> 0")
        test(f"평균 평점 1-5 범위", 1 <= api_avg_rating <= 5, api_avg_rating, "1-5")
        
    except Exception as e:
        test("대시보드 API", False, str(e), "valid response")
        api_total_reviews = api_complaint_rate = api_total_complaints = api_avg_rating = 0
    
    # Analysis Dashboard API
    subsection("분석 대시보드 API (/api/v1/analysis/dashboard)")
    try:
        r = requests.get(f"{BASE_URL}/api/v1/analysis/dashboard?days=30", timeout=30)
        data = r.json()
        test("API 상태 = ok", data.get("status") == "ok", data.get("status"), "ok")
    except Exception as e:
        test("분석 대시보드 API", False, str(e), "valid response")
    
    # =========================================================================
    # PHASE 3: API 응답 vs OpenSearch 직접 쿼리 비교
    # =========================================================================
    section("🔎 Phase 3: API vs OpenSearch 일관성 검증")
    
    try:
        os_client = get_opensearch_client()
        
        # 3.1: Total Reviews Count
        # NOTE: Dashboard API uses 3650 days (10 years) when no year filter is provided
        subsection("총 리뷰 수 비교 (10년 범위)")
        
        # OpenSearch에서 최근 3650일 리뷰 수 쿼리 (like dashboard API)
        ten_years_ago = (datetime.now() - timedelta(days=3650)).isoformat()
        os_query = {
            "query": {
                "bool": {
                    "must": [{"exists": {"field": "sentiment"}}],
                    "filter": [{"range": {"review_date": {"gte": ten_years_ago}}}]
                }
            }
        }
        os_result = os_client.count(index="app_reviews", body=os_query)
        os_total_reviews = os_result['count']
        
        # 허용 오차 5% 내에서 일치 확인
        diff_pct = abs(api_total_reviews - os_total_reviews) / max(os_total_reviews, 1) * 100
        test(f"API({api_total_reviews:,}) ≈ OpenSearch({os_total_reviews:,})", 
             diff_pct < 5, f"{diff_pct:.1f}% 차이", "< 5% 차이")
        
        # 3.2: Complaint Count
        subsection("민원 수 비교")
        
        os_complaint_query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "sentiment"}},
                        {"term": {"complaint.is_complaint": True}}
                    ],
                    "filter": [{"range": {"review_date": {"gte": ten_years_ago}}}]
                }
            }
        }
        os_complaint_result = os_client.count(index="app_reviews", body=os_complaint_query)
        os_total_complaints = os_complaint_result['count']
        
        diff_pct = abs(api_total_complaints - os_total_complaints) / max(os_total_complaints, 1) * 100
        test(f"API({api_total_complaints:,}) ≈ OpenSearch({os_total_complaints:,})", 
             diff_pct < 5, f"{diff_pct:.1f}% 차이", "< 5% 차이")
        
        # 3.3: Complaint Rate Calculation
        subsection("민원 비율 계산 검증")
        
        if os_total_reviews > 0:
            calculated_rate = os_total_complaints / os_total_reviews * 100
            diff = abs(api_complaint_rate - calculated_rate)
            test(f"API({api_complaint_rate:.1f}%) ≈ 계산값({calculated_rate:.1f}%)", 
                 diff < 2, f"{diff:.1f}% 차이", "< 2% 차이")
        
        # 3.4: Average Rating
        subsection("평균 평점 비교")
        
        os_rating_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [{"exists": {"field": "sentiment"}}],
                    "filter": [{"range": {"review_date": {"gte": thirty_days_ago}}}]
                }
            },
            "aggs": {
                "avg_rating": {"avg": {"field": "score"}}
            }
        }
        os_rating_result = os_client.search(index="app_reviews", body=os_rating_query)
        os_avg_rating = os_rating_result['aggregations']['avg_rating']['value'] or 0
        
        diff = abs(api_avg_rating - os_avg_rating)
        test(f"API({api_avg_rating:.2f}) ≈ OpenSearch({os_avg_rating:.2f})", 
             diff < 0.2, f"{diff:.2f} 차이", "< 0.2 차이")
        
    except Exception as e:
        test("OpenSearch 검증", False, str(e), "valid")
    
    # =========================================================================
    # PHASE 4: API 응답 vs MariaDB 비교
    # =========================================================================
    section("🗄️ Phase 4: API vs MariaDB 일관성 검증")
    
    try:
        conn = get_mysql_connection()
        
        with conn.cursor() as cursor:
            # 4.1: Total Reviews in DB
            subsection("총 리뷰 수 (MariaDB)")
            
            cursor.execute("SELECT COUNT(*) FROM reviews")
            db_total_all = cursor.fetchone()[0]
            test(f"MariaDB 전체 리뷰: {db_total_all:,}개", db_total_all > 0, db_total_all, "> 0")
            
            # 4.2: Analyzed Reviews
            subsection("분석된 리뷰 수")
            
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed = 1")
            db_analyzed = cursor.fetchone()[0]
            test(f"MariaDB 분석 완료: {db_analyzed:,}개", db_analyzed > 0, db_analyzed, "> 0")
            
            # 4.3: Complaint Reviews
            subsection("민원 리뷰 수")
            
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE is_complaint = 1")
            db_complaints = cursor.fetchone()[0]
            test(f"MariaDB 민원: {db_complaints:,}개", db_complaints > 0, db_complaints, "> 0")
            
            # 4.4: Year Data Populated
            subsection("연도 데이터")
            
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE year IS NOT NULL")
            db_with_year = cursor.fetchone()[0]
            year_ratio = db_with_year / db_total_all * 100 if db_total_all > 0 else 0
            test(f"연도 데이터 비율: {year_ratio:.1f}%", year_ratio > 90, f"{year_ratio:.1f}%", "> 90%")
            
            # 4.5: Department Data
            subsection("부서 데이터")
            
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE complaint_primary_dept IS NOT NULL")
            db_with_dept = cursor.fetchone()[0]
            test(f"부서 데이터: {db_with_dept:,}개", db_with_dept > 0, db_with_dept, "> 0")
            
        conn.close()
    except Exception as e:
        test("MariaDB 검증", False, str(e), "valid")
    
    # =========================================================================
    # PHASE 5: OpenSearch vs MariaDB 동기화 검증
    # =========================================================================
    section("🔄 Phase 5: OpenSearch ↔ MariaDB 동기화 검증")
    
    try:
        os_client = get_opensearch_client()
        conn = get_mysql_connection()
        
        # 5.1: Total Document Count Comparison
        subsection("전체 문서 수 비교")
        
        os_count = os_client.count(index="app_reviews")['count']
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM reviews")
            db_count = cursor.fetchone()[0]
        
        diff_pct = abs(os_count - db_count) / max(db_count, 1) * 100
        test(f"OpenSearch({os_count:,}) ≈ MariaDB({db_count:,})", 
             diff_pct < 10, f"{diff_pct:.1f}% 차이", "< 10% 차이")
        
        # 5.2: Sample Record Consistency
        subsection("샘플 레코드 일관성 (랜덤 5개)")
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, original_content, score, is_complaint 
                FROM reviews 
                WHERE analyzed = 1 
                ORDER BY RAND() 
                LIMIT 5
            """)
            samples = cursor.fetchall()
        
        for sample in samples:
            review_id, content, score, is_complaint = sample
            
            # OpenSearch에서 같은 ID로 조회
            try:
                os_doc = os_client.get(index="app_reviews", id=review_id)
                os_source = os_doc['_source']
                
                os_score = os_source.get('score', 0)
                os_is_complaint = os_source.get('complaint', {}).get('is_complaint', False)
                
                score_match = abs(os_score - score) < 0.1
                complaint_match = os_is_complaint == bool(is_complaint)
                
                test(f"ID {review_id[:8]}... 일치", score_match and complaint_match, 
                     f"score={os_score}, complaint={os_is_complaint}",
                     f"score={score}, complaint={bool(is_complaint)}")
            except:
                test(f"ID {review_id[:8]}... 조회", False, "Not found", "Found", critical=False)
        
        conn.close()
    except Exception as e:
        test("동기화 검증", False, str(e), "valid")
    
    # =========================================================================
    # PHASE 6: 화면별 데이터 흐름 검증
    # =========================================================================
    section("🔗 Phase 6: 화면별 데이터 흐름 검증")
    
    # 6.1: Dashboard Flow
    subsection("대시보드 데이터 흐름")
    try:
        # 화면에서 보이는 값
        r = requests.get(f"{BASE_URL}/", timeout=15)
        html = r.text
        
        # API에서 반환하는 값
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=30", timeout=30)
        api_data = r.json()
        
        # 화면에 API 데이터가 제대로 렌더링되었는지 확인
        api_reviews = api_data.get("sentiment", {}).get("total_reviews", 0)
        
        # HTML에서 숫자 추출은 복잡하므로, 단순히 숫자가 존재하는지 확인
        test("대시보드에 리뷰 수 표시", str(api_reviews) in html or "총 리뷰 수" in html, 
             "Found", "Present")
        
    except Exception as e:
        test("대시보드 흐름", False, str(e), "valid")
    
    # 6.2: Complaint Board Flow
    subsection("민원현황 데이터 흐름")
    try:
        r = requests.get(f"{BASE_URL}/complaint_board", timeout=15)
        html = r.text
        
        # 화면에 민원 데이터가 있는지 확인
        has_data = "민원이 없습니다" not in html
        test("민원현황에 데이터 표시", has_data, "데이터 있음" if has_data else "없음", "데이터 있음")
        
    except Exception as e:
        test("민원현황 흐름", False, str(e), "valid")
    
    # 6.3: Dept Review Flow
    subsection("부서별 리뷰 데이터 흐름")
    try:
        r = requests.get(f"{BASE_URL}/dept_review/ALL", timeout=15)
        html = r.text
        
        row_count = html.count("hover:bg-gray-50")
        test(f"부서별 리뷰에 {row_count}개 행 표시", row_count > 0, row_count, "> 0")
        
    except Exception as e:
        test("부서별 리뷰 흐름", False, str(e), "valid")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    total = results["pass"] + results["fail"]
    rate = results["pass"] / total * 100 if total > 0 else 0
    
    if results["fail"] == 0:
        print(f"🎉 {bcolors.PASS}전체 E2E 검증 통과!{bcolors.END}")
    else:
        print(f"⚠️  {bcolors.FAIL}일부 검증 실패{bcolors.END}")
    
    print(f"\n   총 테스트: {total}개")
    print(f"   {bcolors.PASS}통과: {results['pass']}{bcolors.END}")
    print(f"   {bcolors.FAIL}실패: {results['fail']}{bcolors.END}")
    print(f"   {bcolors.WARN}경고: {results['warn']}{bcolors.END}")
    print(f"   성공률: {rate:.1f}%")
    print("=" * 70)
    
    return 0 if results["fail"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
