# 입력 검증 사용 가이드

**작성일:** 2025-12-31
**대상:** Backend 개발자
**목적:** Pydantic 검증 시스템 사용 방법

---

## 🚀 빠른 시작

### 1. Query Parameter 검증

```python
from app.api.models_extended import ReviewQueryParams
from app.utils.validation import validate_query_params

@api_bp.route('/reviews', methods=['GET'])
@validate_query_params(ReviewQueryParams)
def get_reviews(validated_params: ReviewQueryParams):
    # 이미 검증된 파라미터
    page = validated_params.page          # int (1-10000)
    size = validated_params.size          # int (1-100)
    sentiment = validated_params.sentiment  # SentimentLabel enum

    # Enum 사용 시 .value로 문자열 변환
    if sentiment:
        filter_value = sentiment.value  # 'positive'
```

### 2. Request Body 검증

```python
from app.api.models_extended import AnalyzeRequest
from app.utils.validation import validate_request_body

@api_bp.route('/analysis/analyze', methods=['POST'])
@validate_request_body(AnalyzeRequest)
def analyze_review(validated_data: AnalyzeRequest):
    # 이미 검증 + 절삭된 content
    content = validated_data.content  # 1-2000자
```

### 3. Rate Limiting 적용

```python
from app.utils.rate_limiter import rate_limit

@api_bp.route('/search', methods=['POST'])
@rate_limit(limit=100, window=60)  # 100 req/min
@validate_request_body(SimilarReviewRequest)
def search_endpoint(validated_data):
    # ...
```

---

## 📋 사용 가능한 모델

### Query Models

**ReviewQueryParams**
```python
{
  "page": 1,              # 1-10000
  "size": 20,             # 1-100
  "sentiment": "positive", # Enum
  "category": "UI",       # max 50 chars
  "is_complaint": true,   # bool
  "date_from": "2024-01-01",  # ISO date
  "date_to": "2024-12-31"     # ISO date
}
```

**DashboardQueryParams**
```python
{
  "days": 30,      # 1-3650
  "category": "UI", # max 50 chars
  "year": 2024     # 2020-2030
}
```

### Request Models

**SimilarReviewRequest**
```python
{
  "content": "앱이 좋습니다...",  # 10-2000자
  "app_id": "com.example",      # optional
  "k": 20,                       # 1-50 (또는 top_k)
  "min_similarity": 0.8          # 0.0-1.0 (또는 threshold)
}
```

**AnalyzeRequest**
```python
{
  "content": "리뷰 내용...",      # 1-5000자 (자동 2000자 절삭)
  "analyze_sentiment": true,    # default: true
  "analyze_category": true,     # default: true
  "analyze_complaint": true     # default: true
}
```

**ComplaintUpdateRequest**
```python
{
  "status": "in_progress",       # Enum: new/in_progress/resolved/closed
  "assigned_to": "홍길동",        # max 100 chars
  "notes": "처리 중입니다"        # max 1000 chars
}
```

---

## 🎯 Enum 타입

### SentimentLabel
```python
"very_negative" | "negative" | "neutral" | "positive" | "very_positive"
```

### ComplaintStatus
```python
"new" | "in_progress" | "resolved" | "closed"
```

### SortOrder
```python
"asc" | "desc"
```

---

## ⚠️ 에러 응답

### ValidationError (400)

```json
{
  "status": "error",
  "error_code": "VALIDATION_ERROR",
  "message": "Invalid query parameters",
  "details": [
    {
      "loc": ["page"],
      "msg": "ensure this value is less than or equal to 10000",
      "type": "value_error.number.not_le"
    }
  ]
}
```

### Rate Limit Exceeded (429)

```json
{
  "status": "error",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded: 100 requests per 60s",
  "details": {
    "limit": 100,
    "window": 60,
    "current": 101,
    "retry_after": 45
  }
}
```

**Response Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704023400
```

---

## 🔧 새 모델 추가

### 1. models_extended.py에 정의

```python
from pydantic import BaseModel, Field
from typing import Optional

class MyQueryParams(BaseModel):
    """설명"""
    my_field: str = Field(max_length=100, description="필드 설명")
    my_number: int = Field(default=10, ge=1, le=100)

    @validator('my_field')
    def validate_my_field(cls, v):
        if not v.strip():
            raise ValueError('cannot be empty')
        return v.strip()
```

### 2. API에서 사용

```python
from app.api.models_extended import MyQueryParams
from app.utils.validation import validate_query_params

@api_bp.route('/my-endpoint', methods=['GET'])
@validate_query_params(MyQueryParams)
def my_endpoint(validated_params: MyQueryParams):
    field = validated_params.my_field
    number = validated_params.my_number
    # ...
```

---

## 💡 주요 패턴

### 데코레이터 체이닝

```python
@api_bp.route('/endpoint', methods=['POST'])
@rate_limit(limit=50, window=60)
@validate_request_body(MyRequest)
def my_endpoint(validated_data: MyRequest):
    # 순서: rate_limit → validation → endpoint
```

### Enum → 문자열 변환

```python
sentiment = validated_params.sentiment  # SentimentLabel enum
if sentiment:
    db_value = sentiment.value  # 'positive'
    opensearch_filter = {"term": {"sentiment.label": sentiment.value}}
```

### Date → ISO 문자열

```python
date_from = validated_params.date_from  # date object
if date_from:
    iso_string = date_from.isoformat()  # '2024-01-01'
```

### Optional 필드 처리

```python
# None 체크 필수
if validated_data.app_id:
    filters.append({"term": {"app_id": validated_data.app_id}})
```

---

## 🧪 테스트

### 단위 테스트

```python
from app.api.models_extended import ReviewQueryParams
from pydantic import ValidationError
import pytest

def test_page_validation():
    # 정상
    params = ReviewQueryParams(page=1)
    assert params.page == 1

    # 범위 초과
    with pytest.raises(ValidationError):
        ReviewQueryParams(page=99999)
```

### 통합 테스트 (Flask)

```python
def test_get_reviews_validation(client):
    # 정상 요청
    response = client.get('/api/v1/reviews?page=1&size=20')
    assert response.status_code == 200

    # 잘못된 파라미터
    response = client.get('/api/v1/reviews?page=99999')
    assert response.status_code == 400
    assert response.json['error_code'] == 'VALIDATION_ERROR'
```

---

## 🎓 Best Practices

### 1. 항상 검증 사용
```python
# ❌ 나쁜 예
page = int(request.args.get('page', 1))

# ✅ 좋은 예
@validate_query_params(ReviewQueryParams)
def endpoint(validated_params):
    page = validated_params.page
```

### 2. Enum 값 사용
```python
# ❌ 나쁜 예
sentiment = "positive"  # 오타 가능

# ✅ 좋은 예
from app.api.models_extended import SentimentLabel
sentiment = SentimentLabel.POSITIVE
```

### 3. Custom Validator 활용
```python
@validator('email')
def validate_email(cls, v):
    if '@' not in v:
        raise ValueError('invalid email')
    return v.lower()
```

### 4. 에러 메시지 명확하게
```python
@validator('content')
def validate_content(cls, v):
    if len(v) < 10:
        raise ValueError('content must be at least 10 characters')
    return v
```

---

## 🔍 문제 해결

### ImportError
```bash
# models_extended.py 경로 확인
ls -l app/api/models_extended.py

# Python path 확인
python -c "import sys; print(sys.path)"
```

### ValidationError 계속 발생
```python
# 디버깅: 어떤 필드가 문제인지 확인
try:
    params = ReviewQueryParams(**request.args)
except ValidationError as e:
    print(e.errors())  # 상세 에러 정보
```

### Rate Limiter 작동 안 함
```bash
# Redis 연결 확인
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# Rate limit 키 확인
redis-cli keys "api_rate_limit:*"
```

---

## 📚 참고

- Pydantic 공식 문서: https://docs.pydantic.dev/
- Session 2 완료 보고서: `docs/todo/SESSION_2_FINAL_REPORT.md`
- 원본 가이드: `docs/todo/critical/02_input_validation.md`

---

**모든 API 엔드포인트에 검증을 적용하여 안전하고 예측 가능한 시스템을 구축하세요!** ✅
