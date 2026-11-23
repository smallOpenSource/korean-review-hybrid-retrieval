# 신규 스케줄러 빠른 시작 가이드

## 요약

레거시 배치 시스템의 핵심 기능(증분 수집, 텍스트 전처리, 시간 분할)을 신규 스케줄러에 통합 완료.

**완료된 작업:**
- ✅ ReviewData 클래스 개선 (전처리, 시간 분할)
- ✅ 증분 수집 로직 (중복 방지)
- ✅ DB Session Factory & 연결 풀링
- ✅ Job 실행 추적 & 모니터링
- ✅ DDL 스키마 정의

**남은 작업:**
- 🔧 데이터베이스 생성 및 테이블 설정
- 🔧 환경변수 설정
- 🔧 실행 테스트

---

## Quick Start (3단계)

### 1️⃣ 데이터베이스 설정 (5분)

```bash
# 1. 데이터베이스 생성
mysql -u root -p -e "CREATE DATABASE app_reviews_scheduler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. 권한 부여
mysql -u root -p -e "GRANT ALL PRIVILEGES ON app_reviews_scheduler.* TO 'your_user'@'localhost'; FLUSH PRIVILEGES;"

# 3. 테이블 생성
mysql -u your_user -p app_reviews_scheduler < scheduler/schema/reviews_table.sql

# 4. 확인
mysql -u your_user -p app_reviews_scheduler -e "SHOW TABLES;"
```

### 2️⃣ 환경변수 설정

`.env` 파일에 추가:

```bash
# Scheduler Database
SCHEDULER_DB_HOST=127.0.0.1
SCHEDULER_DB_PORT=3306
SCHEDULER_DB_USER=your_user
SCHEDULER_DB_PASSWORD=<set-in-.env>
SCHEDULER_DB_NAME=app_reviews_scheduler
```

또는 기존 MySQL 설정 재사용:
```bash
# 기존 MYSQL_USER, MYSQL_PASSWORD 자동 사용
SCHEDULER_DB_NAME=app_reviews_scheduler
```

### 3️⃣ 테스트 실행

```bash
# DB 연결 테스트
cd <PROJECT_ROOT>/scheduler
python -c "from utils import get_db_session_factory; print('✅ OK' if get_db_session_factory().health_check() else '❌ FAIL')"

# 앱 목록 확인
python -m scheduler.main --list-apps

# 고우선순위 앱 수집 테스트
python -m scheduler.main --run-once collect_high
```

---

## 주요 기능 설명

### 🔄 증분 수집 (중복 방지)

```python
# 수집된 리뷰 중 DB에 이미 있는 것은 자동으로 skip
# reviewId 기반으로 중복 체크
```

**로그 예시:**
```
INFO: Found 150 existing reviews for com.example.app
INFO: Saved reviews: 23 new, 127 duplicates
```

### 📝 텍스트 전처리 (3가지 버전 저장)

| 필드 | 용도 | 예시 |
|------|------|------|
| `content` | 원본 (Play Store 그대로) | "정말 좋은 앱입니다! ⭐⭐⭐" |
| `original_content` | 사람이 읽을 용도 | "정말 좋은 앱입니다 " |
| `cleaned_content` | NLP 분석용 | "정말좋은앱입니다" |

### ⏰ 시간 분할 (쿼리 최적화)

```sql
-- ❌ 느림 (함수 사용)
SELECT * FROM reviews WHERE YEAR(at) = 2024 AND MONTH(at) = 11;

-- ✅ 빠름 (인덱스 활용)
SELECT * FROM reviews WHERE year = 2024 AND month = 11;
```

### 📊 Job 실행 추적

모든 수집 작업은 `job_runs` 테이블에 자동 기록:

```sql
SELECT job_name, package_id, status, rows_inserted, rows_duplicate
FROM job_runs
ORDER BY started_at DESC
LIMIT 5;
```

---

## 파일 구조

```
scheduler/
├── schema/
│   └── reviews_table.sql          # ✅ DDL 스키마
├── utils/
│   ├── database.py                # ✅ DB Session Factory
│   └── job_tracker.py             # ✅ Job 실행 추적
├── collectors/
│   └── play_store_collector.py    # ✅ 전처리 적용
├── jobs/
│   └── collect_reviews.py         # ✅ 증분 수집 적용
├── DATABASE_SETUP.md              # 📖 DB 설정 가이드 (상세)
└── IMPLEMENTATION_TODO.md         # 📋 작업 체크리스트
```

---

## 검증 체크리스트

실행 후 다음 항목들을 확인하세요:

### ✅ 데이터 저장 확인
```sql
-- 리뷰가 저장되었는지 확인
SELECT COUNT(*) FROM reviews;

-- 전처리 필드 확인
SELECT content, original_content, cleaned_content FROM reviews LIMIT 3;

-- 시간 분할 확인
SELECT year, month, day, hour FROM reviews LIMIT 3;
```

### ✅ 중복 방지 확인
```bash
# 같은 명령 2회 실행
python -m scheduler.main --run-once collect_high

# 2번째 실행 로그에서 "duplicates" 확인
# 예: "Saved reviews: 0 new, 150 duplicates"
```

### ✅ Job 추적 확인
```sql
-- Job 실행 기록 확인
SELECT * FROM job_runs ORDER BY started_at DESC LIMIT 5;

-- 통계 확인
SELECT SUM(rows_inserted), SUM(rows_duplicate) FROM job_runs WHERE status='completed';
```

---

## 문제 해결

### Q: "Access denied" 에러
```bash
# 권한 재부여
mysql -u root -p -e "
GRANT ALL PRIVILEGES ON app_reviews_scheduler.* TO 'your_user'@'%';
FLUSH PRIVILEGES;
"
```

### Q: "Unknown database" 에러
```bash
# 데이터베이스 재생성
mysql -u root -p -e "CREATE DATABASE app_reviews_scheduler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### Q: "Table has no partition" 에러
```sql
-- 새 파티션 추가
ALTER TABLE reviews ADD PARTITION (PARTITION p2027 VALUES LESS THAN (2028));
```

---

## 다음 단계

1. **정기 스케줄 설정**: `main.py`에서 cron 스케줄 활성화
2. **메인 앱 통합**: OpenSearch와 데이터 동기화
3. **모니터링 대시보드**: Grafana 또는 웹 UI로 job_runs 시각화

더 자세한 내용은 `DATABASE_SETUP.md` 참고.
