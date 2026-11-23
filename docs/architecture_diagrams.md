# 시스템 아키텍처 다이어그램

이 문서는 App Reviews Analysis System의 전체 구조를 시각화한 ASCII 다이어그램을 제공합니다.

## 목차
1. [전체 시스템 아키텍처](#1-전체-시스템-아키텍처)
2. [데이터 파이프라인 (3단계)](#2-데이터-파이프라인-3단계)
3. [Multi-Agent 시스템 구조](#3-multi-agent-시스템-구조)
4. [검색 아키텍처 (OpenSearch)](#4-검색-아키텍처-opensearch)
5. [디렉토리 구조](#5-디렉토리-구조)
6. [요청 흐름 (End-to-End)](#6-요청-흐름-end-to-end)

---

## 1. 전체 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        App Reviews Analysis System                           │
│                     (Google Play Store 리뷰 분석 플랫폼)                      │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────┐
                    │   Google Play Store API      │
                    └──────────┬───────────────────┘
                               │
                               │ 리뷰 수집
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          SCHEDULER (독립 프로세스)                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │
│  │  COLLECT    │───▶│   ANALYZE   │───▶│    SYNC     │                   │
│  │ (수집 Job)  │    │  (분석 Job) │    │ (동기화 Job)│                   │
│  └─────────────┘    └─────────────┘    └─────────────┘                   │
│       │                    │                    │                          │
│       │ INSERT             │ UPDATE             │ INDEX + EMBED            │
│       ▼                    ▼                    ▼                          │
│  ┌──────────────────────────────────────────────────────┐                 │
│  │              MySQL (Source of Truth)                  │                 │
│  │  analyzed=0 ──▶ analyzed=1 ──▶ synced_to_opensearch=1│                 │
│  └──────────────────────────────────────────────────────┘                 │
└────────────────────────────────────────────────────────────────────────────┘
                               │
                               │ Sync Job만 Write
                               ▼
                    ┌──────────────────────────────┐
                    │      OpenSearch Index        │
                    │  (KNN Vector + BM25 Search)  │
                    │  - Nori Analyzer (Korean)    │
                    │  - 1024-dim Embeddings       │
                    └──────────┬───────────────────┘
                               │
                               │ Read Only
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      FLASK APPLICATION (Web/API)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │Dashboard │  │ Search   │  │ Analysis │  │Complaints│                  │
│  │  Views   │  │   API    │  │   API    │  │   API    │                  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │              Redis Sentinel (캐싱 레이어)                   │          │
│  └─────────────────────────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────────┘
```

### 주요 특징
- **Scheduler**: 독립 프로세스로 실행 (`python -m scheduler.main`)
- **MySQL**: 모든 원본 데이터와 분석 결과의 Source of Truth
- **OpenSearch**: 검색 전용 인덱스 (Sync Job만 Write 가능)
- **Flask App**: OpenSearch에서만 Read (MySQL 직접 쿼리 X)

---

## 2. 데이터 파이프라인 (3단계)

### STAGE 1: COLLECT (수집)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  STAGE 1: COLLECT (수집)                                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

    Google Play Store
           │
           │ fetch reviews
           ▼
    ┌─────────────────┐
    │ collect_reviews │
    │      .py        │
    └────────┬────────┘
             │
             │ INSERT INTO reviews
             │   analyzed = 0
             │   synced_to_opensearch = 0
             │   embedding = NULL
             ▼
    ┌─────────────────┐
    │   MySQL (Raw)   │
    └─────────────────┘
```

**주요 동작:**
- Google Play Store API에서 리뷰 수집
- MySQL에 원본 저장 (분석 전 상태)
- 임베딩은 이 단계에서 생성하지 않음

---

### STAGE 2: ANALYZE (분석)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  STAGE 2: ANALYZE (분석)                                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

    ┌─────────────────┐
    │MySQL (analyzed=0)│
    └────────┬────────┘
             │ SELECT WHERE analyzed=0
             ▼
    ┌─────────────────┐
    │ analyze_reviews │
    │      .py        │
    └────────┬────────┘
             │
             │ ┌──────────────────────────────────────┐
             ├─▶│ Multi-Agent Analysis (LLM 호출)     │
             │ ├──────────────────────────────────────┤
             │ │ • SentimentAgent  (감성 분석)        │
             │ │ • CategoryAgent   (카테고리 분류)    │
             │ │ • ComplaintAgent  (민원 분류)        │
             │ └──────────────────────────────────────┘
             │
             │ UPDATE reviews SET
             │   analyzed = 1
             │   sentiment_label = '...'
             │   is_complaint = 1
             │   category_primary = '...'
             ▼
    ┌─────────────────┐
    │MySQL (analyzed=1)│
    └─────────────────┘
```

**주요 동작:**
- MySQL에서 미분석 리뷰 조회 (`analyzed=0`)
- LLM Multi-Agent로 분석 (Sentiment, Category, Complaint)
- 분석 결과를 MySQL에 업데이트
- OpenSearch는 업데이트하지 않음 (다음 단계에서 처리)

---

### STAGE 3: SYNC (동기화 + 임베딩)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  STAGE 3: SYNC (동기화 + 임베딩)                                           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

    ┌─────────────────────────┐
    │MySQL (analyzed=1,       │
    │       synced=0)         │
    └────────┬────────────────┘
             │ SELECT WHERE analyzed=1 AND synced_to_opensearch=0
             ▼
    ┌─────────────────────────┐
    │  sync_to_opensearch.py  │
    └────────┬────────────────┘
             │
             ├─▶ EmbeddingService.generate()
             │   └─▶ BGE-M3-KO (1024-dim vector)
             │
             │ Bulk Index to OpenSearch
             │   - 리뷰 원문
             │   - 분석 결과 (sentiment, category, complaint)
             │   - 임베딩 벡터 (content_embedding)
             ▼
    ┌─────────────────────────┐
    │  OpenSearch (indexed)   │
    └─────────────────────────┘
             │
             │ UPDATE MySQL SET
             │   synced_to_opensearch = 1
             ▼
    ┌─────────────────────────┐
    │   MySQL (synced=1)      │
    └─────────────────────────┘
```

**주요 동작:**
- 분석 완료되었으나 미동기화된 리뷰 조회
- **이 단계에서 임베딩 생성** (BGE-M3-KO, 1024차원)
- OpenSearch에 벡터와 함께 인덱싱
- MySQL 동기화 상태 업데이트

**중요:** 임베딩은 SYNC 단계에서만 생성됩니다!

---

### STAGE 4: APPLICATION (활용)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  STAGE 4: APPLICATION (활용)                                               ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

    ┌─────────────────────────┐
    │   OpenSearch (indexed)  │
    └────────┬────────────────┘
             │
             │ Query (Read Only)
             ▼
    ┌─────────────────────────┐
    │   Flask Application     │
    │  • Dashboard            │
    │  • Search (BM25 + KNN)  │
    │  • Analytics            │
    │  • Complaint Management │
    └─────────────────────────┘
```

**주요 동작:**
- Flask App은 OpenSearch에서만 데이터 조회
- MySQL은 직접 쿼리하지 않음 (파이프라인 무결성 유지)

---

## 3. Multi-Agent 시스템 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Multi-Agent System                               │
└─────────────────────────────────────────────────────────────────────────┘

                            ┌─────────────────┐
                            │   BaseAgent     │ ◀─── 추상 기본 클래스
                            │  (base_agent)   │
                            └────────┬────────┘
                                     │
                   ┌─────────────────┼─────────────────┬──────────────┐
                   │                 │                 │              │
                   ▼                 ▼                 ▼              ▼
        ┌──────────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │ SentimentAgent   │ │CategoryAgent│ │ComplaintAgent│ │InsightAgent │
        │                  │ │             │ │             │ │             │
        │ 5-level sentiment│ │Product      │ │Department   │ │Strategic    │
        │ very_negative    │ │category     │ │routing      │ │insights     │
        │   ⋮              │ │classification│ │+ SLA mgmt   │ │generation   │
        │ very_positive    │ │             │ │             │ │             │
        └────────┬─────────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
                 │                  │                │                │
                 └──────────────────┴────────────────┴────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │     LLMClient         │
                        │  (llm_client.py)      │
                        │                       │
                        │ • Provider Fallback   │
                        │ • Rate Limiting       │
                        │ • Token Counting      │
                        │ • Retry Logic         │
                        └───────────┬───────────┘
                                    │
            ┌───────────────────────┼───────────────────────┬────────────────┐
            │                       │                       │                │
            ▼                       ▼                       ▼                ▼
    ┌───────────┐          ┌───────────┐          ┌───────────┐    ┌──────────┐
    │  Gemini   │ (Primary)│  Ollama   │(Fallback1)│   Groq    │(F2)│  OpenAI  │(F3)
    │           │          │           │          │           │    │          │
    │ 2.0 Flash │          │ Qwen/Llama│          │Llama-3.3  │    │GPT-4o-mini│
    │ 1.5 Pro   │          │   Local   │          │  -70B     │    │          │
    │           │          │           │          │           │    │          │
    │ 15 RPM    │  ──X──▶  │ Unlimited │  ──X──▶  │ 30 RPM    │──X▶│ 500 RPM  │
    │Rate Limit │          │           │          │           │    │          │
    └───────────┘          └───────────┘          └───────────┘    └──────────┘
```

### BaseAgent가 제공하는 공통 기능

```
┌─────────────────────────────────────────────────────────────────┐
│ • Prompt Template Management (prompts.yaml에서 로드)            │
│ • JSON Response Parsing & Validation                            │
│ • Confidence Scoring (0-100)                                    │
│ • Reasoning Extraction (steps, evidence, alternatives)          │
│ • Batch Processing (asyncio)                                    │
│ • Quality Flagging (needs_review flag)                          │
└─────────────────────────────────────────────────────────────────┘
```

### LLM Fallback 체인

1. **Gemini** (Primary) - 15 RPM, 무료/유료 티어
2. **Ollama** (Fallback 1) - 로컬 모델, 무제한
3. **Groq** (Fallback 2) - 30 RPM
4. **OpenAI** (Fallback 3) - 500 RPM

각 Provider 실패 시 자동으로 다음 Provider로 전환됩니다.

---

## 4. 검색 아키텍처 (OpenSearch)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      OpenSearch Search Architecture                      │
└─────────────────────────────────────────────────────────────────────────┘

사용자 쿼리: "배송이 너무 느려요"
      │
      ▼
┌──────────────────────────────────────┐
│   ReviewService.search_reviews()     │
└──────────┬───────────────────────────┘
           │
           ├─────────────────┬─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌───────────┐    ┌───────────┐    ┌───────────┐
    │   BM25    │    │    KNN    │    │  Hybrid   │
    │ Full-Text │    │  Vector   │    │ (BM25+KNN)│
    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
          │                │                │
          │                │ Embedding      │
          │                │ Generation     │
          │                │ (BGE-M3-KO)    │
          │                │                │
          └────────────────┴────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │  OpenSearch Query Engine   │
              │                            │
              │  Index: app_reviews        │
              │  ┌──────────────────────┐  │
              │  │ Nori Analyzer        │  │ ◀─── 한국어 형태소 분석
              │  │ (Korean Morphology)  │  │
              │  └──────────────────────┘  │
              │                            │
              │  ┌──────────────────────┐  │
              │  │ KNN Vector Search    │  │ ◀─── 1024-dim 임베딩
              │  │ (content_embedding)  │  │
              │  └──────────────────────┘  │
              └────────────┬───────────────┘
                           │
                           │ Top 100 Results
                           ▼
              ┌────────────────────────────┐
              │   RerankService            │
              │   (BGE-Reranker-v2-M3)     │
              └────────────┬───────────────┘
                           │
                           │ Top 10 Reranked
                           ▼
              ┌────────────────────────────┐
              │   Final Results            │
              │   (정확도 향상)             │
              └────────────────────────────┘
```

### OpenSearch 인덱스 구조

```
┌──────────────────────────────────────────────────────────────┐
│ app_reviews 인덱스                                            │
├──────────────────────────────────────────────────────────────┤
│ review_id (keyword)                                          │
│ content (text + Nori)        ◀─── BM25 검색용               │
│ content_embedding (vector)   ◀─── KNN 검색용 (1024-dim)     │
│                                                              │
│ sentiment {                                                  │
│   label (keyword)            ◀─── 필터링용                  │
│   score (float)                                              │
│   confidence (float)                                         │
│   emotions (object)                                          │
│ }                                                            │
│                                                              │
│ complaint {                                                  │
│   is_complaint (boolean)     ◀─── 필터링용                  │
│   type (keyword)                                             │
│   urgency (keyword)                                          │
│   department (keyword)       ◀─── 부서별 집계용             │
│   sla_deadline (date)                                        │
│ }                                                            │
│                                                              │
│ category {                                                   │
│   primary (keyword)          ◀─── 카테고리별 집계용         │
│   secondary (keyword)                                        │
│   confidence (float)                                         │
│ }                                                            │
└──────────────────────────────────────────────────────────────┘
```

### 검색 방식

1. **BM25 (Full-Text)**: Nori 분석기로 한국어 형태소 분석 → 키워드 매칭
2. **KNN (Vector)**: 쿼리를 임베딩으로 변환 → 코사인 유사도 검색
3. **Hybrid**: BM25와 KNN 결과를 결합 → Reranker로 최종 정렬

---

## 5. 디렉토리 구조

```
appReviews/
│
├── app/                                  ◀─── Flask 애플리케이션
│   ├── __init__.py                       ◀─── Flask factory (create_app)
│   │
│   ├── agents/                           ◀─── Multi-Agent System
│   │   ├── base_agent.py                 ◀─── 추상 기본 클래스
│   │   ├── sentiment_agent.py            ◀─── 감성 분석 (5-level)
│   │   ├── category_agent.py             ◀─── 카테고리 분류
│   │   ├── complaint_agent.py            ◀─── 민원 탐지 + 라우팅
│   │   ├── insight_agent.py              ◀─── 전략적 인사이트
│   │   ├── unified_agent.py              ◀─── 통합 분석 (3-in-1)
│   │   ├── llm_client.py                 ◀─── LLM 통합 클라이언트 (Fallback)
│   │   ├── embedding_service.py          ◀─── 벡터 임베딩 생성
│   │   ├── rerank_service.py             ◀─── 검색 결과 재정렬
│   │   └── query_agent.py                ◀─── 쿼리 분석
│   │
│   ├── api/                              ◀─── REST API
│   │   ├── models.py                     ◀─── Pydantic 스키마
│   │   └── v1/
│   │       ├── __init__.py               ◀─── Blueprint 등록
│   │       ├── reviews.py                ◀─── 리뷰 CRUD
│   │       ├── analysis.py               ◀─── 분석 API
│   │       ├── complaints.py             ◀─── 민원 관리
│   │       ├── search.py                 ◀─── 검색 API
│   │       └── dashboard.py              ◀─── 대시보드 데이터
│   │
│   ├── config/                           ◀─── 설정
│   │   ├── settings.py                   ◀─── 환경변수 로드 (Dataclass)
│   │   ├── llm_config.py                 ◀─── LLM 모델 설정
│   │   ├── llm_models.yaml               ◀─── 모델 스펙 (RPM, 비용)
│   │   ├── prompts.yaml                  ◀─── Agent 프롬프트 템플릿
│   │   ├── prompts.py                    ◀─── 프롬프트 로더
│   │   └── department_hierarchy.yaml     ◀─── 부서 계층 구조
│   │
│   ├── core/                             ◀─── 핵심 인프라
│   │   ├── opensearch_client.py          ◀─── OpenSearch 래퍼 (KNN+BM25)
│   │   ├── mysql_client.py               ◀─── MySQL 연결 풀링
│   │   ├── redis_client.py               ◀─── Redis Sentinel 클라이언트
│   │   ├── rate_limiter.py               ◀─── Token Bucket 알고리즘
│   │   └── api_key_rotator.py            ◀─── API Key 로테이션
│   │
│   ├── services/                         ◀─── 비즈니스 로직
│   │   ├── review_service.py             ◀─── 리뷰 검색/집계
│   │   ├── category_service.py           ◀─── 카테고리 통계
│   │   ├── dedup_service.py              ◀─── 중복 제거 (Hash)
│   │   ├── word_analysis_service.py      ◀─── 키워드 빈도 분석
│   │   ├── similar_review_service.py     ◀─── KNN 유사도 검색
│   │   ├── department_routing_service.py ◀─── 민원 부서 배정
│   │   └── settings_service.py           ◀─── 설정 관리
│   │
│   ├── views/                            ◀─── HTML 페이지 라우트
│   │   ├── __init__.py
│   │   ├── dashboard.py                  ◀─── 메인 대시보드
│   │   ├── company.py                    ◀─── 회사별 분석
│   │   ├── complaints.py                 ◀─── 민원 UI
│   │   └── settings.py                   ◀─── 설정 페이지
│   │
│   ├── templates/                        ◀─── Jinja2 템플릿
│   ├── static/                           ◀─── CSS, JS, Images
│   └── schemas/
│       └── llm.py                        ◀─── LLM 응답 스키마
│
├── scheduler/                            ◀─── 스케줄러 (독립 프로세스)
│   ├── main.py                           ◀─── APScheduler 진입점
│   │
│   ├── config/
│   │   ├── scheduler_config.yaml         ◀─── Job 스케줄 (High/Med/Low)
│   │   └── apps_config.yaml              ◀─── 모니터링 앱 목록
│   │
│   ├── collectors/
│   │   └── play_store_collector.py       ◀─── Google Play API 수집
│   │
│   ├── jobs/                             ◀─── 스케줄 Job들
│   │   ├── collect_reviews.py            ◀─── [STAGE 1] 수집
│   │   ├── analyze_reviews.py            ◀─── [STAGE 2] LLM 분석
│   │   ├── sync_to_opensearch.py         ◀─── [STAGE 3] 동기화 + 임베딩
│   │   ├── generate_wordcloud.py         ◀─── 워드클라우드 생성
│   │   └── aggregate_mart.py             ◀─── OLAP 집계
│   │
│   └── utils/
│       ├── config_loader.py              ◀─── YAML 파서
│       ├── database.py                   ◀─── DB 세션 팩토리
│       ├── priority.py                   ◀─── Priority Enum
│       └── job_tracker.py                ◀─── Job 상태 추적
│
├── docs/                                 ◀─── 문서
│   ├── data_pipeline.md                  ◀─── 파이프라인 상세 설명
│   ├── architecture_diagrams.md          ◀─── 이 문서!
│   └── ...
│
├── migrations/                           ◀─── DB 마이그레이션
├── tests/                                ◀─── 테스트
│   └── pytest.ini
│
├── .env.example                         ◀─── 환경변수 템플릿
├── requirements.txt                      ◀─── Python 의존성
├── run.sh                                ◀─── Flask 실행 스크립트
├── run_asgi.py                           ◀─── ASGI 진입점
├── CLAUDE.md                             ◀─── Claude Code 가이드
└── README.md
```

### 핵심 파일 역할

| 파일 | 역할 |
|------|------|
| `app/__init__.py` | Flask 애플리케이션 팩토리, Blueprint 등록 |
| `scheduler/main.py` | APScheduler 설정 및 Job 등록 |
| `app/agents/base_agent.py` | Multi-Agent 프레임워크 기반 클래스 |
| `app/agents/llm_client.py` | LLM Provider 통합 + Fallback 로직 |
| `app/core/opensearch_client.py` | KNN + BM25 검색 래퍼 |
| `app/services/review_service.py` | 리뷰 검색/집계 핵심 로직 |
| `scheduler/jobs/sync_to_opensearch.py` | 임베딩 생성 + 인덱싱 |

---

## 6. 요청 흐름 (End-to-End)

### 예시: 부정적 리뷰 조회 API

```
사용자: "최근 부정적인 리뷰를 보고 싶어요"

    │
    │ HTTP GET /api/v1/reviews?sentiment=negative&days=7
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask App (app/__init__.py)                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Blueprint: /api/v1                                   │  │
│  │  Route Handler: reviews.py                            │  │
│  └───────────────┬───────────────────────────────────────┘  │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   │ 1. Request Validation (Pydantic)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ReviewService (app/services/review_service.py)             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  search_reviews(filters={sentiment:'negative'})       │  │
│  └───────────────┬───────────────────────────────────────┘  │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   │ 2. Cache Check
                   ▼
          ┌─────────────────┐
          │ Redis Sentinel  │
          │ (Cache Layer)   │
          └────────┬────────┘
                   │ Cache Miss
                   │
                   │ 3. Query OpenSearch
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  OpenSearchClient (app/core/opensearch_client.py)           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  query = {                                            │  │
│  │    "bool": {                                          │  │
│  │      "filter": [                                      │  │
│  │        {"term": {"sentiment.label": "negative"}},    │  │
│  │        {"range": {"at": {"gte": "now-7d"}}}          │  │
│  │      ]                                                │  │
│  │    }                                                  │  │
│  │  }                                                    │  │
│  └───────────────┬───────────────────────────────────────┘  │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   │ 4. Execute Search
                   ▼
          ┌─────────────────┐
          │   OpenSearch    │
          │   app_reviews   │
          │   Index         │
          └────────┬────────┘
                   │
                   │ 5. Return Results
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Response Processing                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  • Parse hits                                         │  │
│  │  • Format response (Pydantic models)                  │  │
│  │  • Cache results (Redis)                              │  │
│  │  • Return JSON                                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                   │
                   │ 6. HTTP Response
                   ▼
                 User
    {
      "reviews": [
        {
          "review_id": "...",
          "content": "앱이 자주 멈춰요",
          "sentiment": {
            "label": "negative",
            "score": -0.8,
            "confidence": 92
          }
        }
      ],
      "total": 1247,
      "page": 1
    }
```

### 요청 처리 단계

1. **Request Validation**: Pydantic으로 입력 검증
2. **Cache Check**: Redis에서 캐시 확인
3. **Query OpenSearch**: 검색 쿼리 생성 및 실행
4. **Execute Search**: OpenSearch에서 결과 조회
5. **Response Processing**: 결과 포맷팅 및 캐싱
6. **HTTP Response**: JSON 응답 반환

---

## 주요 아키텍처 원칙

### 1. 데이터 흐름의 단방향성
- **MySQL → OpenSearch**: Sync Job만 Write
- **OpenSearch → Flask App**: Read Only
- 순환 참조 없음 (무결성 보장)

### 2. 책임의 분리
- **Scheduler**: 데이터 수집, 분석, 동기화
- **Flask App**: API 서빙, 검색, 시각화
- 독립적으로 스케일 가능

### 3. LLM Resilience
- 4-Tier Fallback Chain (Gemini → Ollama → Groq → OpenAI)
- Rate Limiting + API Key Rotation
- 자동 복구 메커니즘

### 4. 검색 최적화
- Hybrid Search (BM25 + KNN)
- Reranking으로 정확도 향상
- Redis 캐싱으로 응답 속도 개선

### 5. 한국어 처리
- Nori Analyzer (형태소 분석)
- BGE-M3-KO (한국어 최적화 임베딩)
- Korean-aware tokenization

---

## 참고 문서

- [데이터 파이프라인 상세](./data_pipeline.md)
- [CLAUDE.md](../CLAUDE.md) - 개발 가이드
- [README.md](../README.md) - 프로젝트 개요
