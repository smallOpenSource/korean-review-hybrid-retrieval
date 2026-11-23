# 코드 품질 개선 세션 준비 완료

**작성일**: 2025-01-01
**상태**: ✅ 완료
**세션 수**: 8개 (Session 5-12)

---

## 개요

코드 품질 감사 보고서(CODE_QUALITY_AUDIT_REPORT.md)를 기반으로 8개의 개선 세션을 계획하고, 각 세션별 상세 실행 프롬프트를 작성했습니다.

---

## 생성된 문서

### 1. 전체 계획서
- **파일**: `docs/CODE_QUALITY_IMPROVEMENT_PLAN.md`
- **내용**: 8개 세션 전체 로드맵, 우선순위, 의존성, 병렬 처리 전략

### 2. 세션별 실행 프롬프트 (8개)

| 세션 | 파일 | 우선순위 | 소요시간 | 의존성 |
|------|------|----------|----------|---------|
| Session 5 | `SESSION_05_PROMPT.md` | 🔴 최고 | 2시간 | 없음 |
| Session 6 | `SESSION_06_PROMPT.md` | 🔴 높음 | 2시간 | 없음 |
| Session 7 | `SESSION_07_PROMPT.md` | 🔴 높음 | 2시간 | 없음 |
| Session 8 | `SESSION_08_PROMPT.md` | 🟡 중간 | 2시간 | Session 5 |
| Session 9 | `SESSION_09_PROMPT.md` | 🟡 중간 | 2시간 | 없음 |
| Session 10 | `SESSION_10_PROMPT.md` | 🟡 중간 | 1.5시간 | 없음 |
| Session 11 | `SESSION_11_PROMPT.md` | 🟡 중간 | 1.5시간 | Session 8 권장 |
| Session 12 | `SESSION_12_PROMPT.md` | 🟢 낮음 | 1시간 | 전체 완료 후 |

**총 예상 소요 시간**: 14시간

---

## 세션별 주요 내용

### 🔴 Session 5: LLM Client JSON 파싱 개선
**목표**: JSON 파싱 안정성 및 디버깅 가능성 향상

**주요 작업**:
- `JSONParsingResult` 데이터클래스 생성
- `_try_parse_json()` 메서드 개선 (에러별 상세 처리)
- 모든 LLM Client에 상세 에러 로깅 추가
- BaseAgent 에러 처리 강화

**수정 파일**: 2개
- `app/agents/llm_client.py`
- `app/agents/base_agent.py`

---

### 🔴 Session 6: 상수/설정값 중앙화 Part 1
**목표**: 하드코딩된 설정값을 환경변수 기반 중앙 관리로 전환

**주요 작업**:
- 4개 설정 데이터클래스 추가 (AgentConfidenceThresholds, OllamaAdvancedConfig, BGETimeoutConfig, FallbackDepartmentConfig)
- BaseAgent 동적 임계값 로딩
- LLM Client Ollama 파라미터 중앙화
- Embedding Service 타임아웃 설정화
- `.env.example` 업데이트

**수정 파일**: 8개
- `app/config/settings.py`
- `app/agents/base_agent.py`
- `app/agents/llm_client.py`
- `app/agents/embedding_service.py`
- `app/services/department_routing_service.py`
- 각 Agent 파일들
- `.env.example`

**제거 하드코딩**: 20개

---

### 🔴 Session 7: API 응답 상태 표준화
**목표**: API 응답 상태를 Enum으로 표준화

**주요 작업**:
- `ResponseStatus` Enum 생성
- `success_response()`, `error_response()` 헬퍼 함수 추가
- 6개 API 파일에서 "ok", "error" 하드코딩 제거

**수정 파일**: 9개
- `app/constants/response_status.py` (생성)
- `app/constants/__init__.py`
- `app/api/v1/auth.py`
- `app/api/v1/reviews.py`
- `app/api/v1/analysis.py`
- `app/api/v1/complaints.py`
- `app/api/v1/dashboard.py`
- `app/api/v1/search.py`

**제거 하드코딩**: 15개

---

### 🟡 Session 8: BaseAgent Pydantic 완전 전환
**목표**: 레거시 fallback 제거, Pydantic 검증 100% 적용

**주요 작업**:
- `QueryResult` 스키마 생성
- `ReasoningModel` 스키마 생성
- BaseAgent 레거시 코드 제거
- QueryAgent Pydantic 적용
- ValidationError 상세 처리

**수정 파일**: 3개
- `app/schemas/llm.py`
- `app/agents/base_agent.py`
- `app/agents/query_agent.py`

**Pydantic 사용률**: 78% → 95%

---

### 🟡 Session 9: 열거형 변수 도입 Part 1 (인증/민원)
**목표**: UserRole, ComplaintStatus를 Enum으로 표준화

**주요 작업**:
- `UserRole` Enum 생성 (admin, analyst, viewer)
- `ComplaintStatus` Enum 생성 (new, in_progress, resolved, closed)
- 권한 매핑 함수 (`has_permission`)
- 상태 전이 규칙 (`can_transition`)

**수정 파일**: 9개
- `app/constants/user_roles.py` (생성)
- `app/constants/complaint_status.py` (생성)
- `app/models/user.py`
- `app/utils/auth.py`
- `app/api/v1/auth.py`
- `app/constants/mappings.py`
- `app/api/models_extended.py`
- `app/api/v1/complaints.py`

**제거 하드코딩**: 15개

---

### 🟡 Session 10: 열거형 변수 도입 Part 2 (카테고리/DB)
**목표**: ReviewCategory, DB 상태 플래그를 Enum으로 표준화

**주요 작업**:
- `ReviewCategory` Enum 생성 (14개 카테고리)
- `ReviewAnalysisStatus`, `ReviewSyncStatus` IntEnum 생성
- CategoryAgent 카테고리 리스트 Enum 전환
- 스케줄러 Jobs에서 매직 넘버(0, 1) 제거

**수정 파일**: 6개
- `app/constants/review_categories.py` (생성)
- `app/constants/db_status.py` (생성)
- `app/agents/category_agent.py`
- `scheduler/jobs/analyze_reviews.py`
- `scheduler/jobs/sync_to_opensearch.py`
- `scheduler/jobs/aggregate_mart.py`

**제거 하드코딩**: 5개

---

### 🟡 Session 11: 서비스 레이어 JSON 파싱 개선
**목표**: 서비스 레이어의 JSON 파싱에 Pydantic 검증 추가

**주요 작업**:
- `WordRankingResult`, `TeamInfo`, `RoutingRule` 스키마 생성
- word_analysis_service.py Redis 캐시 검증
- department_routing_service.py 부서 규칙 검증
- ValidationError 상세 처리

**수정 파일**: 3개
- `app/schemas/service_models.py` (생성)
- `app/services/word_analysis_service.py`
- `app/services/department_routing_service.py`

---

### 🟢 Session 12: 중복 제거 및 최종 정리
**목표**: 중복 정의 제거, 문서 업데이트, 최종 검증

**주요 작업**:
- `SentimentLabel` 중복 제거 (schemas/llm.py만 유지)
- `mappings.py` 정리
- `.env.example` 업데이트
- CODE_QUALITY_AUDIT_REPORT.md 업데이트 (개선 결과 추가)
- README.md 업데이트
- 전체 검증 실행

**수정 파일**: 5개
- `app/schemas/llm.py`
- `app/api/models_extended.py`
- `app/constants/mappings.py`
- `.env.example`
- `README.md`

---

## 병렬 처리 전략

### Week 1 (Day 1-4)
```
Day 1-2: Session 5 (필수 선행)
         └─> JSON 파싱 개선 완료 후

Day 3-4: 병렬 실행
         ├─ Session 6 (담당자 A: 설정 중앙화)
         ├─ Session 7 (담당자 B: API 응답 표준화)
         └─ Session 8 (담당자 C: Pydantic 전환, Session 5 의존)
```

### Week 2 (Day 5-7)
```
Day 5-6: 병렬 실행
         ├─ Session 9 (담당자 A: 인증/민원 Enum)
         ├─ Session 10 (담당자 B: 카테고리/DB Enum)
         └─ Session 11 (담당자 C: 서비스 레이어 검증)

Day 7:   Session 12 (최종 정리)
```

---

## 프롬프트 사용 방법

각 세션 프롬프트는 독립적으로 실행 가능하도록 설계되었습니다:

### 1. 세션 선택
```bash
cat docs/prompts/SESSION_05_PROMPT.md
```

### 2. 단계별 실행
각 프롬프트는 다음 구조로 되어 있습니다:
- **작업 지시**: 현재 문제점과 목표
- **작업 단계**: Step 1, 2, 3... 순차적 실행 가이드
- **검증 방법**: 구문 검사, Import 테스트, 통합 테스트
- **완료 체크리스트**: 모든 작업 항목 확인

### 3. 검증
각 세션 완료 후 체크리스트를 확인하고 검증 스크립트를 실행합니다.

---

## 예상 개선 효과

### 정량적 개선
- ✅ Pydantic 사용률: 78% → 95%
- ✅ 하드코딩 제거: 약 60개
- ✅ 추가 Enum: 7개
- ✅ 추가 Pydantic 스키마: 12개

### 정성적 개선
- ✅ 타입 안전성 향상
- ✅ 디버깅 용이성 증가
- ✅ 설정 관리 중앙화
- ✅ 코드 일관성 확보
- ✅ 문서 최신화

---

## 다음 단계

1. **Session 5부터 순차 실행**: 가장 높은 우선순위부터 시작
2. **병렬 처리**: Session 6, 7, 9, 10은 동시 진행 가능
3. **최종 정리**: Session 12로 마무리

---

## 참고 문서

- `docs/CODE_QUALITY_AUDIT_REPORT.md` - 감사 결과 (107KB, 91개 이슈)
- `docs/CODE_QUALITY_IMPROVEMENT_PLAN.md` - 전체 개선 계획
- `docs/prompts/SESSION_XX_PROMPT.md` - 세션별 실행 프롬프트

---

## 작성자 노트

모든 프롬프트는 다음 원칙으로 작성되었습니다:

1. **명확한 작업 지시**: 무엇을, 왜, 어떻게 하는지 명시
2. **단계별 가이드**: Step-by-step으로 따라할 수 있도록 구성
3. **Before/After 예시**: 코드 변경 전후 비교
4. **검증 스크립트**: 즉시 실행 가능한 검증 코드 제공
5. **체크리스트**: 완료 여부를 명확히 확인
6. **롤백 방법**: 문제 발생 시 복구 방법 제시

---

**준비 완료!** 이제 Session 5부터 차례대로 실행하면 됩니다. 🚀
