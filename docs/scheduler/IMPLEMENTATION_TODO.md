# 신규 스케줄러 레거시 통합 개선사항 적용 TODO

## 완료된 작업 ✅

### 1. ReviewData 클래스 개선 (play_store_collector.py)
- [x] `original_content` 필드 추가 (특수문자 일부 보존)
- [x] `cleaned_content` 필드 추가 (한글/숫자만, NLP 분석용)
- [x] 시간 분할 필드 추가 (`year`, `month`, `day`, `hour`)
- [x] `__post_init__` 메서드에 텍스트 전처리 로직 구현
- [x] `to_dict()` 메서드에 신규 필드 추가

### 2. 증분 수집 로직 구현 (collect_reviews.py)
- [x] `_save_reviews()` 메서드 구현
- [x] 기존 review_id 조회 로직 추가
- [x] 중복 필터링 및 통계 기록
- [x] SQLAlchemy text() 사용하여 raw SQL 실행

### 3. DDL 작성 (schema/reviews_table.sql)
- [x] `reviews` 테이블 스키마 정의
- [x] 레거시 호환 컬럼 구조
- [x] 파티셔닝 설정 (연도별)
- [x] 인덱스 최적화
- [x] `app_metadata` 테이블 추가
- [x] `job_runs` 테이블 추가 (작업 추적용)

### 4. DB Session Factory 구현 (utils/database.py)
- [x] DatabaseConfig 클래스로 환경변수 로드
- [x] SQLAlchemy engine 및 session factory 설정
- [x] 연결 풀링 구성 (QueuePool)
- [x] session_scope() context manager 구현
- [x] health_check() 메서드 추가
- [x] Singleton pattern 적용

### 5. Job 실행 추적 (utils/job_tracker.py)
- [x] JobRunTracker 클래스 구현
- [x] track_job() context manager
- [x] job_runs 테이블 관리
- [x] 실행 시간, 성공/실패 상태 기록
- [x] 통계 업데이트 (rows_inserted, rows_duplicate)

### 6. 메인 스케줄러 연동 (jobs/collect_reviews.py)
- [x] CollectReviewsJob에 session factory 자동 주입
- [x] DB 연결 실패 시 graceful degradation
- [x] JobRunTracker 통합
- [x] 앱별 실행 추적 및 통계 기록

---

## 남은 작업 🔧

### 7. 데이터베이스 초기 설정 (수동 작업)
- [ ] `.env` 파일에 스케줄러 DB 설정 추가 (DATABASE_SETUP.md 참고)
- [ ] MySQL/MariaDB에서 데이터베이스 생성
  ```bash
  mysql -u root -p -e "CREATE DATABASE app_reviews_scheduler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  ```
- [ ] DDL 실행하여 테이블 생성
  ```bash
  mysql -u your_user -p app_reviews_scheduler < scheduler/schema/reviews_table.sql
  ```
- [ ] DB 연결 테스트
  ```bash
  python -c "from scheduler.utils import get_db_session_factory; print('OK' if get_db_session_factory().health_check() else 'FAIL')"
  ```

### 8. 테스트 및 검증
- [ ] 단일 앱 수집 테스트
  ```bash
  python -m scheduler.main --run-once collect_high
  ```
- [ ] 중복 리뷰 필터링 확인 (2회 실행 후 duplicate count 확인)
- [ ] `job_runs` 테이블에 실행 기록 저장 확인
- [ ] 텍스트 전처리 결과 검증 (original_content, cleaned_content)
- [ ] 시간 분할 컬럼 저장 확인 (year, month, day, hour)
- [ ] 파티셔닝 동작 확인

### 9. 메인 앱과의 통합 (선택 사항)
- [ ] 메인 앱의 OpenSearch와 데이터 동기화 전략 수립
- [ ] `analyze_reviews.py` Job에서 스케줄러 DB 조회
- [ ] 분석 완료 시 `analyzed` 플래그 업데이트
- [ ] 양방향 데이터 흐름 설계
  - 스케줄러 → OpenSearch (검색용)
  - 스케줄러 → MySQL (분석 결과 저장)

---

## 검증 체크리스트 ✓

### 기능 검증
- [ ] 신규 리뷰만 저장되는지 확인 (중복 skip)
- [ ] `original_content`와 `cleaned_content`가 올바르게 생성되는지 확인
- [ ] `year`, `month`, `day`, `hour` 값이 정확한지 확인
- [ ] 파티션이 자동으로 선택되는지 확인

### 성능 검증
- [ ] 100개 앱 동시 수집 성능 측정
- [ ] 중복 체크 쿼리 속도 확인 (인덱스 활용)
- [ ] 파티셔닝으로 인한 쿼리 성능 개선 확인

### 안정성 검증
- [ ] DB 연결 실패 시 에러 핸들링
- [ ] 트랜잭션 롤백 동작 확인
- [ ] 재시작 후 증분 수집 정상 작동

---

## 다음 단계 권장사항

1. **우선순위 높음**: DB 설정 및 테이블 생성
2. **우선순위 중간**: Session factory 구현
3. **우선순위 낮음**: 메인 앱과의 통합

## 참고 파일
- 레거시 배치(증분 수집, 텍스트 전처리, 테이블 DDL)는 공개본에서 제외됨. 현재 구현은 `scheduler/` 와 `scripts/scheduler/schema/` 참고
