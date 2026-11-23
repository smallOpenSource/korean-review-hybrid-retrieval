# Azure AOAI 구조화 응답 개발 가이드

## 권장 조합

| 모델 | 엔드포인트 | API Version | 이유 |
|---|:---:|:---:|---|
| o4-mini | Chat Completions | `2024-12-01-preview` | medium/long 입력 최대 1.32x 빠름 |
| gpt-5-mini | Chat Completions | `2024-12-01-preview` | 전 구간 빠름 + Responses long 토큰 +55% 과잉 |

***

## Pydantic 모델 설계

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field, field_validator

class ReviewAnalysis(BaseModel, extra="forbid"):        # ❶
    sentiment: Literal["positive", "negative", "neutral"]
    score: Annotated[
        Literal[1, 2, 3, 4, 5],                        # ❷
        Field(description="1(최저) ~ 5(최고) 점수"),
    ]
    summary: str

    @field_validator("summary")                         # ❸
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary는 빈 문자열일 수 없습니다.")
        return v.strip()
```

| # | 설정 | 이유 |
|:---:|---|---|
| ❶ | `extra="forbid"` | `additionalProperties: false` 자동 포함 → 수동 스키마 패치 불필요 |
| ❷ | `Literal[1,2,3,4,5]` | `enum: [1,2,3,4,5]` 스키마 생성 → **Azure SO는 `minimum`/`maximum` 미지원**, `enum`이 유일한 범위 강제 수단 |
| ❸ | `field_validator` | 스키마 통과 후 런타임 최종 방어 → `score`는 `Literal`이 보장하므로 문자열 필드 검증에 집중 |

***

## API 호출 패턴

```python
from openai import AzureOpenAI
from pydantic import ValidationError

SYSTEM_PROMPT = (
    "You are a review analyzer. "
    "Always respond in Korean. "
    "score 필드는 반드시 1(최저)에서 5(최고) 사이의 정수 중 하나로만 응답하세요."
)

def analyze_review(client: AzureOpenAI, deployment: str, review: str) -> ReviewAnalysis:
    res = client.chat.completions.create(   # ❹
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Analyze: {review}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name":   "ReviewAnalysis",
                "strict": True,
                "schema": ReviewAnalysis.model_json_schema(),
            },
        },
    )
    # ❺ usage 먼저 캡처 → ValidationError 발생 후에도 토큰 추적 가능
    usage = res.usage
    raw   = res.choices[0].message.content
    return ReviewAnalysis.model_validate_json(raw), usage   # ❻
```

| # | 설정 | 이유 |
|:---:|---|---|
| ❹ | `create()` | `beta.parse()` 대신 사용 → `beta.parse()`는 `ValidationError` 시 `res` 반환 전 raise → `usage` 캡처 불가 |
| ❺ | `usage` 선취 | 파싱 전 토큰 확보 → 에러 발생 시에도 비용 추적 가능 |
| ❻ | `model_validate_json()` | Pydantic 런타임 검증 → `field_validator` 까지 실행 |

***

## 에러 처리

```python
try:
    result, usage = analyze_review(client, deployment, review)

except ValidationError as ve:
    # 스키마 위반 (summary 공백 등)
    # score는 Literal 강제로 이 블록에 도달하지 않음
    logger.error(f"[ValidationError] {ve}")

except Exception as e:
    if "content_filter" in str(e):
        # gpt-5-mini: jailbreak 시도 Azure 콘텐츠 필터 차단 (정상 동작)
        logger.warning(f"[ContentFilter] 입력 필터링됨")
    else:
        logger.error(f"[APIError] {e}")
```

***

## 생성 스키마 확인

실제 전송되는 스키마는 아래와 같습니다. `strict: True`와 함께 사용 시 모델은 이 구조만 반환합니다.

```json
{
  "additionalProperties": false,
  "properties": {
    "sentiment": { "enum": ["positive", "negative", "neutral"], "type": "string" },
    "score":     { "enum": [1, 2, 3, 4, 5], "type": "integer", "description": "1(최저) ~ 5(최고) 점수" },
    "summary":   { "type": "string" }
  },
  "required": ["sentiment", "score", "summary"],
  "type": "object"
}
```

***

## 금지 패턴

| ❌ 하지 말 것 | ✅ 대신 |
|---|---|
| `score: int` + `Field(ge=1, le=5)` | `score: Literal[1,2,3,4,5]` — `minimum`/`maximum` Azure SO 미지원 |
| `beta.parse()` | `create()` + `model_validate_json()` — usage 캡처 보장 |
| `_fix_pydantic_schema()` 수동 패치 | `extra="forbid"` — `additionalProperties: false` 자동 포함 |
| Responses API (gpt-5-mini) | Chat Completions — long 입력 토큰 +55% 과잉 실측 확인 |
| Responses API without `instructions=` | `instructions=SYSTEM_PROMPT` 필수 — 미지정 시 o4-mini 영어 응답 |