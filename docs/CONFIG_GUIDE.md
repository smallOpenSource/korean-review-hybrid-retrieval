# 설정 파일 구조 가이드

## 📋 설정 파일 목록 및 역할

---

### 1️⃣ **.env** (환경 변수)

**용도**: 환경별로 달라지는 **비밀 정보 및 연결 설정**

**내용**:
```bash
# 데이터베이스 연결
MYSQL_HOST=db-host.example.com
MYSQL_PASSWORD=<set-in-.env>

# API 키 (민감 정보)
GEMINI_API_KEY=<set-in-.env>
OLLAMA_API_KEY=<set-in-.env>

# 환경별 설정
FLASK_ENV=production
LOG_LEVEL=INFO
ANALYSIS_CONCURRENCY=4
```

**특징**:
- ✅ 민감한 정보 (비밀번호, API 키)
- ✅ 서버별로 다른 값 (개발/운영)
- ✅ Git에 커밋 안 함 (`.gitignore` 포함)
- ✅ 간단한 key=value 형식

---

### 2️⃣ **YAML 파일들** (정적 설정)

#### 필수 YAML (실제 사용 중)

##### `scheduler/config/scheduler_config.yaml`
**용도**: 스케줄러 작업 스케줄 정의
```yaml
jobs:
  collect_reviews:
    enabled: true
    schedule: '0 */6 * * *'  # 6시간마다
    settings:
      reviews_per_app: 200
```

**특징**: 스케줄링 시간, 배치 크기 등 **동작 로직**

---

##### `app/config/prompts.yaml`
**용도**: LLM 프롬프트 템플릿
```yaml
templates:
  sentiment_analysis:
    template: |
      다음 리뷰의 감정을 분석하세요...
```

**특징**: 긴 텍스트 템플릿, 버전 관리 필요

---

##### `app/config/llm_models.yaml`
**용도**: LLM 모델별 파라미터
```yaml
task_mappings:
  sentiment_analysis:
    primary_model: gemini-2.0-flash
    temperature: 0.1
```

**특징**: 모델 선택, 파라미터 조정

---

##### `app/config/department_hierarchy.yaml`
**용도**: 부서 계층 구조 (fallback)
```yaml
departments:
  - code: CS_CENTER
    name: 고객센터
```

**특징**: DB에서 로드 실패 시 fallback

---

#### ⚠️ 레거시 YAML (현재 미사용)

##### `scheduler/config/apps_config.yaml`
**상태**: **더 이상 사용 안 함** (DB fallback용으로만 유지)  
**이유**: 앱 목록은 이제 `app_metadata` 테이블에서 로드

---

### 📊 .env vs YAML 비교

| 항목 | .env | YAML |
|------|------|------|
| **용도** | 환경별 설정 | 정적 설정 |
| **예시** | DB 비밀번호, API 키 | 프롬프트, 스케줄 |
| **변경 주기** | 드물게 (서버 이동 시) | 가끔 (로직 변경 시) |
| **버전 관리** | ❌ Git 제외 | ✅ Git 포함 |
| **형식** | 간단 (key=value) | 복잡 (계층 구조) |
| **보안** | 민감 정보 포함 | 공개 가능 |

---

## 🎯 설정 변경 가이드

### ✅ .env 수정해야 하는 경우

- DB 연결 정보 변경
- API 키 변경
- 병렬 처리 개수 조정 (`ANALYSIS_CONCURRENCY`)
- LLM fallback 순서 변경 (`LLM_FALLBACK_ORDER`)

### ✅ YAML 수정해야 하는 경우

- 스케줄 시간 변경 (`scheduler_config.yaml`)
- 프롬프트 템플릿 수정 (`prompts.yaml`)
- LLM 모델 선택 변경 (`llm_models.yaml`)

### ✅ DB 수정해야 하는 경우

- 앱 추가/삭제 (`app_metadata` 테이블)
- 부서 계층 변경 (`department_hierarchy` 테이블)

---

## 🧹 정리 권장 사항

### 1. `apps_config.yaml` → **삭제 가능**
- 이제 DB에서만 로드하므로 불필요
- 안전을 위해 fallback으로 유지 가능

### 2. `.env` → **계속 사용**
- 환경별 설정의 표준 방식
- 보안 정보 관리에 적합

### 3. 필수 YAML만 유지
- `scheduler_config.yaml` ✅
- `prompts.yaml` ✅
- `llm_models.yaml` ✅
- `department_hierarchy.yaml` ✅ (fallback)

---

## 💡 결론

**혼란 방지 원칙**:
1. **비밀·환경** → `.env`
2. **템플릿·로직** → `YAML`
3. **데이터·목록** → `Database`

간단하죠! 🎯
