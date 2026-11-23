#!/bin/bash

# =============================================================================
# AppReviews 헤드리스 종합 점검 스크립트
# Flask 백엔드 + 템플릿 페이지 + API 엔드포인트 테스트
# =============================================================================

set -e
set +H  # 히스토리 확장 비활성화

# 설정
BASE_URL="${APP_REVIEWS_URL:-http://localhost:5952}"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 결과 저장 파일
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="/tmp/appreview_headless_results_${TIMESTAMP}.csv"
SUMMARY_FILE="/tmp/appreview_headless_summary_${TIMESTAMP}.md"

# CSV 헤더 작성
echo "category,test_name,endpoint,method,expected_status,actual_status,response_time_ms,result,error_details,timestamp" > "$RESULTS_FILE"

# 전역 변수
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 로그 함수
log_result() {
    local category="$1"
    local test_name="$2"
    local endpoint="$3"
    local method="$4"
    local expected_status="$5"
    local actual_status="$6"
    local response_time="$7"
    local result="$8"
    local error_details="$9"

    local timestamp=$(date -Iseconds)
    echo "${category},${test_name},${endpoint},${method},${expected_status},${actual_status},${response_time},${result},\"${error_details}\",${timestamp}" >> "$RESULTS_FILE"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    if [[ "$result" == "PASS" ]]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "  ${GREEN}✅ ${test_name}${NC} (${response_time}ms)"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "  ${RED}❌ ${test_name}${NC} - ${error_details}"
    fi
}

# HTTP 테스트 함수
test_endpoint() {
    local method="$1"
    local url="$2"
    local expected_status="$3"
    local headers="$4"
    local data_content="$5"
    local content_check="$6"  # 응답에 포함되어야 할 문자열

    local start_time=$(date +%s%3N)
    local temp_response="/tmp/curl_response_$$"

    if [[ "$method" == "GET" ]]; then
        if [[ -n "$headers" ]]; then
            eval "curl -s -w '\nHTTP_STATUS:%{http_code}' -k $headers \"$url\"" > "$temp_response" 2>&1
        else
            curl -s -w '\nHTTP_STATUS:%{http_code}' -k "$url" > "$temp_response" 2>&1
        fi
    else
        if [[ -n "$data_content" ]]; then
            echo "$data_content" > "/tmp/curl_data_$$"
            if [[ -n "$headers" ]]; then
                eval "curl -s -w '\nHTTP_STATUS:%{http_code}' -k -X \"$method\" $headers --data-binary \"@/tmp/curl_data_$$\" \"$url\"" > "$temp_response" 2>&1
            else
                curl -s -w '\nHTTP_STATUS:%{http_code}' -k -X "$method" --data-binary "@/tmp/curl_data_$$" "$url" > "$temp_response" 2>&1
            fi
            rm -f "/tmp/curl_data_$$"
        else
            if [[ -n "$headers" ]]; then
                eval "curl -s -w '\nHTTP_STATUS:%{http_code}' -k -X \"$method\" $headers \"$url\"" > "$temp_response" 2>&1
            else
                curl -s -w '\nHTTP_STATUS:%{http_code}' -k -X "$method" "$url" > "$temp_response" 2>&1
            fi
        fi
    fi

    local end_time=$(date +%s%3N)
    local response_time=$((end_time - start_time))

    local status_code=$(grep "HTTP_STATUS:" "$temp_response" | tail -1 | cut -d':' -f2)
    local response_body=$(grep -v "HTTP_STATUS:" "$temp_response")
    
    rm -f "$temp_response"

    if [[ -z "$status_code" ]]; then
        status_code="0"
    fi

    local result="FAIL"
    local error_msg=""

    if [[ "$status_code" == "$expected_status" ]]; then
        if [[ -n "$content_check" ]]; then
            if echo "$response_body" | grep -q "$content_check"; then
                result="PASS"
            else
                error_msg="Content check failed: '$content_check' not found"
            fi
        else
            result="PASS"
        fi
    else
        error_msg="Expected $expected_status, got $status_code"
    fi

    echo "$result|$status_code|$response_time|$error_msg"
}

# ==================== 테스트 카테고리 ====================

# 1. 서버 상태 점검
check_server_status() {
    echo -e "${BLUE}🔍 1. 서버 상태 점검${NC}"

    # Health 엔드포인트
    result=$(test_endpoint "GET" "$BASE_URL/health" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "server_status" "health_check" "$BASE_URL/health" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    echo ""
}

# 2. 페이지 렌더링 점검 (HTML)
check_pages() {
    echo -e "${BLUE}📄 2. 페이지 렌더링 점검${NC}"

    # 메인 페이지 (index)
    result=$(test_endpoint "GET" "$BASE_URL/" "200" "" "" "html")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "pages" "main_page" "$BASE_URL/" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 부서 리뷰 페이지 (ALL)
    result=$(test_endpoint "GET" "$BASE_URL/dept_review/ALL" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "pages" "dept_review_all" "$BASE_URL/dept_review/ALL" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 민원 게시판
    result=$(test_endpoint "GET" "$BASE_URL/complaint_board" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "pages" "complaint_board" "$BASE_URL/complaint_board" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 설정 페이지
    result=$(test_endpoint "GET" "$BASE_URL/settings" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "pages" "settings_page" "$BASE_URL/settings" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    echo ""
}

# 3. API 엔드포인트 점검
check_api_endpoints() {
    echo -e "${BLUE}🔌 3. API 엔드포인트 점검${NC}"

    # 대시보드 요약
    result=$(test_endpoint "GET" "$BASE_URL/api/v1/dashboard/summary" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "dashboard_summary" "$BASE_URL/api/v1/dashboard/summary" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 앱별 대시보드
    result=$(test_endpoint "GET" "$BASE_URL/api/v1/dashboard/summary?app_id=bank_c" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "dashboard_by_app" "$BASE_URL/api/v1/dashboard/summary?app_id=bank_c" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 리뷰 검색 (search endpoint - POST)
    result=$(test_endpoint "POST" "$BASE_URL/api/v1/search" "200" "-H 'Content-Type: application/json'" '{"query":"테스트","k":5}' "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "review_search" "$BASE_URL/api/v1/search" "POST" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 분석 트렌드
    result=$(test_endpoint "GET" "$BASE_URL/api/v1/analysis/trend?app_id=bank_c" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "analysis_trend" "$BASE_URL/api/v1/analysis/trend" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 민원 목록
    result=$(test_endpoint "GET" "$BASE_URL/api/v1/complaints" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "complaints_list" "$BASE_URL/api/v1/complaints" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # 회사별 분석
    result=$(test_endpoint "GET" "$BASE_URL/api/v1/analysis/company/bank_c" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "api" "company_analysis" "$BASE_URL/api/v1/analysis/company/bank_c" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    echo ""
}

# 4. 회사별 API 분석 점검
check_company_api() {
    echo -e "${BLUE}🏢 4. 회사별 API 분석 점검${NC}"

    # 주요 회사 API 테스트
    local companies=("bank_c" "bank_a" "bank_b")
    
    for company in "${companies[@]}"; do
        result=$(test_endpoint "GET" "$BASE_URL/api/v1/analysis/company/$company" "200" "" "" "")
        IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
        log_result "company_api" "api_$company" "$BASE_URL/api/v1/analysis/company/$company" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"
    done

    echo ""
}

# 5. 정적 파일 점검
check_static_files() {
    echo -e "${BLUE}📁 5. 정적 파일 점검${NC}"

    # CSS 파일 (루트 static 폴더)
    result=$(test_endpoint "GET" "$BASE_URL/static/styles.css" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "static" "css_styles" "$BASE_URL/static/styles.css" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # JavaScript 파일
    result=$(test_endpoint "GET" "$BASE_URL/static/scripts.js" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "static" "js_scripts" "$BASE_URL/static/scripts.js" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    # Chart.js 라이브러리
    result=$(test_endpoint "GET" "$BASE_URL/static/chart.min.js" "200" "" "" "")
    IFS='|' read -r test_result actual_status response_time error_details <<< "$result"
    log_result "static" "chart_js" "$BASE_URL/static/chart.min.js" "GET" "200" "$actual_status" "$response_time" "$test_result" "$error_details"

    echo ""
}

# 결과 요약 생성
generate_summary() {
    local success_rate=0
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        success_rate=$(( PASSED_TESTS * 100 / TOTAL_TESTS ))
    fi

    cat > "$SUMMARY_FILE" << EOF
# AppReviews 헤드리스 테스트 결과 요약

**테스트 실행 시간**: $(date)
**Backend URL**: $BASE_URL

## 📊 전체 결과

| 구분 | 수량 |
|------|------|
| 전체 테스트 | $TOTAL_TESTS |
| 성공 | $PASSED_TESTS |
| 실패 | $FAILED_TESTS |
| 성공률 | $success_rate% |

## 📋 카테고리별 결과

EOF

    # 카테고리별 통계 추가
    for category in "server_status" "pages" "api" "company_api" "static"; do
        local category_total=$(tail -n +2 "$RESULTS_FILE" | grep "^$category," | wc -l)
        local category_passed=$(tail -n +2 "$RESULTS_FILE" | grep "^$category," | grep ",PASS," | wc -l)
        if [[ $category_total -gt 0 ]]; then
            local category_rate=$(( category_passed * 100 / category_total ))
            echo "- **$category**: $category_passed/$category_total ($category_rate%)" >> "$SUMMARY_FILE"
        fi
    done

    cat >> "$SUMMARY_FILE" << EOF

## 🔧 실패한 테스트

EOF

    # 실패한 테스트 목록 추가
    if [[ $FAILED_TESTS -gt 0 ]]; then
        tail -n +2 "$RESULTS_FILE" | grep ",FAIL," | while IFS=',' read -r category test_name endpoint method expected actual response_time result error_details timestamp; do
            echo "- **$test_name** ($category): $error_details" >> "$SUMMARY_FILE"
        done
    else
        echo "실패한 테스트가 없습니다! 🎉" >> "$SUMMARY_FILE"
    fi
}

# 메인 실행 함수
main() {
    echo ""
    echo -e "${PURPLE}======================================${NC}"
    echo -e "${PURPLE}🚀 AppReviews 헤드리스 종합 테스트${NC}"
    echo -e "${PURPLE}======================================${NC}"
    echo -e "${CYAN}📅 $(date)${NC}"
    echo -e "${CYAN}🌐 Backend: $BASE_URL${NC}"
    echo ""

    # 각 테스트 실행
    check_server_status
    check_pages
    check_api_endpoints
    check_company_api
    check_static_files

    # 결과 요약 생성
    generate_summary

    # 최종 결과 출력
    echo -e "${PURPLE}======================================${NC}"
    echo -e "${PURPLE}🎯 테스트 완료!${NC}"
    echo -e "${PURPLE}======================================${NC}"
    echo ""
    echo -e "${YELLOW}📊 최종 결과:${NC}"
    echo -e "   전체: $TOTAL_TESTS"
    if [[ $PASSED_TESTS -gt 0 ]]; then
        echo -e "   ${GREEN}성공: $PASSED_TESTS${NC}"
    fi
    if [[ $FAILED_TESTS -gt 0 ]]; then
        echo -e "   ${RED}실패: $FAILED_TESTS${NC}"
    fi
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        local success_rate=$(( PASSED_TESTS * 100 / TOTAL_TESTS ))
        echo -e "   성공률: $success_rate%"
    fi
    echo ""
    echo -e "${CYAN}📁 생성된 파일:${NC}"
    echo -e "   📊 CSV 데이터: $RESULTS_FILE"
    echo -e "   📋 요약 보고서: $SUMMARY_FILE"
    echo ""
}

# 스크립트 실행
main "$@"
