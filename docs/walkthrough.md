# UI 복구 및 설정 구현 (UI Restoration & Settings Implementation)

## 개요
Mock 데이터 Fallback을 구현하고 "(개선중)" 라벨을 추가하여 애플리케이션 전반의 UI 가시성을 복구했습니다. 또한 시스템 구성을 위한 새로운 설정 페이지를 구현했습니다.

## 변경 사항

### 1. 대시보드 (종합분석)
- 제목에 **"(개선중)"** 라벨 추가.
- `dashboard.html` 스크립트에 **Mock 데이터 Fallback** 구현. API가 실패하거나 빈 데이터를 반환하면 차트(감성 트렌드, 분포)가 빈 상태 대신 랜덤 Mock 데이터로 렌더링됩니다.

### 2. 회사 분석 (비교분석)
- **회사 목록**: "(개선중)" 라벨 추가.
- **회사 상세**:
    - "(개선중)" 라벨 추가.
    - 감성 트렌드 차트에 **Chart.js** 구현 및 Mock 데이터 Fallback 적용.
    - 실제 데이터가 없을 경우 KPI 카드(리뷰 수, 평점, 긍정 비율)에 Mock 값 표시.
    - 워드클라우드 이미지 로드 실패 시 대체 이미지 표시.

### 3. 부서 리뷰 (리뷰분석)
- "(개선중)" 라벨 추가.
- `dept_review.html`에 **Mock 리뷰 목록** 구현하여 실제 목록이 비어있을 때 샘플 데이터를 표시.

### 4. 민원 현황 (Complaint Board)
- "(개선중)" 라벨 추가.
- **Mock 민원 통계** (전체: 45, 대기: 12, 완료: 33) 및 Mock 민원 목록을 구현하여 UI가 채워지도록 함.

### 5. 사이드바
- 민원 현황의 Mock 데이터(대기: 12)와 일치하도록 하드코딩된 배지 "12" 수정.

### 6. 설정 페이지 (시스템 설정)
- 시스템 구성을 위한 새로운 **설정 페이지** (`/settings`) 생성.
- 주요 기능:
    - **LLM Provider 선택**: OpenAI, Gemini, Anthropic 간 전환 옵션.
    - **수집 한도**: 일일 수집 한도 및 자동 수집 토글 설정.
- Flask 애플리케이션에 `settings` 블루프린트 등록.

## 검증
- 모든 페이지에 "(개선중)" 라벨이 올바르게 표시되는지 확인.
- 차트와 목록이 빈 상태 대신 Mock 데이터를 표시하는지 확인.
- 설정 페이지 접근 및 구성 폼 렌더링 확인.
- Flask 시작 시 발생하던 `ImportError` 및 `AttributeError` 해결하여 안정성 확보.

## 데이터 연결 및 검증 (Data Connection & Verification)

### 1. 메타데이터 시딩 (Metadata Seeding)
- **문제**: `app_metadata` 테이블이 비어 있어 앱 정보가 누락됨.
- **해결**:
    - `init_database.py`에 `app_metadata` 테이블 생성 로직 추가.
    - `scripts/seed_metadata.py`를 생성하여 초기 앱 데이터(E페이, L은행, K은행 등) 적재.
    - 시딩 스크립트 성공적 실행.

### 7. 동적 앱 로딩 구현 (Dynamic App Loading Implementation)
- **데이터 정제**: 68개 앱 전체에 대해 `app_metadata`의 `company_code` 슬러그(예: `bank_k`, `bank_l`)를 정리 및 업데이트.
- **백엔드 리팩토링**:
    - MySQL에서 앱 메타데이터를 관리하는 `AppService` 생성.
    - `company.py`에서 하드코딩된 `COMPANY_MAPPING`을 제거하고 `AppService`의 동적 데이터로 대체.
    - Web App이 `app_reviews_scheduler` 데이터베이스에 연결되도록 `.env` 업데이트.
- **프론트엔드 리팩토링**:
    - `company_list.html`이 Jinja2 루프를 사용하여 앱 카드를 동적으로 렌더링하도록 수정.
    - 아이콘이 없는 앱을 위한 기본 아이콘(`default.png`) Fallback 메커니즘 추가.
- **검증**:
    - `scripts/test_app_service.py`: `AppService`가 올바른 데이터를 반환하는지 검증.
    - `scripts/test_frontend.py`: 프론트엔드가 동적 데이터를 올바르게 렌더링하는지 검증.

### 8. 실제 데이터 통합 (Real Data Integration - No Mocking)
- **백엔드 수정**:
    - `app/api/v1/analysis.py`를 리팩토링하여 `AppService`를 통해 `company_code`를 `package_id`로 변환.
    - 비동기 컨텍스트 오류 방지를 위해 `aggregate_sentiment_sync` 사용으로 전환.
    - `WordAnalysisService` 버그(`AttributeError: 'OpenSearchClient' object has no attribute 'client'`) 수정.
- **프론트엔드 통합**:
    - `company_detail.html`이 `/api/v1/analysis/company/<code`에서 실제 감성 트렌드 데이터를 가져오도록 업데이트.
    - 하드코딩된 Mock 데이터 및 랜덤 숫자 생성 로직 제거.
    - `company.py` 뷰가 템플릿에 올바른 `company_name`과 `company_code`를 전달하도록 수정.
- **검증**:
    - `scripts/test_backend_analysis.py`: API가 올바른 `package_id`와 데이터 구조를 반환하는지 검증.

### 9. 설정 영구 저장 (Settings Persistence)
- **데이터베이스**:
    - Key-Value 설정을 저장할 `system_config` 테이블 생성.
    - `scripts/init_settings_db.py`를 사용하여 기본값으로 초기화.
- **백엔드**:
    - DB 작업을 관리할 `SettingsService` 구현.
    - `app/views/settings.py`가 `SettingsService`를 사용하여 설정을 조회하고 저장하도록 업데이트.
- **프론트엔드**:
    - `settings.html`이 DB 구성을 입력값에 바인딩하도록 업데이트.
    - 폼 데이터를 수집하여 `/api/v1/settings/update`로 POST하는 JavaScript 로직 추가.
- **검증**:
    - `scripts/test_settings.py`: API를 통해 설정이 업데이트되고 데이터베이스에 영구 저장되는지 검증.

### 2. 서버 구성
- **호스트 바인딩**: 외부 접속을 허용하기 위해 Flask를 `0.0.0.0`에서 실행하도록 구성.
- **포트**: 5952

### 3. API 검증
- 다음 API들이 도달 가능하고 유효한 응답을 반환하는지 확인 (리뷰 누락으로 데이터가 0건일 수 있음):
    - `GET /api/v1/dashboard/summary`
    - `GET /api/v1/complaints`
- 백엔드가 MariaDB 및 OpenSearch에 올바르게 연결되었음 확인.

### 4. 데이터베이스 스키마 수정
- **문제**: 리뷰 수집 중 `Data too long for column 'content_hash'` 오류 발생.
- **원인**: `reviews` 테이블의 `content_hash` 컬럼 길이가 SHA-256 해시(64자)를 저장하기에 부족했음.
- **해결**: `scripts/fix_schema.py`를 생성 및 실행하여 컬럼을 `VARCHAR(64)`로 변경.

### 5. 앱 메타데이터 시딩 수정
- **문제**: `app_reviews_scheduler` 데이터베이스의 `app_metadata` 테이블이 비어 있었음.
- **원인**: 원래 시딩 스크립트가 `summary` 데이터베이스를 대상으로 했으나, 스케줄러는 `app_reviews_scheduler`를 사용함.
- **해결**: `.env`가 스케줄러의 `app_reviews_scheduler`를 가리키도록 되돌림. `scripts/fix_scheduler_db.py`를 업데이트하여 `scheduler/config/apps_config.yaml`에서 68개 앱 전체 목록을 동적으로 로드하고 시딩하도록 함. 68개 앱이 모두 표시됨을 확인.
