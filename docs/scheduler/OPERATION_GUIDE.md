# Scheduler 운영 가이드

## 개요

앱 리뷰 수집 스케줄러는 **2가지 모드**로 실행할 수 있습니다:
- **Daemon 모드**: 백그라운드에서 계속 실행 (운영 환경)
- **One-shot 모드**: 1회 실행 후 종료 (테스트, 수동 실행)

---

## 🔄 실행 모드

### 1. Daemon 모드 (기본) - 상시 실행

스케줄러를 시작하면 프로세스는 종료될 때까지 계속 실행됩니다.

#### 실행 방법
```bash
# 기본 실행
python -m scheduler.main

# 또는 직접 실행
python scheduler/main.py

# 설정 파일 지정
python -m scheduler.main --config /path/to/scheduler_config.yaml
```

#### 동작 방식
- ✅ `APScheduler`가 백그라운드에서 계속 실행
- ✅ 설정된 스케줄에 따라 자동으로 Job 실행
- ✅ `Ctrl+C` 또는 `SIGTERM` 신호로 종료
- ✅ 종료 시 graceful shutdown (실행 중인 Job 완료 후)

#### 기본 스케줄

| Job | 스케줄 | 설명 |
|-----|--------|------|
| **Collect Reviews (High)** | 4시간마다 | 고우선순위 앱 리뷰 수집 |
| **Collect Reviews (Medium)** | 8시간마다 | 중간 우선순위 앱 리뷰 수집 |
| **Collect Reviews (Low)** | 매일 02:00 | 저우선순위 앱 리뷰 수집 |
| **Analyze Reviews** | 1시간마다 | 수집된 리뷰 LLM 분석 |
| **Generate WordCloud** | 매일 03:00 | 워드클라우드 생성 |

스케줄은 `scheduler/config/scheduler_config.yaml`에서 변경 가능합니다.

#### 실행 로그 예시
```
2025-11-24 12:00:00 - INFO - Starting scheduler service...
2025-11-24 12:00:00 - INFO - Scheduler started with 5 jobs:
2025-11-24 12:00:00 - INFO -   - Collect Reviews (High Priority): next run at 2025-11-24 16:00:00
2025-11-24 12:00:00 - INFO -   - Collect Reviews (Medium Priority): next run at 2025-11-24 20:00:00
2025-11-24 12:00:00 - INFO -   - Collect Reviews (Low Priority): next run at 2025-11-25 02:00:00
2025-11-24 12:00:00 - INFO -   - Analyze Reviews: next run at 2025-11-24 13:00:00
2025-11-24 12:00:00 - INFO -   - Generate Word Clouds: next run at 2025-11-25 03:00:00
```

### 2. One-shot 모드 - 즉시 실행

특정 Job을 1회 실행하고 즉시 종료합니다. 테스트나 수동 실행에 적합합니다.

#### 실행 방법
```bash
# 고우선순위 앱 수집
python -m scheduler.main --run-once collect_high

# 중간 우선순위 앱 수집
python -m scheduler.main --run-once collect_medium

# 저우선순위 앱 수집
python -m scheduler.main --run-once collect_low

# 리뷰 분석
python -m scheduler.main --run-once analyze

# 워드클라우드 생성
python -m scheduler.main --run-once wordcloud
```

#### 동작 방식
- ✅ 즉시 1회 실행
- ✅ 완료 후 자동 종료
- ✅ 스케줄 등록 없음
- ✅ 결과를 stdout으로 출력

#### 사용 사례
- **테스트**: 새로운 앱 추가 후 수집 테스트
- **수동 실행**: 스케줄 외에 즉시 수집 필요 시
- **Cron 통합**: 외부 cron으로 스케줄링
- **디버깅**: 특정 Job 동작 확인

---

## 🛠️ 유틸리티 명령어

### 앱 목록 확인
```bash
python -m scheduler.main --list-apps
```

출력 예시:
```
Configured Apps (70 total):
Config version: 2024-11-20

By priority: High=20, Medium=30, Low=20

Banks (25 apps):
  - A은행 (com.example.bank_a) [high]
  - B은행 (com.example.bank_b) [high]
  - C은행 (com.example.bank_c) [medium]
  ...
```

### 설정 검증
```bash
python -m scheduler.main --validate
```

출력 예시:
```
Configuration validation:
  Scheduler config: OK
  Apps configured: 70
  Jobs enabled:
    - collect_reviews: enabled
    - analyze_reviews: enabled
    - generate_wordcloud: enabled

Configuration is valid!
```

---

## 🚀 운영 환경 배포

### 방법 1: Systemd Service (권장)

#### 1. Service 파일 생성
```bash
sudo nano /etc/systemd/system/app-review-scheduler.service
```

#### 2. Service 내용
```ini
[Unit]
Description=App Review Scheduler Service
After=network.target mariadb.service redis.service
Wants=mariadb.service redis.service

[Service]
Type=simple
User=appuser
Group=appuser
WorkingDirectory=<PROJECT_ROOT>

# Python 가상환경 경로 (miniconda)
Environment="PATH=/opt/conda/envs/appreviews/bin:/usr/local/bin:/usr/bin"
Environment="PYTHONPATH=<PROJECT_ROOT>"

# 환경변수 파일 로드
EnvironmentFile=<PROJECT_ROOT>/.env

# 실행 명령
ExecStart=python -m scheduler.main

# 재시작 설정
Restart=always
RestartSec=10
StartLimitInterval=0

# 로그 설정
StandardOutput=journal
StandardError=journal
SyslogIdentifier=app-scheduler

[Install]
WantedBy=multi-user.target
```

#### 3. Service 등록 및 시작
```bash
# Service 파일 reload
sudo systemctl daemon-reload

# 부팅 시 자동 시작 설정
sudo systemctl enable app-review-scheduler

# Service 시작
sudo systemctl start app-review-scheduler

# 상태 확인
sudo systemctl status app-review-scheduler

# 로그 확인
sudo journalctl -u app-review-scheduler -f
```

#### 4. Service 관리
```bash
# 중지
sudo systemctl stop app-review-scheduler

# 재시작
sudo systemctl restart app-review-scheduler

# 자동 시작 해제
sudo systemctl disable app-review-scheduler
```

---

### 방법 2: Screen/Tmux (간단한 방법)

```bash
# Screen 세션 시작
screen -S scheduler

# 스케줄러 실행
cd <PROJECT_ROOT>
conda activate appreviews
python -m scheduler.main

# Detach: Ctrl+A, D

# 다시 연결
screen -r scheduler

# 세션 목록
screen -ls
```

---

### 방법 3: nohup (백그라운드 실행)

```bash
cd <PROJECT_ROOT>
conda activate appreviews

# 백그라운드 실행
nohup python -m scheduler.main > logs/scheduler.log 2>&1 &

# PID 확인
echo $!

# 프로세스 확인
ps aux | grep scheduler.main

# 종료
kill <PID>
```

---

## 📊 모니터링

### 로그 확인

#### Systemd 사용 시
```bash
# 실시간 로그
sudo journalctl -u app-review-scheduler -f

# 최근 100줄
sudo journalctl -u app-review-scheduler -n 100

# 특정 시간대
sudo journalctl -u app-review-scheduler --since "2025-11-24 00:00:00"
```

#### nohup 사용 시
```bash
tail -f logs/scheduler.log
```

### Job 실행 상태 확인

#### 데이터베이스 조회
```sql
-- 최근 실행 기록
SELECT job_name, package_id, status, 
       rows_inserted, rows_duplicate,
       started_at, completed_at
FROM job_runs
ORDER BY started_at DESC
LIMIT 20;

-- 실패한 작업
SELECT job_name, package_id, error_message, started_at
FROM job_runs
WHERE status = 'failed'
ORDER BY started_at DESC
LIMIT 10;

-- 오늘 수집 통계
SELECT 
    job_name,
    COUNT(*) as total_runs,
    SUM(rows_inserted) as total_inserted,
    SUM(rows_duplicate) as total_duplicates
FROM job_runs
WHERE DATE(started_at) = CURDATE()
GROUP BY job_name;
```

---

## 🔧 트러블슈팅

### 스케줄러가 시작되지 않음

#### 1. 설정 검증
```bash
python -m scheduler.main --validate
```

#### 2. 데이터베이스 연결 확인
```bash
python -c "
from scheduler.utils import get_db_session_factory
factory = get_db_session_factory()
print('OK' if factory.health_check() else 'FAIL')
"
```

#### 3. 환경변수 확인
```bash
# .env 파일 로드 확인
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('DB_HOST:', os.getenv('SCHEDULER_DB_HOST'))
print('DB_NAME:', os.getenv('SCHEDULER_DB_NAME'))
"
```

### Job이 실행되지 않음

#### 1. Job 활성화 확인
`scheduler/config/scheduler_config.yaml`에서:
```yaml
jobs:
  collect_reviews:
    enabled: true  # ← 확인
```

#### 2. 스케줄 확인
Daemon 모드 시작 로그에서 "next run at" 확인

#### 3. 수동 실행 테스트
```bash
python -m scheduler.main --run-once collect_high
```

### 메모리/CPU 사용량 높음

#### 1. 동시 실행 Job 제한
`scheduler_config.yaml`:
```yaml
scheduler:
  executor:
    max_workers: 5  # 줄이기
```

#### 2. 배치 크기 조정
`.env`:
```bash
SCHEDULER_COLLECTION_BATCH_SIZE=50  # 기본값 줄이기
```

---

## 📝 베스트 프랙티스

### 1. 운영 환경
- ✅ **Systemd service 사용** (자동 재시작, 로그 관리)
- ✅ **환경변수는 `.env` 파일 사용** (보안)
- ✅ **로그 rotation 설정** (디스크 공간 절약)
- ✅ **모니터링 알림 설정** (실패 시 알림)

### 2. 개발/테스트 환경
- ✅ **One-shot 모드로 테스트**
- ✅ **설정 검증 먼저 실행**
- ✅ **소수의 앱으로 시작** (high priority만)

### 3. 성능 최적화
- ✅ **우선순위별 스케줄 분산**
- ✅ **피크 시간 회피** (새벽 시간 활용)
- ✅ **DB 연결 풀 크기 조정**

---

## 🔗 관련 문서

- [빠른 시작 가이드](QUICKSTART.md)
- [데이터베이스 설정](DATABASE_SETUP.md)
- [구현 상태](IMPLEMENTATION_TODO.md)
- [스케줄러 설정](../scheduler/config/scheduler_config.yaml)
- [앱 설정](../scheduler/config/apps_config.yaml)
