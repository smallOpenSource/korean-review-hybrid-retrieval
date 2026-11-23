# 파이프라인 데이터 적재 검증 가이드

## 📋 검증 절차

### 1. 실행 전 상태 확인
```bash
# 스크립트 사용
./scripts/check_pipeline_before.sh

# 또는 수동 확인
mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -P"${MYSQL_PORT:-3306}" -h"$MYSQL_HOST" app_reviews_scheduler -e "
SELECT 
    COUNT(*) as total_reviews,
    SUM(CASE WHEN synced_to_opensearch = TRUE THEN 1 ELSE 0 END) as synced,
    SUM(CASE WHEN analyzed = TRUE THEN 1 ELSE 0 END) as analyzed
FROM reviews;"
```

**기록할 값:**
- `total_reviews`: ______
- `synced`: ______
- `analyzed`: ______

---

### 2. 파이프라인 실행
```bash
python -m scheduler.main --run-pipeline
```

**예상 실행 시간:** 약 48분
- [1/4] collect_reviews: ~30분
- [2/4] analyze_reviews: ~10분
- [3/4] sync_to_opensearch: ~5분
- [4/4] generate_wordcloud: ~3분

---

### 3. 실행 후 검증
```bash
# 스크립트 사용 (권장)
./scripts/check_pipeline_after.sh

# 또는 수동 확인
mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -P"${MYSQL_PORT:-3306}" -h"$MYSQL_HOST" app_reviews_scheduler -e "
SELECT 
    COUNT(*) as total_reviews,
    SUM(CASE WHEN synced_to_opensearch = TRUE THEN 1 ELSE 0 END) as synced,
    SUM(CASE WHEN analyzed = TRUE THEN 1 ELSE 0 END) as analyzed
FROM reviews;"
```

---

## 🔍 상세 검증 SQL

### MariaDB 확인

#### A. reviews 테이블 전체 현황
```sql
/* sql_id: verify_reviewsOverview */
SELECT 
    COUNT(*) as total_reviews,
    SUM(CASE WHEN synced_to_opensearch = TRUE THEN 1 ELSE 0 END) as synced_to_os,
    SUM(CASE WHEN synced_to_opensearch = FALSE THEN 1 ELSE 0 END) as not_synced,
    SUM(CASE WHEN analyzed = TRUE THEN 1 ELSE 0 END) as analyzed,
    SUM(CASE WHEN analyzed = FALSE THEN 1 ELSE 0 END) as not_analyzed,
    MIN(created_at) as oldest_review,
    MAX(created_at) as newest_review
FROM reviews;
```

#### B. 앱별 수집 현황
```sql
/* sql_id: verify_appCollectionStatus */
SELECT 
    package_id,
    COUNT(*) as review_count,
    MAX(at) as latest_review_date,
    MAX(created_at) as last_collected
FROM reviews 
GROUP BY package_id 
ORDER BY last_collected DESC 
LIMIT 20;
```

#### C. 최근 1시간 내 수집된 리뷰
```sql
/* sql_id: verify_recentCollection */
SELECT 
    package_id,
    COUNT(*) as new_reviews,
    MAX(created_at) as collected_at
FROM reviews 
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY package_id;
```

#### D. 동기화 상태
```sql
/* sql_id: verify_syncStatus */
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN synced_to_opensearch = TRUE THEN 1 ELSE 0 END) as synced,
    ROUND(SUM(CASE WHEN synced_to_opensearch = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as sync_percent,
    MIN(synced_at) as first_sync,
    MAX(synced_at) as last_sync
FROM reviews;
```

#### E. Job 실행 이력 (job_runs 테이블)
```sql
/* sql_id: verify_jobHistory */
SELECT 
    job_name,
    package_id,
    status,
    rows_inserted,
    rows_duplicate,
    TIMESTAMPDIFF(SECOND, started_at, completed_at) as duration_sec,
    error_message,
    started_at,
    completed_at
FROM job_runs 
WHERE started_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
ORDER BY started_at DESC;
```

---

### OpenSearch 확인

#### A. 인덱스 존재 및 문서 수
```bash
# 인덱스 목록
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/_cat/indices/app_reviews?v

# 문서 수
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/app_reviews/_count | python3 -m json.tool
```

**예상 출력:**
```json
{
  "count": 12345,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
```

#### B. 최근 인덱싱된 문서
```bash
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/app_reviews/_search -H 'Content-Type: application/json' -d '{
  "size": 5,
  "sort": [{"created_at": "desc"}],
  "_source": ["review_id", "app_id", "rating", "original_content", "created_at"]
}' | python3 -m json.tool
```

#### C. 앱별 문서 수
```bash
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/app_reviews/_search -H 'Content-Type: application/json' -d '{
  "size": 0,
  "aggs": {
    "apps": {
      "terms": {"field": "app_id", "size": 10}
    }
  }
}' | python3 -m json.tool
```

---

## ✅ 검증 체크리스트

### Stage 1: collect_reviews ✅
**MariaDB 확인:**
```sql
-- 새 리뷰 수집 확인
SELECT COUNT(*) FROM reviews WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR);

-- 앱별 수집 확인
SELECT package_id, COUNT(*) FROM reviews 
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY package_id;
```

**기대 결과:** 새 리뷰 건수 증가

---

### Stage 2: analyze_reviews ✅
**MariaDB 확인:**
```sql
-- 분석 완료 리뷰 수
SELECT COUNT(*) FROM reviews WHERE analyzed = TRUE;

-- 최근 분석된 리뷰
SELECT review_id, package_id, analyzed FROM reviews 
WHERE analyzed = TRUE 
ORDER BY created_at DESC LIMIT 10;
```

**기대 결과:** `analyzed = TRUE` 건수 증가

---

### Stage 3: sync_to_opensearch ✅
**MariaDB 확인:**
```sql
-- 동기화된 리뷰 수
SELECT COUNT(*) FROM reviews WHERE synced_to_opensearch = TRUE;

-- 최근 동기화
SELECT COUNT(*), MAX(synced_at) FROM reviews 
WHERE synced_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR);
```

**OpenSearch 확인:**
```bash
# 문서 수 증가 확인
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/app_reviews/_count
```

**기대 결과:** 
- MariaDB: `synced_to_opensearch = TRUE` 증가
- OpenSearch: 문서 수 증가 (MariaDB와 일치)

---

### Stage 4: generate_wordcloud ✅
**파일 시스템 확인:**
```bash
# 워드클라우드 파일 생성 확인
ls -lh /var/data/wordclouds/
find /var/data/wordclouds/ -type f -mtime -1
```

**기대 결과:** 새 워드클라우드 이미지 파일 생성

---

## 📊 예상 결과 예시

### 실행 전
```
total_reviews: 10,000
synced_to_os: 8,000
analyzed: 7,500
```

### 실행 후
```
total_reviews: 12,345  (↑ 2,345개 수집)
synced_to_os: 12,345  (↑ 4,345개 동기화)
analyzed: 12,000      (↑ 4,500개 분석)
```

---

## 🚨 문제 해결

### 리뷰가 수집되지 않음
```sql
-- Job 실행 확인
SELECT * FROM job_runs WHERE job_name = 'collect_reviews' ORDER BY started_at DESC LIMIT 1;

-- 에러 확인
SELECT error_message FROM job_runs WHERE status = 'failed' ORDER BY started_at DESC LIMIT 5;
```

### 동기화가 안 됨
```sql
-- 미동기화 리뷰 확인
SELECT COUNT(*) FROM reviews WHERE synced_to_opensearch = FALSE;

-- Sync job 실행 이력
SELECT * FROM job_runs WHERE job_name = 'sync_to_opensearch' ORDER BY started_at DESC;
```

### OpenSearch 연결 실패
```bash
# OpenSearch 상태 확인
curl -k -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/_cluster/health

# 환경변수 확인
echo $OPENSEARCH_HOSTS
echo $OPENSEARCH_USER
```

---

## 📝 실행 예시

```bash
# 1. 실행 전 확인
./scripts/check_pipeline_before.sh > logs/before_$(date +%Y%m%d_%H%M%S).log

# 2. 파이프라인 실행
python -m scheduler.main --run-pipeline 2>&1 | tee logs/pipeline_$(date +%Y%m%d_%H%M%S).log

# 3. 실행 후 검증
./scripts/check_pipeline_after.sh > logs/after_$(date +%Y%m%d_%H%M%S).log

# 4. 결과 비교
diff logs/before_*.log logs/after_*.log
```
