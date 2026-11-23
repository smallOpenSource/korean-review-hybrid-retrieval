# Ollama 다중 엔드포인트 로드밸런싱 구현

## 변경 사항

### 1. `settings.py` - OllamaConfig 확장

**추가된 기능**:
- `base_urls: List[str]` - 여러 엔드포인트 저장
- `get_endpoint()` 메서드 - 라운드로빈 엔드포인트 선택
- `_current_index` - 라운드로빈 인덱스 추적

**동작 방식**:
```python
def get_endpoint(self) -> str:
    """Get next endpoint using round-robin load balancing."""
    endpoint = self.base_urls[self._current_index % len(self.base_urls)]
    self._current_index += 1
    return endpoint
```

### 2. `llm_client.py` - OllamaLLMClient 수정

**Before**:
```python
url = f"{self._settings.base_url}/v1/chat/completions"
```

**After**:
```python
endpoint = self._settings.get_endpoint()  # 라운드로빈 선택
url = f"{endpoint}/v1/chat/completions"
```

---

## .env 설정 방법

### 방법 1: OLLAMA_BASE_URLS (권장)
```bash
# 쉼표로 구분하여 여러 엔드포인트 설정
OLLAMA_BASE_URLS=http://ollama-host.example.com:11434,http://ollama-host.example.com:11435

# 기존 설정은 제거 또는 주석 처리 (fallback으로 작동)
# OLLAMA_BASE_URL=http://ollama-host.example.com:11434
```

### 방법 2: 단일 엔드포인트 (기존)
```bash
# 단일 엔드포인트만 사용 시 (기존 방식과 동일)
OLLAMA_BASE_URL=http://ollama-host.example.com:11434
```

---

## 동작 원리

### 라운드로빈 로드밸런싱

1. **첫 번째 요청**: 엔드포인트 #1 (11434)
2. **두 번째 요청**: 엔드포인트 #2 (11435)
3. **세 번째 요청**: 엔드포인트 #1 (11434)
4. **네 번째 요청**: 엔드포인트 #2 (11435)
...

### 예시
```python
# .env
OLLAMA_BASE_URLS=http://server1:11434,http://server2:11435

# 자동 분산
요청 1 → http://server1:11434
요청 2 → http://server2:11435
요청 3 → http://server1:11434
요청 4 → http://server2:11435
```

---

## 장점

✅ **부하 분산**: 2개 서버에 자동으로 요청 분산  
✅ **동시 처리**: 2배 빠른 처리 속도  
✅ **간단한 설정**: .env 파일만 수정  
✅ **하위 호환성**: 단일 엔드포인트도 계속 지원  

---

## 주의사항

1. **모든 엔드포인트는 동일한 모델**을 사용해야 합니다
2. **모든 엔드포인트가 정상 작동**해야 합니다 (에러 시 다음 요청은 다음 서버로)
3. **API KEY가 동일**해야 합니다 (OLLAMA_API_KEY)

---

## 테스트 방법

```bash
# .env 수정
echo "OLLAMA_BASE_URLS=http://ollama-host.example.com:11434,http://ollama-host.example.com:11435" >> .env

# 스케줄러 재시작 (설정 반영)
./scripts/stop_scheduler.sh
./scripts/start_scheduler.sh

# 로그 확인 - 두 서버로 분산되는지 확인
tail -f logs/scheduler.log | grep "Calling Ollama"
```
