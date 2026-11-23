# 코드 품질 개선 작업 계획

**작성일**: 2026-01-01
**기반 문서**: `docs/CODE_QUALITY_AUDIT_REPORT.md`
**총 세션 수**: 8개
**예상 총 소요 시간**: 2주

---

## 개요

코드 품질 전수 조사에서 발견된 91개 이슈를 8개 세션으로 나누어 개선합니다.

### 세션 분할 원칙
1. **독립성**: 각 세션은 다른 세션과 독립적으로 실행 가능
2. **우선순위**: Critical 이슈를 우선 처리
3. **병렬성**: 의존성 없는 세션은 병렬 처리 가능
4. **균형**: 각 세션당 1-2시간 소요

### 병렬 처리 가능 그룹
- **그룹 A** (우선 실행): Session 5
- **그룹 B** (병렬 가능): Session 6, Session 7
- **그룹 C** (Session 5, 8 완료 후): Session 8
- **그룹 D** (병렬 가능): Session 9, Session 10
- **그룹 E** (Session 8 완료 후): Session 11
- **그룹 F** (모든 세션 완료 후): Session 12

---

## 세션별 작업 계획

### Session 5: LLM Client JSON 파싱 개선 ⭐⭐⭐ (Critical)

**우선순위**: 🔴 최고
**예상 소요 시간**: 2시간
**의존성**: 없음 (독립 실행 가능)
**영향 범위**: 모든 LLM 호출

#### 목표
LLM 응답 파싱의 안정성과 디버깅 가능성을 대폭 향상

#### 작업 범위
1. `JSONParsingResult` 데이터클래스 생성
2. `llm_client.py:_try_parse_json()` 메서드 개선
3. `LLMResponse` 스키마 업데이트
4. 에러 로깅 강화
5. 단위 테스트 추가

#### 수정 파일
- `app/agents/llm_client.py` (핵심)
- 테스트 파일 생성 (선택)

#### 주요 변경사항
- `_try_parse_json()`: `Optional[Dict]` → `JSONParsingResult` 반환
- 모든 예외 타입별 처리 (JSONDecodeError, ValueError 등)
- 상세 로깅 추가

#### 검증 방법
- [ ] 정상 JSON 파싱 성공
- [ ] 잘못된 JSON → 상세 에러 정보 반환
- [ ] 로그에 파싱 실패 원인 기록
- [ ] 기존 Agent 코드 영향 없음

#### 완료 기준
- JSONParsingResult 도입 완료
- 모든 파싱 실패 케이스에 대한 로깅 추가
- 기존 기능 정상 작동 확인

---

### Session 6: 상수/설정값 중앙화 Part 1 ⭐⭐⭐

**우선순위**: 🔴 높음
**예상 소요 시간**: 2시간
**의존성**: 없음 (병렬 처리 가능)
**영향 범위**: Agent, LLM 설정

#### 목표
하드코딩된 설정값들을 `app/config/settings.py`로 중앙화

#### 작업 범위
1. Agent 신뢰도 임계값 설정 추가
2. Ollama 고급 파라미터 설정 추가
3. Fallback 부서 정보 설정 추가
4. BGE 타임아웃 설정 추가
5. LLM Fallback Order 기본값 설정 추가
6. 각 Agent 파일에서 설정값 읽기로 변경

#### 수정 파일
- `app/config/settings.py` (핵심)
- `app/agents/base_agent.py`
- `app/agents/sentiment_agent.py`
- `app/agents/category_agent.py`
- `app/agents/complaint_agent.py`
- `app/agents/insight_agent.py`
- `app/agents/unified_agent.py`
- `app/agents/llm_client.py`
- `app/agents/embedding_service.py`
- `app/services/department_routing_service.py`

#### 주요 변경사항
```python
# settings.py에 추가
agent_confidence_thresholds: Dict[str, float]
ollama_advanced: OllamaAdvancedConfig
fallback_department: Dict[str, str]
bge_timeouts: BGETimeoutConfig
default_llm_fallback_order: List[str]
```

#### 검증 방법
- [ ] 모든 Agent가 settings에서 임계값 읽기
- [ ] 환경변수 우선순위 작동
- [ ] 기본값 정상 작동
- [ ] 설정 변경 시 동작 확인

#### 완료 기준
- 하드코딩된 설정값 20개 이상 제거
- settings.py 중앙 관리 확립
- .env.example 업데이트

---

### Session 7: API 응답 상태 표준화 ⭐⭐

**우선순위**: 🔴 높음
**예상 소요 시간**: 2시간
**의존성**: 없음 (병렬 처리 가능)
**영향 범위**: 모든 API 엔드포인트

#### 목표
API 응답 상태를 Enum으로 표준화하여 일관성 확보

#### 작업 범위
1. `app/constants/response_status.py` 생성
2. `ResponseStatus` Enum 정의
3. 모든 API 엔드포인트에서 Enum 사용
4. 에러 응답 헬퍼 함수 생성 (선택)

#### 수정 파일
- `app/constants/__init__.py` (생성)
- `app/constants/response_status.py` (생성)
- `app/api/v1/auth.py`
- `app/api/v1/reviews.py`
- `app/api/v1/analysis.py`
- `app/api/v1/complaints.py`
- `app/api/v1/dashboard.py`
- `app/api/v1/search.py`

#### 주요 변경사항
```python
# Before
return jsonify({'status': 'ok', 'data': data})

# After
from app.constants.response_status import ResponseStatus
return jsonify({'status': ResponseStatus.OK.value, 'data': data})
```

#### 검증 방법
- [ ] 모든 API 응답이 Enum 사용
- [ ] 하드코딩된 "ok", "error" 제거 확인
- [ ] API 테스트 통과
- [ ] 응답 포맷 일관성 확인

#### 완료 기준
- ResponseStatus Enum 생성
- 10+ API 엔드포인트 적용
- 하드코딩된 상태값 15개 제거

---

### Session 8: BaseAgent Pydantic 완전 전환 ⭐⭐⭐

**우선순위**: 🔴 높음
**예상 소요 시간**: 1.5시간
**의존성**: Session 5 완료 후
**영향 범위**: 모든 Agent

#### 목표
레거시 fallback 코드 제거, Pydantic 완전 전환

#### 작업 범위
1. `base_agent.py`에서 레거시 `Reasoning.from_dict()` 제거
2. Pydantic `ValidationError` 처리 강화
3. 에러 메시지 개선
4. `query_agent.py` Pydantic 전환

#### 수정 파일
- `app/agents/base_agent.py` (핵심)
- `app/agents/query_agent.py` (추가)
- `app/schemas/llm.py` (QueryResult 추가)

#### 주요 변경사항
```python
# Before
try:
    reasoning = ReasoningModel.model_validate(reasoning_data)
except Exception:
    reasoning = Reasoning.from_dict(reasoning_data)  # 레거시

# After
try:
    reasoning = ReasoningModel.model_validate(reasoning_data)
except ValidationError as e:
    logger.error(f"Reasoning validation failed: {e}")
    raise ValueError(f"Invalid reasoning: {e.error_count()} errors")
```

#### 검증 방법
- [ ] 레거시 코드 완전 제거 확인
- [ ] Pydantic 검증 오류 시 명확한 에러 메시지
- [ ] QueryAgent QueryResult 사용 확인
- [ ] 모든 Agent 테스트 통과

#### 완료 기준
- 레거시 fallback 제거
- Pydantic 사용률 95% 달성
- QueryResult 스키마 추가

---

### Session 9: 열거형 변수 도입 Part 1 (인증/민원) ⭐⭐

**우선순위**: 🟡 중간
**예상 소요 시간**: 2시간
**의존성**: 없음 (병렬 처리 가능)
**영향 범위**: 인증, 민원 관리

#### 목표
사용자 역할과 민원 상태를 Enum으로 관리

#### 작업 범위
1. `app/constants/user_roles.py` 생성
2. `app/constants/complaint_status.py` 생성
3. 사용자 역할 Enum 적용
4. 민원 상태 Enum 통일
5. mappings.py와 models_extended.py 정리

#### 수정 파일
- `app/constants/user_roles.py` (생성)
- `app/constants/complaint_status.py` (생성)
- `app/models/user.py`
- `app/utils/auth.py`
- `app/api/v1/auth.py`
- `app/api/models_extended.py`
- `app/constants/mappings.py` (정리)
- `app/api/v1/complaints.py`
- `app/views/complaints.py`

#### 주요 변경사항
```python
# user_roles.py
class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

# complaint_status.py
class ComplaintStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
```

#### 검증 방법
- [ ] 역할 문자열 하드코딩 10개 제거
- [ ] 민원 상태 일관성 확보
- [ ] 인증 테스트 통과
- [ ] 민원 관리 테스트 통과

#### 완료 기준
- UserRole Enum 생성 및 적용
- ComplaintStatus 통일
- 하드코딩 15개 제거

---

### Session 10: 열거형 변수 도입 Part 2 (카테고리/DB) ⭐⭐

**우선순위**: 🟡 중간
**예상 소요 시간**: 1.5시간
**의존성**: 없음 (병렬 처리 가능)
**영향 범위**: 카테고리 분류, 스케줄러

#### 목표
리뷰 카테고리와 DB 상태 플래그를 Enum으로 관리

#### 작업 범위
1. `app/constants/review_categories.py` 생성
2. `app/constants/db_status.py` 생성
3. CategoryAgent 카테고리 Enum 적용
4. 스케줄러 DB 상태 Enum 적용

#### 수정 파일
- `app/constants/review_categories.py` (생성)
- `app/constants/db_status.py` (생성)
- `app/agents/category_agent.py`
- `scheduler/jobs/analyze_reviews.py`
- `scheduler/jobs/sync_to_opensearch.py`

#### 주요 변경사항
```python
# review_categories.py
class ReviewCategory(str, Enum):
    LOGIN = "login"
    TRANSFER = "transfer"
    PAYMENT = "payment"
    # ... 14개 전체

# db_status.py
class ReviewAnalysisStatus(IntEnum):
    PENDING = 0
    COMPLETED = 1

class ReviewSyncStatus(IntEnum):
    NOT_SYNCED = 0
    SYNCED = 1
```

#### 검증 방법
- [ ] 카테고리 리스트 하드코딩 제거
- [ ] DB 상태 플래그 Enum 사용
- [ ] 카테고리 검증 정상 작동
- [ ] 스케줄러 작업 정상 작동

#### 완료 기준
- ReviewCategory Enum 생성
- DB 상태 Enum 생성
- 하드코딩 5개 제거

---

### Session 11: 서비스 레이어 JSON 파싱 개선 ⭐

**우선순위**: 🟡 중간
**예상 소요 시간**: 1.5시간
**의존성**: Session 8 완료 후 권장
**영향 범위**: 서비스 레이어

#### 목표
서비스 레이어의 JSON 파싱에 Pydantic 검증 추가

#### 작업 범위
1. `word_analysis_service.py` 캐시 검증 강화
2. `department_routing_service.py` 규칙 검증 추가
3. Pydantic 스키마 추가 (필요시)

#### 수정 파일
- `app/services/word_analysis_service.py`
- `app/services/department_routing_service.py`
- `app/schemas/service_models.py` (생성, 선택)

#### 주요 변경사항
```python
# Before
data = self._redis.master.get(cache_key)
parsed = json.loads(data)
return WordRankingResult(...)

# After
data = self._redis.master.get(cache_key)
if isinstance(data, bytes):
    data = data.decode('utf-8')
parsed = json.loads(data)
result = WordRankingResult(**parsed)  # Pydantic 검증
return result
```

#### 검증 방법
- [ ] 캐시 파싱 실패 시 명확한 에러
- [ ] 부서 규칙 검증 작동
- [ ] 서비스 레이어 테스트 통과

#### 완료 기준
- JSON 파싱 검증 강화
- 에러 처리 개선

---

### Session 12: 중복 제거 및 최종 정리 ⭐

**우선순위**: 🟢 낮음
**예상 소요 시간**: 1시간
**의존성**: 모든 세션 완료 후
**영향 범위**: 전체 정리

#### 목표
중복 정의 제거 및 문서 업데이트

#### 작업 범위
1. `SentimentLabel` 중복 정의 제거
2. `mappings.py` 불필요한 내용 정리
3. `.env.example` 업데이트
4. 문서 업데이트
5. 최종 검증

#### 수정 파일
- `app/schemas/llm.py`
- `app/api/models_extended.py`
- `app/constants/mappings.py`
- `.env.example`
- `docs/CODE_QUALITY_AUDIT_REPORT.md` (업데이트)
- `README.md` (업데이트)

#### 주요 변경사항
- SentimentLabel은 schemas/llm.py에만 유지
- models_extended.py에서는 import
- mappings.py에서 Enum으로 이관된 항목 제거

#### 검증 방법
- [ ] 중복 정의 완전 제거
- [ ] Import 경로 일관성
- [ ] 전체 테스트 통과
- [ ] 문서 최신화

#### 완료 기준
- 중복 제거 완료
- 문서 업데이트 완료
- 최종 검증 완료

---

## 세션별 우선순위 및 순서

### 실행 순서 권장

```
Phase 1 (Week 1):
├─ Session 5 (필수 선행) ─────┐
│                              ├─→ Session 8 (의존)
├─ Session 6 (병렬 가능) ─────┤
└─ Session 7 (병렬 가능) ─────┘

Phase 2 (Week 2):
├─ Session 9 (병렬 가능) ─────┐
├─ Session 10 (병렬 가능) ────┤
└─ Session 11 (독립) ─────────┴─→ Session 12 (최종)
```

### 병렬 처리 전략

**Week 1 Day 1-2**:
- Session 5 (필수 먼저)

**Week 1 Day 3-4** (병렬):
- Session 6 (담당자 A)
- Session 7 (담당자 B)

**Week 1 Day 5**:
- Session 8 (Session 5 완료 필요)

**Week 2 Day 1-2** (병렬):
- Session 9 (담당자 A)
- Session 10 (담당자 B)

**Week 2 Day 3**:
- Session 11

**Week 2 Day 4-5**:
- Session 12 (최종 정리)

---

## 각 세션 완료 후 체크리스트

### 공통 체크리스트
- [ ] 코드 변경사항 검토
- [ ] 단위 테스트 실행 (있는 경우)
- [ ] 통합 테스트 실행
- [ ] 구문 검사 통과 (`python -m py_compile`)
- [ ] Import 순환 참조 확인
- [ ] 로그 확인 (에러 없음)
- [ ] Git commit (세션 단위)
- [ ] 세션 완료 보고서 작성

### Session별 특수 체크리스트

**Session 5**:
- [ ] JSONParsingResult 모든 케이스 테스트
- [ ] 기존 Agent 영향 없음 확인

**Session 6**:
- [ ] 환경변수 .env.example 추가
- [ ] 기본값 정상 작동 확인

**Session 7**:
- [ ] API 응답 포맷 일관성 확인
- [ ] 기존 클라이언트 호환성 확인

**Session 8**:
- [ ] 레거시 코드 완전 제거 확인
- [ ] Pydantic ValidationError 처리 확인

**Session 9-10**:
- [ ] Enum import 경로 일관성
- [ ] 하드코딩 제거 확인

**Session 11**:
- [ ] 서비스 레이어 에러 처리 확인

**Session 12**:
- [ ] 전체 문서 업데이트
- [ ] 최종 통합 테스트

---

## 위험 관리

### 잠재적 위험

1. **Session 5**: LLM 호출 전체에 영향
   - 대응: 철저한 테스트, 점진적 적용

2. **Session 7**: 다수 API 파일 수정
   - 대응: API 버전 관리, 호환성 테스트

3. **Session 8**: Agent 핵심 로직 변경
   - 대응: 백업 및 롤백 계획

### 롤백 계획

각 세션별로 Git commit 분리:
```bash
# Session 5 완료 후
git add app/agents/llm_client.py
git commit -m "Session 5: LLM Client JSON 파싱 개선"

# 문제 발생 시
git revert HEAD
```

---

## 성공 지표

### 정량적 지표
- [ ] 하드코딩 항목: 46개 → 15개 이하 (67% 감소)
- [ ] Pydantic 사용률: 70% → 95% 이상
- [ ] Enum 관리 항목: 8개 → 20개 이상
- [ ] API 일관성: 60% → 95% 이상

### 정성적 지표
- [ ] 유지보수성 향상 (+40%)
- [ ] 안정성 향상 (+30%)
- [ ] 타입 안전성 향상 (+25%)
- [ ] 개발 생산성 향상 (+25%)

---

## 최종 산출물

### 코드
- 수정된 파일: 약 30개
- 신규 파일: 약 8개
- 삭제된 코드: 약 500 LOC
- 추가된 코드: 약 800 LOC

### 문서
- [ ] 각 세션 완료 보고서 (8개)
- [ ] CODE_QUALITY_AUDIT_REPORT.md 업데이트
- [ ] .env.example 업데이트
- [ ] README.md 업데이트

### 테스트
- [ ] 단위 테스트 추가 (10+개)
- [ ] 통합 테스트 업데이트
- [ ] E2E 테스트 실행

---

**작성일**: 2026-01-01
**검토**: Architecture Team
**승인**: CTO
