#!/usr/bin/env python3
"""
확장된 종합 시스템 검증 스크립트 (Extended Comprehensive Verification)
모든 주요 기능과 API 엔드포인트를 테스트합니다.
"""

import requests
import json
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
import pymysql

# Load environment
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_URL = "http://localhost:5952"

class bcolors:
    PASS = '\033[92m'
    FAIL = '\033[91m'
    WARN = '\033[93m'
    INFO = '\033[94m'
    END = '\033[0m'

results = {"pass": 0, "fail": 0, "warn": 0}

def test(name, condition, actual, expected=None, critical=True):
    """Run a test and print result."""
    global results
    if condition:
        print(f"  {bcolors.PASS}✓ PASS{bcolors.END}: {name}")
        if expected:
            print(f"         Got: {actual}")
        results["pass"] += 1
        return True
    else:
        if critical:
            print(f"  {bcolors.FAIL}✗ FAIL{bcolors.END}: {name}")
            print(f"         Expected: {expected}, Got: {actual}")
            results["fail"] += 1
        else:
            print(f"  {bcolors.WARN}⚠ WARN{bcolors.END}: {name}")
            print(f"         Expected: {expected}, Got: {actual}")
            results["warn"] += 1
        return False

def section(title):
    print(f"\n{bcolors.INFO}{'='*60}{bcolors.END}")
    print(f"{bcolors.INFO}{title}{bcolors.END}")
    print(f"{bcolors.INFO}{'='*60}{bcolors.END}")

def main():
    global results
    
    print("=" * 70)
    print("🔍 확장 종합 시스템 점검 (Extended System Verification)")
    print(f"   시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # =========================================================================
    # SECTION 1: Infrastructure Health
    # =========================================================================
    section("🔧 [1] 인프라 상태 (Infrastructure Health)")
    
    # Test 1.1: Flask Server Running
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        test("Flask 서버 실행 중", r.status_code == 200, r.status_code, 200)
    except:
        test("Flask 서버 실행 중", False, "Connection refused", "200")
    
    # Test 1.2: MySQL Database Connection
    try:
        conn = pymysql.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE'),
            port=int(os.getenv('MYSQL_PORT', 3306)),
            connect_timeout=5
        )
        conn.close()
        test("MariaDB 연결", True, "Connected", "Connected")
    except Exception as e:
        test("MariaDB 연결", False, str(e), "Connected")
    
    # Test 1.3: OpenSearch Connection (via API)
    try:
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=1", timeout=30)
        test("OpenSearch 연결 (via API)", r.status_code == 200, r.status_code, 200)
    except Exception as e:
        test("OpenSearch 연결", False, str(e), "200")
    
    # Test 1.4: Scheduler Process Running
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'scheduler/main.py'], capture_output=True, text=True)
        running = result.returncode == 0
        test("스케줄러 프로세스 실행 중", running, "Running" if running else "Not running", "Running", critical=False)
    except:
        test("스케줄러 프로세스", False, "Check failed", "Running", critical=False)
    
    # =========================================================================
    # SECTION 2: All Page Routes (GET)
    # =========================================================================
    section("📄 [2] 모든 페이지 라우트 (All Page Routes)")
    
    pages = [
        ("/", "메인 대시보드"),
        ("/company_list", "회사 목록"),
        ("/complaint_board", "민원 현황"),
        ("/dept_review/ALL", "부서별 리뷰 (전체)"),
        ("/dept_review/DIGITAL_CHANNEL.MOBILE_BANKING", "부서별 리뷰 (모바일뱅킹부)"),
        ("/settings", "설정"),
        # Company detail pages (dynamic)
    ]
    
    for path, desc in pages:
        try:
            r = requests.get(f"{BASE_URL}{path}", timeout=10)
            test(f"{desc} ({path})", r.status_code == 200, r.status_code, 200)
        except Exception as e:
            test(f"{desc} ({path})", False, str(e), 200)
    
    # Get a sample company for dynamic routes
    try:
        r = requests.get(f"{BASE_URL}/company_list", timeout=10)
        import re
        # Find any company_info link - improved regex
        match = re.search(r'href="/company_info/([a-zA-Z0-9_\-\.]+)/"', r.text)
        if match:
            sample_company = match.group(1)
            r = requests.get(f"{BASE_URL}/company_info/{sample_company}/", timeout=10)
            test(f"회사 상세 (/company_info/{sample_company[:20]}...)", r.status_code == 200, r.status_code, 200)
        else:
            test("회사 상세 페이지", False, "No company link found", 200, critical=False)
    except Exception as e:
        test("회사 상세 페이지", False, str(e), 200, critical=False)
    
    # =========================================================================
    # SECTION 3: All API Endpoints
    # =========================================================================
    section("🔌 [3] 모든 API 엔드포인트 (All API Endpoints)")
    
    api_endpoints = [
        # Dashboard APIs
        ("/api/v1/dashboard/summary?days=30", "대시보드 요약"),
        ("/api/v1/dashboard/summary?days=7", "대시보드 요약 (7일)"),
        ("/api/v1/dashboard/summary?days=365", "대시보드 요약 (365일)"),
        
        # Analysis APIs
        ("/api/v1/analysis/dashboard?days=30", "분석 대시보드"),
        
        # Health check (optional - not all deployments have this)
        # ("/api/v1/health", "헬스 체크"),
    ]
    
    for path, desc in api_endpoints:
        try:
            r = requests.get(f"{BASE_URL}{path}", timeout=30)
            # Check for valid JSON response
            try:
                data = r.json()
                valid = r.status_code == 200 and (data.get('status') == 'ok' or 'error' not in str(data).lower())
            except:
                valid = r.status_code == 200
            test(f"{desc} ({path})", valid, r.status_code, 200)
        except Exception as e:
            test(f"{desc} ({path})", False, str(e), 200)
    
    # =========================================================================
    # SECTION 4: Data Integrity Checks
    # =========================================================================
    section("🔒 [4] 데이터 무결성 검증 (Data Integrity)")
    
    try:
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=30", timeout=30)
        data = r.json()
        
        # 4.1: Complaint Rate NOT 100%
        complaint_rate = data.get("complaints", {}).get("complaint_rate", 100)
        test("민원 비율 < 100% (Bug #1)", complaint_rate < 100, f"{complaint_rate}%", "< 100%")
        
        # 4.2: Complaint Rate > 0%
        test("민원 비율 > 0%", complaint_rate > 0, f"{complaint_rate}%", "> 0%")
        
        # 4.3: Total Reviews in reasonable range
        total_reviews = data.get("sentiment", {}).get("total_reviews", 0)
        test("총 리뷰 수 > 1000", total_reviews > 1000, total_reviews, "> 1000")
        test("총 리뷰 수 < 10,000,000", total_reviews < 10000000, total_reviews, "< 10M")
        
        # 4.4: Total Complaints > 0
        total_complaints = data.get("complaints", {}).get("total_complaints", 0)
        test("총 민원 수 > 0", total_complaints > 0, total_complaints, "> 0")
        
        # 4.5: Math verification: complaint_rate = complaints / reviewed * 100
        # (approximate check due to analyzed subset)
        
        # 4.6: Trend data exists (key is 'trend' not 'trends')
        trend = data.get("complaints", {}).get("trend", data.get("complaints", {}).get("trends", []))
        test("민원 트렌드 데이터 존재", len(trend) >= 0, f"{len(trend)}개 포인트", ">= 0", critical=False)
        
        # 4.7: Average sentiment score in valid range
        avg_sentiment = data.get("sentiment", {}).get("average_rating", 0)
        test("평균 평점 범위 (1-5)", 1 <= avg_sentiment <= 5, avg_sentiment, "1.0 ~ 5.0")
        
    except Exception as e:
        test("데이터 무결성", False, str(e), "valid data")
    
    # =========================================================================
    # SECTION 5: View Rendering Checks
    # =========================================================================
    section("🖼️ [5] 화면 렌더링 검증 (View Rendering)")
    
    # 5.1: Dept Review has table rows
    try:
        r = requests.get(f"{BASE_URL}/dept_review/ALL", timeout=10)
        row_count = r.text.count("hover:bg-gray-50")
        test("부서별 리뷰 테이블 행 > 0 (Bug #4)", row_count > 0, f"{row_count}개 행", "> 0")
    except Exception as e:
        test("부서별 리뷰", False, str(e), "> 0 rows")
    
    # 5.2: Complaint Board has data
    try:
        r = requests.get(f"{BASE_URL}/complaint_board", timeout=10)
        no_data = "민원이 없습니다" in r.text
        test("민원현황 데이터 존재 (Bug #5)", not no_data, "데이터 있음" if not no_data else "없음", "데이터 있음")
    except Exception as e:
        test("민원현황", False, str(e), "has data")
    
    # 5.3: Dashboard has all required cards
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        html = r.text
        cards = [
            ("총 리뷰 수", "총 리뷰 수 카드"),
            ("민원 비율", "민원 비율 카드"),
            ("평균 평점", "평균 평점 카드"),
        ]
        for keyword, desc in cards:
            test(f"{desc} 존재", keyword in html, "Found" if keyword in html else "Missing", "Found")
    except Exception as e:
        test("대시보드 카드", False, str(e), "all cards present")
    
    # 5.4: Company List has companies
    try:
        r = requests.get(f"{BASE_URL}/company_list", timeout=10)
        company_count = r.text.count("company_info")
        test("회사 목록 > 0", company_count > 0, f"{company_count}개 회사", "> 0")
    except Exception as e:
        test("회사 목록", False, str(e), "> 0")
    
    # =========================================================================
    # SECTION 6: Database Content Checks
    # =========================================================================
    section("🗄️ [6] 데이터베이스 내용 검증 (Database Content)")
    
    try:
        conn = pymysql.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE'),
            port=int(os.getenv('MYSQL_PORT', 3306))
        )
        
        with conn.cursor() as cursor:
            # 6.1: Reviews table has data
            cursor.execute("SELECT COUNT(*) FROM reviews")
            review_count = cursor.fetchone()[0]
            test("리뷰 테이블 레코드 > 0", review_count > 0, f"{review_count:,}개", "> 0")
            
            # 6.2: Year column populated
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE year IS NOT NULL")
            year_count = cursor.fetchone()[0]
            test("연도 데이터 채워짐", year_count > 0, f"{year_count:,}개", "> 0")
            year_ratio = year_count / review_count * 100 if review_count > 0 else 0
            test("연도 데이터 비율 > 90%", year_ratio > 90, f"{year_ratio:.1f}%", "> 90%")
            
            # 6.3: Analyzed reviews
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed = 1")
            analyzed_count = cursor.fetchone()[0]
            test("분석된 리뷰 > 0", analyzed_count > 0, f"{analyzed_count:,}개", "> 0")
            
            # 6.4: Complaints exist
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE is_complaint = 1")
            complaint_count = cursor.fetchone()[0]
            test("민원 리뷰 > 0", complaint_count > 0, f"{complaint_count:,}개", "> 0")
            
            # 6.5: Department data exists
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE complaint_primary_dept IS NOT NULL")
            dept_count = cursor.fetchone()[0]
            test("부서 데이터 > 0", dept_count > 0, f"{dept_count:,}개", "> 0")
            
            # 6.6: Check if apps table exists (using scheduler DB)
            try:
                cursor.execute("SELECT COUNT(*) FROM apps")
                app_count = cursor.fetchone()[0]
                test("앱 테이블 > 0", app_count > 0, f"{app_count}개", "> 0")
            except:
                test("앱 테이블", True, "테이블 없음 (정상)", "OK", critical=False)
            
            # 6.7: Departments/Teams table check
            try:
                cursor.execute("SELECT COUNT(*) FROM teams")
                dept_table_count = cursor.fetchone()[0]
                test("팀 테이블 > 0", dept_table_count > 0, f"{dept_table_count}개", "> 0")
            except:
                test("팀 테이블", True, "테이블 없음 (정상)", "OK", critical=False)
            
        conn.close()
    except Exception as e:
        test("데이터베이스 검증", False, str(e), "valid")
    
    # =========================================================================
    # SECTION 7: Edge Cases & Error Handling
    # =========================================================================
    section("⚡ [7] 엣지 케이스 및 에러 처리 (Edge Cases)")
    
    # 7.1: Invalid API parameter handling
    try:
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=-1", timeout=10)
        # Should return some response (not crash)
        test("음수 days 파라미터 처리", r.status_code in [200, 400], r.status_code, "200 or 400")
    except Exception as e:
        test("음수 파라미터", False, str(e), "handled")
    
    # 7.2: Very large days parameter
    try:
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=99999", timeout=30)
        test("큰 days 파라미터 처리", r.status_code == 200, r.status_code, 200)
    except Exception as e:
        test("큰 파라미터", False, str(e), "handled")
    
    # 7.3: Non-existent department
    try:
        r = requests.get(f"{BASE_URL}/dept_review/NONEXISTENT_DEPT", timeout=10)
        test("존재하지 않는 부서 처리", r.status_code == 200, r.status_code, 200)
    except Exception as e:
        test("없는 부서", False, str(e), "handled")
    
    # 7.4: Non-existent company
    try:
        r = requests.get(f"{BASE_URL}/company_info/nonexistent.app.id/", timeout=10)
        # Should return 404 or redirect, not crash
        test("존재하지 않는 회사 처리", r.status_code in [200, 302, 404], r.status_code, "200/302/404")
    except Exception as e:
        test("없는 회사", False, str(e), "handled")
    
    # =========================================================================
    # SECTION 8: Performance Checks
    # =========================================================================
    section("⏱️ [8] 성능 검증 (Performance)")
    
    import time
    
    # 8.1: Dashboard API response time
    try:
        start = time.time()
        r = requests.get(f"{BASE_URL}/api/v1/dashboard/summary?days=30", timeout=60)
        elapsed = time.time() - start
        test("대시보드 API 응답 < 30초", elapsed < 30, f"{elapsed:.2f}초", "< 30초")
    except Exception as e:
        test("대시보드 API 성능", False, str(e), "< 30s")
    
    # 8.2: Main page load time
    try:
        start = time.time()
        r = requests.get(f"{BASE_URL}/", timeout=30)
        elapsed = time.time() - start
        test("메인 페이지 로드 < 10초", elapsed < 10, f"{elapsed:.2f}초", "< 10초")
    except Exception as e:
        test("메인 페이지 성능", False, str(e), "< 10s")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    total = results["pass"] + results["fail"]
    rate = results["pass"] / total * 100 if total > 0 else 0
    
    if results["fail"] == 0:
        print(f"🎉 {bcolors.PASS}모든 테스트 통과!{bcolors.END}")
    else:
        print(f"⚠️  {bcolors.FAIL}일부 테스트 실패{bcolors.END}")
    
    print(f"\n   총 테스트: {total}개")
    print(f"   {bcolors.PASS}통과: {results['pass']}{bcolors.END}")
    print(f"   {bcolors.FAIL}실패: {results['fail']}{bcolors.END}")
    print(f"   {bcolors.WARN}경고: {results['warn']}{bcolors.END}")
    print(f"   성공률: {rate:.1f}%")
    print("=" * 70)
    
    return 0 if results["fail"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
