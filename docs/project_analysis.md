# App Reviews Analysis System - 프로젝트 분석 보고서

## 📋 프로젝트 개요

**App Reviews Analysis System**은 Google Play Store의 한국 금융 앱 리뷰를 수집, 분석, 분류하는 Multi-Agent 기반 시스템입니다.

### 주요 목적
- 📱 **리뷰 자동 수집**: Google Play Store API를 통한 앱 리뷰 정기 수집
- 🤖 **AI 기반 분석**: Gemini LLM을 활용한 감성 분석, 카테고리 분류, 민원 분류
- 🔍 **검색 및 유사도**: OpenSearch KNN을 통한 벡터 기반 유사 리뷰 검색
- 📊 **데이터 분석**: 리뷰 트렌드, 단어 빈도, 인사이트 생성
- 🎯 **민원 라우팅**: 자동 부서 배정 및 우선순위 관리

---

## 🏗️ 시스템 아키텍처

### 전체 구조

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Application (Flask)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Views      │  │   API v1     │  │   Templates     │  │
│  │  (HTML UI)   │  │   (REST)     │  │  (Jinja2)       │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Services Layer                            │  │
│  │ ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐  │  │
│  │ │ Review  │ │  Dedup   │ │  Word   │ │ Similar  │  │  │
│  │ │ Service │ │  Service │ │ Analysis│ │  Review  │  │  │
│  │ └─────────┘ └──────────┘ └─────────┘ └──────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Multi-Agent System (Orchestrator)            │  │
│  │ ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐  │  │
│  │ │Sentiment│ │ Category │ │Complaint│ │ Insight  │  │  │
│  │ │  Agent  │ │  Agent   │ │  Agent  │ │  Agent   │  │  │
│  │ └─────────┘ └──────────┘ └────────┘ └──────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               Core Infrastructure                     │  │
│  │ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐  │  │
│  │ │OpenSearch│ │  Redis  │ │  MySQL  │ │   LLM    │  │  │
│  │ │  Client  │ │ Client  │ │ Client  │ │  Client  │  │  │
│  │ └──────────┘ └─────────┘ └─────────┘ └──────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Scheduler Service (APScheduler)              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Collect    │  │   Analyze    │  │    WordCloud    │  │
│  │   Reviews    │  │   Reviews    │  │    Generator    │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘

                          ▼ ▼ ▼

┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  OpenSearch  │  │    Redis     │  │    MySQL     │
│   (KNN +     │  │  Sentinel    │  │ (Partitioned)│
│    Nori)     │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 🔧 기술 스택

### Backend Framework
| 영역 | 기술 | 버전 | 용도 |
|------|------|------|------|
| Web Framework | Flask | 2.x | 웹 애플리케이션 |
| WSGI Server | Gunicorn | - | 프로덕션 서버 |
| Validation | Pydantic | - | API 요청/응답 검증 |
| Scheduler | APScheduler | - | 배치 작업 스케줄링 |
| Async | aiohttp | - | 비동기 HTTP 요청 |

### AI & LLM
| 영역 | 기술 | 설명 |
|------|------|------|
| Primary LLM | Google Gemini | 2.5 Flash, 2.0 Flash, 1.5 Pro |
| Embedding | Gemini Embedding | 1024차원 벡터 |
| Fallback #1 | Ollama | 로컬 LLM |
| Fallback #2 | Groq | Llama 3.1 |
| Fallback #3 | OpenAI | GPT-4o-mini |
| Korean Embedding | BGE-M3-KO | upskyy/bge-m3-ko (1024차원) |
| Reranking | BGE-Reranker-v2-M3 | 검색 결과 재정렬 |

### Data Storage & Search
| 영역 | 기술 | 버전 | 용도 |
|------|------|------|------|
| Database | MySQL | 8.x | 리뷰 데이터 저장 (파티셔닝) |
| Search Engine | OpenSearch | 2.x | 전문 검색 + KNN 벡터 검색 |
| Korean Analyzer | Nori | - | 한국어 형태소 분석 |
| Cache | Redis Sentinel | 6.x+ | 캐싱 및 고가용성 |

### Frontend
| 영역 | 기술 | 용도 |
|------|------|------|
| Template Engine | Jinja2 | HTML 렌더링 |
| CSS Framework | Tailwind CSS | 스타일링 |
| JavaScript | Alpine.js | 경량 인터랙티브 |
| Charting | ECharts | 데이터 시각화 |

### Python 패키지
```
Flask, python-dotenv, gunicorn, PyMySQL, DBUtils
opensearch-py, redis, google-generativeai, google-api-core
konlpy, sentence-transformers, torch, numpy, scipy
PyYAML, pydantic, aiohttp, structlog, pytz
pytest, pytest-asyncio, prometheus-client
```

---

## 📁 프로젝트 구조 상세

```
appReviews/
├── app/                          # Flask 메인 애플리케이션
│   ├── __init__.py               # Application Factory Pattern
│   ├── agents/                   # Multi-Agent System
│   │   ├── base_agent.py         # 기본 에이전트 클래스
│   │   ├── sentiment_agent.py    # 감성 분석 에이전트
│   │   ├── category_agent.py     # 카테고리 분류 에이전트
│   │   ├── complaint_agent.py    # 민원 분류 에이전트
│   │   ├── insight_agent.py      # 인사이트 생성 에이전트
│   │   ├── llm_client.py         # Gemini API 클라이언트
│   │   ├── embedding_service.py  # 임베딩 서비스 (Gemini/BGE)
│   │   └── rerank_service.py     # Reranking 서비스
│   ├── api/                      # REST API
│   │   ├── models.py             # Pydantic Request/Response 모델
│   │   └── v1/                   # API v1
│   │       ├── reviews.py        # 리뷰 CRUD 엔드포인트
│   │       ├── analysis.py       # 분석 엔드포인트
│   │       ├── complaints.py     # 민원 관리 엔드포인트
│   │       └── search.py         # 검색 엔드포인트
│   ├── config/                   # 설정 파일
│   │   ├── settings.py           # 환경 변수 기반 설정 (Dataclass)
│   │   ├── llm_models.yaml       # LLM 모델 구성 및 Rate Limit
│   │   ├── prompts.yaml          # Agent 프롬프트 템플릿
│   │   └── department_hierarchy.yaml  # 부서 조직도 및 라우팅 규칙
│   ├── core/                     # 핵심 인프라 클라이언트
│   │   ├── opensearch_client.py  # OpenSearch 연결 및 KNN 검색
│   │   ├── redis_client.py       # Redis Sentinel 연결
│   │   ├── mysql_client.py       # MySQL 연결 풀
│   │   └── rate_limiter.py       # LLM API Rate Limiter
│   ├── services/                 # 비즈니스 로직
│   │   ├── review_service.py     # 리뷰 CRUD 및 분석 로직
│   │   ├── dedup_service.py      # 중복 리뷰 제거
│   │   ├── word_analysis_service.py  # 단어 빈도 분석
│   │   ├── similar_review_service.py # 유사 리뷰 검색
│   │   └── department_routing_service.py  # 부서 자동 배정
│   ├── views/                    # HTML 페이지 라우트
│   │   └── main_views.py         # 대시보드, 리뷰 목록 등
│   ├── templates/                # Jinja2 템플릿
│   └── static/                   # CSS, JS, 이미지
│
├── scheduler/                    # 배치 작업 스케줄러
│   ├── main.py                   # APScheduler 메인 엔트리포인트
│   ├── jobs/                     # 스케줄된 작업들
│   │   ├── collect_reviews.py    # 리뷰 수집 작업
│   │   ├── analyze_reviews.py    # 리뷰 분석 작업
│   │   ├── generate_wordcloud.py # 워드클라우드 생성
│   │   └── sync_to_opensearch.py # OpenSearch 동기화
│   ├── collectors/               # 데이터 수집기
│   ├── utils/                    # 유틸리티
│   └── config/                   # 스케줄러 설정
│
├── models/                       # 학습된 모델 파일
│   ├── models--BAAI--bge-m3      # BGE-M3 임베딩 모델
│   └── models--BAAI--bge-reranker-v2-m3  # BGE Reranker
│
├── scripts/                      # 유틸리티 스크립트
│   └── scheduler/
│       └── schema/
│           └── reviews_table.sql  # 리뷰 테이블 DDL
│
├── docs/                         # 문서
│   ├── architecture.puml         # PlantUML 아키텍처 다이어그램
│   ├── openapi.yaml              # OpenAPI 스펙
│   └── scheduler/                # 스케줄러 관련 문서
│
├── test/                         # 테스트
├── .env.example                 # 환경 변수 템플릿
├── run.sh                        # 애플리케이션 실행 스크립트
└── README.md                     # 프로젝트 README
```

---

## 🤖 Multi-Agent 시스템

### Agent 구성

#### 1. **Sentiment Agent** (감성 분석)
- **모델**: Gemini 2.0 Flash → Gemini 1.5 Flash (fallback)
- **기능**: 리뷰의 감성 분석 (5단계: very_negative → very_positive)
- **출력**: 감성 라벨, 점수, 감정 태그, 신뢰도, reasoning

#### 2. **Category Agent** (카테고리 분류)
- **모델**: Gemini 2.0 Flash → Gemini 1.5 Flash
- **기능**: 리뷰를 14개 카테고리로 분류 (로그인, 이체, 결제, UI/UX 등)
- **출력**: Primary/Secondary 카테고리, 메트릭, reasoning

#### 3. **Complaint Agent** (민원 분류)
- **모델**: Gemini 2.0 Flash → Gemini 1.5 Flash
- **기능**: 
  - 민원 여부 판단
  - 민원 유형 분류 (개선요청, 불만, 오류신고, 피해신고 등)
  - 긴급도 (1-4) 및 심각도 (1-5) 평가
  - 담당 부서 자동 배정 (Primary + Secondary)
  - Escalation 필요성 판단
- **출력**: 민원 정보, 부서 배정, 우선순위, reasoning

#### 4. **Insight Agent** (인사이트 생성)
- **모델**: Gemini 1.5 Pro → Gemini 2.0 Flash
- **기능**: 대량 리뷰 데이터 기반 트렌드 및 인사이트 생성
- **출력**: 핵심 인사이트, 근본 원인 분석, 개선 제안, reasoning

### Prompt Engineering
- **템플릿 기반**: `app/config/prompts.yaml`에 모든 프롬프트 집중 관리
- **변수 치환**: Python Template 문법 (`$variable_name`)
- **Reasoning 필수**: 모든 Agent 응답에 reasoning 필드 포함 (판단 근거 추적)
- **JSON 응답**: 구조화된 JSON 포맷으로 응답 강제

### Rate Limiting
- **Tier 기반**: Free/Pro/Enterprise 티어별 Rate Limit
- **Token Bucket 알고리즘**: RPM, RPD, TPM 제한
- **자동 Fallback**: Primary 모델 제한 시 Secondary 모델 사용
- **우선순위 큐**: 긴급 요청 우선 처리

---

## 🔍 검색 및 임베딩

### OpenSearch 구성

#### 인덱스 구조
1. **app_reviews**: 리뷰 원본 데이터
   - Nori 분석기: 한국어 형태소 분석 (BM25 검색용)
   - KNN 벡터 필드: 1024차원 임베딩 (코사인 유사도)
   
2. **review_analytics**: 분석 결과 저장
   - Agent 분석 결과 (sentiment, category, complaint)
   - 집계 데이터 (트렌드, 통계)

#### 검색 기능
- **전문 검색**: Nori 분석기 기반 BM25 검색
- **벡터 검색**: KNN 알고리즘으로 유사 리뷰 찾기
- **하이브리드 검색**: BM25 + KNN 결합 후 Reranking

### Embedding 전략

#### Primary: Gemini Embedding
- 모델: `gemini-embedding-001`
- 차원: 1024
- RPM: 1500 (Free tier)

#### Fallback: BGE-M3-KO
- 모델: `upskyy/bge-m3-ko`
- 차원: 1024 (Gemini와 동일)
- 한국어 특화: 높은 정확도
- 로컬 실행 가능 (CPU/GPU)

#### Reranking
- 모델: `BAAI/bge-reranker-v2-m3`
- 검색 결과 재정렬로 정확도 향상

---

## 💾 데이터베이스 구조

### MySQL 스키마

#### `reviews` 테이블 (메인)
```sql
CREATE TABLE reviews (
  -- Primary Key
  id BIGINT AUTO_INCREMENT,
  
  -- 리뷰 식별
  review_id VARCHAR(255) NOT NULL,
  package_id VARCHAR(255) NOT NULL,
  
  -- 콘텐츠 (3가지 버전)
  content TEXT NOT NULL,              -- Play Store 원본
  original_content TEXT,              -- 사람이 읽기 좋은 버전
  cleaned_content TEXT,               -- NLP용 (한글+숫자만)
  
  -- 평점 및 메타데이터
  score FLOAT DEFAULT 0,
  thumbs_up_count INT DEFAULT 0,
  
  -- 타임스탬프
  at DATETIME NOT NULL,               -- 리뷰 작성 시각
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  
  -- 분석 상태
  analyzed BOOLEAN DEFAULT FALSE,
  analysis_failed BOOLEAN DEFAULT FALSE,
  
  -- OpenSearch 동기화
  synced_to_opensearch BOOLEAN DEFAULT FALSE,
  synced_at TIMESTAMP NULL,
  
  -- 인덱스
  PRIMARY KEY (id, at),
  KEY idx_review_id (review_id),
  KEY idx_package_id (package_id),
  KEY idx_analyzed (analyzed)
  
) PARTITION BY RANGE (YEAR(at)) (
  PARTITION p2023 VALUES LESS THAN (2024),
  PARTITION p2024 VALUES LESS THAN (2025),
  PARTITION p2025 VALUES LESS THAN (2026),
  PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

**파티셔닝 전략**
- 연도별 Range 파티셔닝
- 쿼리 성능 최적화 (특정 연도 데이터만 스캔)
- 오래된 데이터 아카이빙 용이

#### `app_metadata` 테이블
- 앱 정보 (package_id, 회사명, 카테고리, 우선순위)
- Play Store 메타데이터 (제목, 평점, 설치 수)

#### `job_runs` 테이블
- 스케줄러 작업 실행 이력
- 성공/실패 추적, 중복 방지

---

## ⚙️ 설정 관리

### 환경 변수 (.env)
```bash
# Flask
FLASK_ENV=development
FLASK_PORT=5000

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_DATABASE=summary

# OpenSearch
OPENSEARCH_HOSTS=https://localhost:9200
OPENSEARCH_USER=admin

# Redis Sentinel
REDIS_SENTINEL_HOSTS=localhost:26379,localhost:26380,localhost:26381
REDIS_SENTINEL_MASTER_NAME=mymaster

# Gemini LLM
GEMINI_API_KEY=<set-in-.env>
GEMINI_MODEL_REALTIME=gemini-2.0-flash
GEMINI_MODEL_INSIGHT=gemini-1.5-pro

# BGE Embedding
BGE_EMBEDDING_API_URL=http://api.server.com/embed
BGE_LOCAL_EMBEDDING_MODEL=upskyy/bge-m3-ko
```

### YAML 설정 파일

#### `llm_models.yaml`
- 모델별 스펙 (context_window, rate_limits)
- Task별 모델 매핑 (sentiment → gemini-2.0-flash)
- Primary/Secondary 모델 정의
- Retry 설정 (백오프 전략)

#### `prompts.yaml`
- Agent별 프롬프트 템플릿
- 부서 코드 및 설명
- 리뷰 카테고리 목록

#### `department_hierarchy.yaml`
- 부서 조직도 및 계층 구조
- 부서별 키워드 및 라우팅 규칙

### Dataclass 기반 Settings (`app/config/settings.py`)
```python
@dataclass
class Settings:
    flask: FlaskConfig
    mysql: MySQLConfig
    opensearch: OpenSearchConfig
    redis: RedisSentinelConfig
    gemini: GeminiConfig
    bge: BGEConfig
    rate_limit: RateLimitConfig
    logging: LoggingConfig
    app: AppConfig
```
- Type-safe 설정 접근
- `@lru_cache`로 싱글톤 패턴
- IDE 자동완성 지원

---

## 📊 스케줄러 (APScheduler)

### 작업 스케줄

#### 1. **리뷰 수집** (`collect_reviews`)
- **High Priority 앱**: 4시간마다
- **Medium Priority 앱**: 8시간마다
- **Low Priority 앱**: 매일 새벽 2시

#### 2. **리뷰 분석** (`analyze_reviews`)
- **주기**: 1시간마다
- **대상**: `analyzed=FALSE` 리뷰
- **처리**: Multi-Agent 순차 실행

#### 3. **워드클라우드 생성** (`generate_wordcloud`)
- **주기**: 매일 새벽 3시
- **출력**: 이미지 파일 저장

#### 4. **OpenSearch 동기화** (`sync_to_opensearch`)
- **대상**: `synced_to_opensearch=FALSE` 리뷰
- **기능**: 벡터 임베딩 생성 및 인덱싱

### 실행 방식
```bash
# 스케줄러 데몬 실행
python -m scheduler.main

# 특정 작업 1회 실행
python -m scheduler.main --run-once collect_high

# 앱 목록 확인
python -m scheduler.main --list-apps

# 설정 검증
python -m scheduler.main --validate
```

---

## 🌐 API 엔드포인트

### Reviews API
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reviews` | 리뷰 목록 조회 (페이지네이션) |
| GET | `/api/v1/reviews/{id}` | 리뷰 상세 조회 |
| GET | `/api/v1/reviews/{id}/similar` | 유사 리뷰 검색 |
| POST | `/api/v1/reviews/search/similar` | 텍스트 기반 유사 검색 |

### Analysis API
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/analysis/dashboard` | 대시보드 데이터 |
| GET | `/api/v1/analysis/company/{code}` | 회사별 분석 |
| GET | `/api/v1/analysis/trend` | 트렌드 분석 |
| GET | `/api/v1/analysis/words` | 단어 빈도 분석 |
| GET | `/api/v1/analysis/words/{word}/trend` | 단어 트렌드 |

### Complaints API
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/complaints` | 민원 목록 |
| POST | `/api/v1/complaints/route` | 민원 부서 배정 |

### 응답 형식 (Pydantic)
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2025-11-25T12:00:00Z",
    "latency_ms": 125,
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 500
    }
  }
}
```

---

## 🎯 주요 특징

### 1. **고가용성 아키텍처**
- Redis Sentinel: 자동 Failover
- MySQL 파티셔닝: 성능 최적화
- Rate Limiter: API 과부하 방지

### 2. **LLM Provider Fallback Chain**
```
Gemini API (Primary)
  ↓ (Rate Limit 도달 시)
Ollama (Fallback #1, 로컬)
  ↓ (사용 불가 시)
Groq (Fallback #2, Llama 3.1)
  ↓ (사용 불가 시)
OpenAI (Fallback #3, GPT-4o-mini)
```

### 3. **데이터 품질 관리**
- 중복 제거: `content_hash` 기반 Deduplication
- 3가지 콘텐츠 버전: 원본, 가독성, NLP용
- 분석 실패 추적: `analysis_failed` 플래그

### 4. **한국어 최적화**
- Nori 형태소 분석기
- BGE-M3-KO 임베딩 (한국어 특화)
- 한글 전처리 파이프라인

### 5. **관찰성 (Observability)**
- Structured Logging (structlog, JSON)
- Prometheus 메트릭
- API 요청 추적 (request_id, latency)

---

## 🚀 실행 방법

### 1. 환경 설정
```bash
cp .env.example .env
# .env 파일 수정 (API 키, DB 정보 등)
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 애플리케이션 실행
```bash
# Development
./run.sh

# Production
FLASK_ENV=production ./run.sh
```

# 프로젝트 감사 보고서 - 최종 상태

**날짜:** 2025-11-27
**상태:** 완료됨

## 1. 요약
본 프로젝트는 하드코딩된 데이터와 Mock 데이터를 사용하는 프로토타입에서, 실제 데이터베이스 기반의 동적 시스템으로 완전히 전환되었습니다. 모든 핵심 기능(대시보드, 회사 목록, 상세 분석, 설정, 민원)이 백엔드 API 및 실제 데이터 소스(MySQL, OpenSearch)와 연동되었습니다.

## 2. 컴포넌트 상태

| 컴포넌트 | 상태 | 구현 상세 |
| :--- | :--- | :--- |
| **Backend API** | ✅ 검증됨 | `analysis.py`, `company.py`, `complaints.py`, `settings.py`의 모든 엔드포인트가 서비스와 연동됨. |
| **Data Layer** | ✅ 검증됨 | `AppService` (MySQL), `ReviewService` (OpenSearch), `SettingsService` (MySQL) 구현 및 테스트 완료. |
| **회사 목록** | ✅ 검증됨 | `app_metadata`에서 68개 앱을 동적으로 로딩. 아이콘 Fallback 구현. |
| **회사 상세** | ✅ 검증됨 | 감성 차트 및 워드클라우드가 `/api/v1/analysis/company` API와 연동됨. |
| **설정** | ✅ 검증됨 | `system_config` 테이블에 설정값 영구 저장. |
| **대시보드** | ✅ 검증됨 | 주요 통계 및 랭킹을 `ReviewService`에서 조회. Mock 데이터는 Fallback으로만 존재. |
| **민원** | ✅ 검증됨 | OpenSearch에서 최근 민원 데이터 조회. |

## 3. 코드 품질 및 아키텍처
- **Service Pattern**: 비즈니스 로직을 서비스 계층(`AppService`, `ReviewService`, `SettingsService`)으로 캡슐화하여 뷰를 깔끔하게 유지.
- **Async/Sync**: `analysis.py`의 혼합된 비동기/동기 호출 문제 해결.
- **Configuration**: 환경 변수는 `.env`와 `settings.py`로 관리하며, 시스템 설정은 DB에 저장.
- **Testing**: 안정성 확보를 위한 검증 스크립트(`test_backend_analysis.py`, `test_frontend_integration.py`, `test_settings.py`) 추가.

## 4. 향후 과제 (Future Work)
- **고급 필터링**: `dashboard.py`의 `dashboard_filtered` 라우트에 연도/차트 타입 필터링 구현 필요 (현재 TODO).
- **Query Agent**: `search.py`에 자연어 검색을 위한 `QueryAgent` 통합 필요 (현재 TODO).
- **데이터 수집**: 스케줄러가 지속적으로 실행되어 최신 데이터를 유지해야 함.

## 5. 결론
시스템은 이제 견고하고 동적이며, 프로덕션 수준의 사용 준비가 완료되었습니다. "하드코딩된 데이터" 문제는 완전히 해결되었습니다.

---

## 📝 코드 품질 특징

### Design Patterns
- **Factory Pattern**: Flask Application Factory
- **Singleton Pattern**: Settings (`@lru_cache`)
- **Strategy Pattern**: LLM Provider Fallback
- **Observer Pattern**: Rate Limiter Events

### 타입 안정성
- Pydantic: API 요청/응답 검증
- Dataclass: 설정 관리
- Type Hints: 대부분의 함수에 타입 명시

### 테스트
- pytest 기반 테스트 프레임워크
- 비동기 테스트: pytest-asyncio
- 커버리지: pytest-cov

---

## 🔐 보안 고려사항

1. **환경 변수 관리**
   - `.env` 파일은 `.gitignore`에 포함
   - `.env.example`만 버전 관리

2. **API 인증**
   - OpenSearch: Basic Auth (user/password)
   - Redis: 선택적 비밀번호
   - Gemini/BGE: API Key (Bearer Token)

3. **SQL Injection 방지**
   - PyMySQL parameterized queries
   - ORM 미사용이지만 파라미터화된 쿼리 사용

4. **Rate Limiting**
   - LLM API 과도한 호출 방지
   - 비용 관리 및 서비스 안정성

---

## 📈 확장 가능성

### 수평 확장
- Flask: Gunicorn 멀티 워커
- MySQL: Read Replica 추가 가능
- Redis: Sentinel 노드 추가

### 기능 확장
- 추가 LLM Provider 연동 (Claude, PaLM 등)
- 더 많은 Agent 추가 (요약, 번역 등)
- 실시간 알림 (Slack, Email)
- 대시보드 고도화

---

## 🎓 학습 포인트

이 프로젝트는 다음을 학습하기에 좋은 예제입니다:

1. **Multi-Agent LLM 시스템 설계**
2. **벡터 검색 및 RAG 구현**
3. **Flask 애플리케이션 아키텍처**
4. **APScheduler 배치 처리**
5. **OpenSearch KNN 활용**
6. **Redis Sentinel 고가용성**
7. **MySQL 파티셔닝**
8. **YAML 기반 설정 관리**
9. **Pydantic 데이터 검증**
10. **Rate Limiting 구현**

---

## 📌 요약

**App Reviews Analysis System**은 Google Play Store의 한국 금융 앱 리뷰를 수집하고, Gemini LLM 기반 Multi-Agent 시스템으로 분석하며, OpenSearch KNN과 Redis를 활용한 고성능 검색을 제공하는 종합 리뷰 분석 플랫폼입니다.

**핵심 가치**:
- 🤖 **AI 기반 자동화**: 감성, 카테고리, 민원 분류 자동화
- 🔍 **지능형 검색**: 벡터 임베딩 기반 유사 리뷰 찾기
- 📊 **데이터 인사이트**: 트렌드 분석 및 개선 제안
- ⚡ **고성능**: 파티셔닝, 캐싱, 인덱싱 최적화
- 🛡️ **안정성**: Fallback Chain, Rate Limiting, 고가용성

**기술적 우수성**:
- Clean Architecture (Layers: Views, Services, Agents, Core)
- Type-safe Configuration (Dataclass + Pydantic)
- YAML-driven Configuration
- Comprehensive Error Handling
- Observability & Monitoring
