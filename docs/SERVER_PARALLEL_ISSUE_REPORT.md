# Ollama 서버 병렬 처리 문제 보고서

**작성일**: 2026-01-03
**서버**: llm-server.example.com:11434
**모델**: exaone3.5:2.4b
**상황**: 서버 관리자가 OLLAMA_NUM_PARALLEL=8 설정 후에도 병렬 처리 실패

---

## 📊 Executive Summary

**상태**: ❌ **서버 병렬 처리 설정 미적용 또는 리소스 부족**

**핵심 문제**:
1. 서버 관리자가 `OLLAMA_NUM_PARALLEL=8` 설정했다고 함
2. 하지만 테스트 결과는 설정 전과 **완전 동일**
3. 병렬 4개 이상: 100% 실패 (리소스 제한 오류)
4. 병렬 2개: 87.5% 성공 (불안정, 운영 부적합)

**임시 조치**: `ANALYSIS_CONCURRENCY=1` (순차 처리) 유지

---

## 🧪 테스트 결과

### 테스트 1: 간단한 요청 (50 tokens, 0.5초)

| Concurrency | 성공률 | 결과 |
|-------------|--------|------|
| 순차 2개 | 100% (2/2) | ✅ 성공 |
| 병렬 4개 | **0%** (0/4) | ❌ 실패 - "model runner has unexpectedly stopped" |
| 병렬 8개 | **0%** (0/8) | ❌ 실패 - "resource limitations" |

**오류 메시지**:
```
{"error":"model runner has unexpectedly stopped, this may be due to resource limitations or an inter..."}
{"error":"an error was encountered while running the model: read tcp 127.0.0.1:..."}
```

### 테스트 2: 실제 리뷰 분석 (500 tokens, 25초)

| Concurrency | 성공률 | 결과 |
|-------------|--------|------|
| 병렬 2개 | 87.5% (7/8) | ⚠️ 불안정 - 12.5% 실패 |
| 병렬 4개 | 0% (0/8) | ❌ 완전 실패 |
| 병렬 8개 | 0% (0/16) | ❌ 완전 실패 |

---

## 🔍 문제 진단

### 1. 서버 설정 미적용 (가장 유력)

**증거**:
- 설정 변경 전후 테스트 결과 **완전 동일**
- 병렬 4개, 8개 여전히 100% 실패
- 오류 메시지 동일

**가능한 원인**:

#### A. 환경 변수가 Ollama 프로세스에 전달 안 됨

```bash
# 잘못된 방법 (서비스에 적용 안 됨)
export OLLAMA_NUM_PARALLEL=8
ollama serve &

# 올바른 방법 (systemd 사용 시)
sudo vi /etc/systemd/system/ollama.service

[Service]
Environment="OLLAMA_NUM_PARALLEL=8"
Environment="OLLAMA_MAX_LOADED_MODELS=1"

sudo systemctl daemon-reload
sudo systemctl restart ollama

# 확인
sudo systemctl status ollama
ps aux | grep ollama
```

#### B. Ollama 서버 재시작 안 함

환경 변수 설정 후 **반드시 재시작** 필요:
```bash
sudo systemctl restart ollama
# 또는
pkill ollama && ollama serve
```

#### C. 다른 설정 파일이 우선 적용

Ollama는 여러 곳에서 설정 가능:
- `/etc/systemd/system/ollama.service`
- `~/.ollama/config`
- 실행 시 환경 변수

우선순위 확인 필요.

---

### 2. GPU 메모리 부족 (두 번째 유력)

**증거**:
- 오류 메시지: `"resource limitations"`
- 병렬 수 증가 시 즉시 실패

**진단 방법**:
```bash
# Ollama 서버에서 실행
nvidia-smi

# 출력 예시:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2    |
# |-------------------------------+----------------------+----------------------+
# |   0  Tesla T4           On   | 00000000:00:04.0 Off |                    0 |
# | N/A   45C    P0    25W /  70W |  14500MiB / 15360MiB |     85%      Default |
# +-------------------------------+----------------------+----------------------+
#                                 ^^^^^^^^  ^^^^^^^^
#                                 사용 중   전체
```

**exaone3.5:2.4b 메모리 요구사항**:
- 1개 인스턴스: ~2-3GB
- 4개 인스턴스: ~8-12GB
- 8개 인스턴스: ~16-24GB

**필요 조건**:
- 최소 16GB 여유 GPU 메모리 (병렬 8개 기준)
- 현재 사용 중인 메모리 확인 필요

---

### 3. 모델 로더 설정 문제

**가능성**:
- `OLLAMA_MAX_LOADED_MODELS=1`로 설정되어 있을 수 있음
- 동시에 1개 모델 인스턴스만 허용

**확인**:
```bash
# Ollama API로 확인
curl http://localhost:11434/api/ps

# 또는 로그 확인
journalctl -u ollama -n 100 | grep -i "model\|load\|parallel"
```

---

## 🔧 서버 관리자 조치 사항

### Step 1: 현재 설정 확인

```bash
# 1. Ollama 프로세스의 환경 변수 확인
ps aux | grep ollama
ps eww $(pgrep ollama) | tr ' ' '\n' | grep OLLAMA

# 2. systemd 서비스 설정 확인 (systemd 사용 시)
systemctl cat ollama

# 3. 실행 중인 설정 확인
curl http://localhost:11434/api/tags
curl http://localhost:11434/api/ps
```

**기대값**:
```
OLLAMA_NUM_PARALLEL=8
OLLAMA_MAX_LOADED_MODELS=1 (또는 8)
```

---

### Step 2: 올바른 설정 적용

#### systemd 사용 시

```bash
# 1. 서비스 파일 수정
sudo vi /etc/systemd/system/ollama.service

# 다음 추가:
[Service]
Environment="OLLAMA_NUM_PARALLEL=8"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_MAX_QUEUE=512"

# 2. 재로드 및 재시작
sudo systemctl daemon-reload
sudo systemctl restart ollama

# 3. 확인
sudo systemctl status ollama
journalctl -u ollama -n 50
```

#### 직접 실행 시

```bash
# 1. 기존 프로세스 종료
pkill ollama

# 2. 환경 변수와 함께 실행
OLLAMA_NUM_PARALLEL=8 \
OLLAMA_MAX_LOADED_MODELS=1 \
ollama serve

# 또는 screen/tmux 사용
screen -S ollama
OLLAMA_NUM_PARALLEL=8 ollama serve
# Ctrl+A, D로 detach
```

---

### Step 3: GPU 메모리 확인

```bash
# 1. 현재 메모리 사용량
nvidia-smi

# 2. 실시간 모니터링
watch -n1 nvidia-smi

# 3. 다른 프로세스가 GPU 사용하는지 확인
nvidia-smi pmon
```

**필요 조건**:
- 여유 GPU 메모리: 최소 16GB (병렬 8개)
- 또는 10GB (병렬 4개)
- 또는 5GB (병렬 2개)

**GPU 메모리 부족 시 옵션**:
```bash
# 옵션 A: 병렬 수 감소
OLLAMA_NUM_PARALLEL=4  # 8 → 4

# 옵션 B: 양자화 모델 사용 (메모리 50% 절감)
ollama pull exaone3.5:2.4b-q4_0

# 옵션 C: GPU 레이어 제한
OLLAMA_GPU_LAYERS=20  # 전체보다 적게
```

---

### Step 4: 설정 검증

```bash
# 1. 간단한 API 테스트
curl -X POST http://localhost:11434/api/generate \
  -d '{
    "model": "exaone3.5:2.4b",
    "prompt": "Hello",
    "stream": false
  }'

# 2. 병렬 요청 테스트 (4개 동시)
for i in {1..4}; do
  curl -X POST http://localhost:11434/api/generate \
    -d '{"model": "exaone3.5:2.4b", "prompt": "Test '$i'", "stream": false}' &
done
wait

# 모두 성공하면 설정 OK
```

---

## 📋 우리 측 재테스트 절차

서버 관리자가 설정 완료 후 다음 테스트:

### 1. 간단한 요청 테스트

```bash
python /tmp/test_server_parallel_8.py
```

**기대 결과**:
- 병렬 4개: 100% 성공
- 병렬 8개: 100% 성공
- 속도 향상: 4배 이상

### 2. 실제 리뷰 분석 테스트

```bash
python /tmp/test_review_analysis_progressive.py
```

**기대 결과**:
- Concurrency=2: 100% 성공
- Concurrency=4: 100% 성공
- Concurrency=8: 90% 이상 성공

### 3. .env 업데이트

성공 시:
```bash
# .env
ANALYSIS_CONCURRENCY=8  # 1 → 8로 증가
```

---

## 📊 예상 성능 비교

### 현재 (Concurrency=1)

| 지표 | 값 |
|------|-----|
| 평균 처리 시간 | 22.74초/리뷰 |
| 시간당 처리 | 158개 |
| 일일 처리 | 3,792개 |
| **598K 처리** | **157일** |

### 서버 문제 해결 후 (Concurrency=8)

| 지표 | 값 |
|------|-----|
| 평균 처리 시간 | 22.74초/리뷰 (동일) |
| 시간당 처리 | 1,264개 (8배) |
| 일일 처리 | 30,336개 (8배) |
| **598K 처리** | **20일** (7.85배 빠름) |

**시간 절약**: 137일 (4.5개월)

---

## 💡 대안 (서버 문제 미해결 시)

### 옵션 1: Gemini 사용 (권장)

```bash
# .env
LLM_FALLBACK_ORDER=gemini,ollama,groq,openai
GEMINI_MODEL_REALTIME=gemini-2.0-flash-lite
ANALYSIS_CONCURRENCY=8
```

**장점**:
- 병렬 처리 완벽 지원
- 평균 2-3초/리뷰 (Ollama의 10배 빠름)
- 598K 처리: **~26일** (1개월)

**단점**:
- API 비용 (하지만 API 키 10개 rotation으로 무료 가능)
- Rate limit: 15 RPM (키 rotation으로 해결)

---

### 옵션 2: Concurrency=1 유지 (현재)

```bash
# .env
OLLAMA_MODEL=exaone3.5:2.4b
ANALYSIS_CONCURRENCY=1
```

**장점**:
- 100% 안정성
- 비용 없음

**단점**:
- 598K 처리: 157일 (5.2개월)

---

## 🎯 현재 상태

**적용된 설정** (.env):
```bash
OLLAMA_MODEL=exaone3.5:2.4b
ANALYSIS_CONCURRENCY=1  # 서버 병렬 처리 문제 해결 시 2 또는 8로 증가
```

**다음 단계**:
1. ✅ 서버 관리자에게 본 보고서 전달
2. ⏳ 서버 설정 확인 및 수정 대기
3. ⏳ 재테스트 후 Concurrency 증가

---

## 📞 서버 관리자 체크리스트

- [ ] 1. Ollama 프로세스의 환경 변수 확인 (`ps eww $(pgrep ollama)`)
- [ ] 2. `OLLAMA_NUM_PARALLEL=8` 설정 확인
- [ ] 3. Ollama 서비스 재시작 (`systemctl restart ollama`)
- [ ] 4. GPU 메모리 확인 (`nvidia-smi`) - 최소 16GB 여유 필요
- [ ] 5. 간단한 병렬 요청 테스트 (위 Step 4)
- [ ] 6. 우리 측 재테스트 요청

---

**작성자**: Claude Code
**연락**: 재테스트 요청 시 알려주세요
**우선순위**: 높음 (137일 절약 가능)
