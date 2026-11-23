"""
tests/azure_aoai_guide.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Azure AOAI 구조화 응답 — 개발자 권장 패턴 가이드
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[테스트 결과 기반 권장 조합]
  모델          엔드포인트   이유
  ──────────    ─────────   ─────────────────────────────────
  o4-mini       Chat ✅      medium/long 입력에서 최대 1.32x 빠름
  gpt-5-mini    Chat ✅      전 구간 빠름 + Responses long 토큰 +55% 과잉

[Pydantic 스키마 설계 원칙]
  1. extra="forbid"        → additionalProperties: false 자동 포함
  2. Literal[1,2,3,4,5]    → enum 스키마 (minimum/maximum은 Azure SO 미지원)
  3. field_validator        → 런타임 최종 방어선

실행:
    python tests/azure_aoai_guide.py
"""

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from openai import AzureOpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

# ──────────────────────────────────────────────────────────────
# [1] 환경 설정
# ──────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_loaded   = load_dotenv(_ENV_PATH, override=True)

_REQUIRED = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]
_OPTIONAL = ["AZURE_OPENAI_DEPLOYMENT_GPT5_MINI"]

SEP  = "=" * 64
SEP2 = "-" * 64


def _print_env():
    print(f"\n{SEP}")
    print(f"[ENV] .env 경로 : {_ENV_PATH}")
    print(f"[ENV] 로드 결과 : {'✅ 성공' if _loaded else '❌ 파일 없음'}")
    print(SEP)
    missing = []
    for var, required in [(v, True) for v in _REQUIRED] + [(v, False) for v in _OPTIONAL]:
        raw     = os.getenv(var)
        display = (raw[:8] + "..." if "KEY" in var else raw) if raw else (
            "❌ 미설정" if required else "⚠️  미설정 (선택)"
        )
        print(f"  {'[필수]' if required else '[선택]'} {var:<40} = {display}")
        if required and not raw:
            missing.append(var)
    print(f"{SEP}\n")
    return missing


_missing = _print_env()
if _missing:
    print(f"[FATAL] 누락된 필수 환경 변수: {_missing}", file=sys.stderr)
    sys.exit(1)

_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
_API_KEY  = os.environ["AZURE_OPENAI_API_KEY"]
_API_VER  = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

DEPLOYMENTS: dict[str, str | None] = {
    "o4-mini":   os.environ["AZURE_OPENAI_DEPLOYMENT"],
    "gpt-5-mini": os.environ.get("AZURE_OPENAI_DEPLOYMENT_GPT5_MINI"),
}

# ──────────────────────────────────────────────────────────────
# [2] Pydantic 모델 — 권장 설계 패턴
# ──────────────────────────────────────────────────────────────

class ReviewAnalysis(BaseModel, extra="forbid"):
    """
    ❶ extra="forbid"
         model_json_schema()에 additionalProperties: false 자동 포함
         → _fix_pydantic_schema() 같은 수동 패치 불필요

    ❷ score: Literal[1,2,3,4,5]
         enum: [1,2,3,4,5] 스키마 생성
         → Azure SO는 minimum/maximum 미지원(공식 문서 확인)
         → Field(ge=1,le=5)의 minimum/maximum은 API가 무시함
         → enum이 스키마 레벨에서 범위를 강제하는 유일한 수단

    ❸ field_validator
         스키마 레벨을 통과한 후 런타임 최종 검증
    """
    sentiment: Literal["positive", "negative", "neutral"]
    score: Annotated[
        Literal[1, 2, 3, 4, 5],
        Field(description="1(최저) ~ 5(최고) 점수"),
    ]
    summary: str

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary는 빈 문자열일 수 없습니다.")
        return v.strip()


# ──────────────────────────────────────────────────────────────
# [3] 권장 호출 함수
# ──────────────────────────────────────────────────────────────

# 시스템 프롬프트 — 언어 고정 + score 범위 명시
_SYSTEM_PROMPT = (
    "You are a review analyzer. "
    "Always respond in Korean. "
    "score 필드는 반드시 1(최저)에서 5(최고) 사이의 정수 중 하나로만 응답하세요."
)


def analyze_review(
    client:     AzureOpenAI,
    deployment: str,
    review:     str,
) -> ReviewAnalysis:
    """
    리뷰 텍스트 → ReviewAnalysis 반환

    왜 beta.parse() 대신 create()인가?
      beta.parse()는 ValidationError 발생 시 res 반환 전에 raise
      → usage(토큰) 캡처 불가
      create() + model_validate_json()은 usage를 먼저 확보한 후 파싱
      → 에러 발생 시에도 토큰 사용량 추적 가능
    """
    schema = ReviewAnalysis.model_json_schema()

    res = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": f"Analyze: {review}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name":   "ReviewAnalysis",
                "strict": True,
                "schema": schema,
            },
        },
    )

    # usage는 파싱 전에 확보 (ValidationError 이후에도 접근 가능)
    usage  = res.usage
    raw    = res.choices[0].message.content
    result = ReviewAnalysis.model_validate_json(raw)  # ValidationError 발생 가능

    return result, usage


# ──────────────────────────────────────────────────────────────
# [4] 가이드 실행 케이스
# ──────────────────────────────────────────────────────────────

CASES = {
    "normal":    "이 앱은 UI가 직관적이고 속도도 빠릅니다. 다만 가끔 알림이 늦게 옵니다.",
    "positive":  "완벽한 앱입니다! 모든 기능이 훌륭해요.",
    "negative":  "자꾸 앱이 꺼지고 배터리도 엄청 먹어요. 최악입니다.",
    "empty":     "",
    "multilang": "Great app! UI가 좋아요. Très bien. 素晴らしい。",
}


def _run_case(client: AzureOpenAI, deployment: str, model_name: str, case_name: str, review: str):
    print(f"\n  [{model_name} / {case_name}]")
    print(f"  입력: {review!r:.80}" if review else "  입력: (빈 문자열)")

    try:
        result, usage = analyze_review(client, deployment, review)
        in_tok  = usage.prompt_tokens     if usage else 0
        out_tok = usage.completion_tokens if usage else 0
        print(f"  ✅ sentiment={result.sentiment!r}  score={result.score}  tokens(in={in_tok}, out={out_tok})")
        print(f"     summary  ={result.summary!r}")

    except ValidationError as ve:
        # 스키마 설계 오류 또는 모델이 스키마를 위반한 경우
        # → Literal[1,2,3,4,5] 사용 시 score 범위 위반 불가 (enum 강제)
        # → 이 블록이 실행된다면 summary 공백 등 다른 필드 문제
        print(f"  ❌ [ValidationError] {ve}")

    except Exception as e:
        err_type = "content_filter" if "content_filter" in str(e) else "api_error"
        print(f"  ⚠️  [{err_type}] {str(e)[:120]}")


def _print_schema_guide():
    """스키마 설계 포인트 출력 — 개발자 참조용"""
    schema = ReviewAnalysis.model_json_schema()
    score_s     = schema["properties"]["score"]
    sentiment_s = schema["properties"]["sentiment"]

    print(f"\n{SEP}")
    print("  📐 스키마 설계 검증")
    print(SEP)
    print(f"  전체 스키마:\n{json.dumps(schema, ensure_ascii=False, indent=4)}")
    print()

    checks = [
        ("additionalProperties: false 포함",   schema.get("additionalProperties") is False),
        ("score — enum 사용 (minimum/maximum 아님)", "enum" in score_s and "minimum" not in score_s),
        ("score — enum 값: [1,2,3,4,5]",        score_s.get("enum") == [1, 2, 3, 4, 5]),
        ("sentiment — enum 사용",                "enum" in sentiment_s),
        ("required 필드 3개 포함",               set(schema.get("required", [])) == {"sentiment", "score", "summary"}),
    ]

    all_pass = True
    for desc, ok in checks:
        mark = "✅" if ok else "❌"
        print(f"  {mark}  {desc}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("  ✅ 스키마 설계 검증 완료 — 모든 항목 통과")
    else:
        print("  ❌ 스키마 설계 오류 — 위 항목을 확인하세요")
        sys.exit(1)

    print(SEP)


def _print_pattern_guide():
    """권장 패턴 요약 출력"""
    print(f"\n{SEP}")
    print("  📋 권장 패턴 요약 (벤치마크 테스트 결과 기반)")
    print(SEP)
    print("""
  모델          엔드포인트    이유
  ──────────    ─────────   ──────────────────────────────────────────
  o4-mini       Chat ✅       medium/long 입력에서 최대 1.32x 빠름
  gpt-5-mini    Chat ✅       전 구간 빠름 + Responses long 출력 토큰 +55% 과잉

  Pydantic 설계 원칙
  ─────────────────────────────────────────────────────────────────────
  extra="forbid"          additionalProperties: false 자동 포함
                          → _fix_pydantic_schema() 패치 불필요

  Literal[1,2,3,4,5]      enum: [1,2,3,4,5] 스키마 생성
                          → Azure SO에서 minimum/maximum 미지원 (공식 문서 확인)
                          → Field(ge=1, le=5) 사용 시 API가 minimum/maximum 무시
                          → enum이 스키마 레벨에서 범위를 강제하는 유일한 수단

  field_validator         스키마 레벨 이후 런타임 최종 방어
                          → score는 Literal이 보장하므로 summary 등 문자열 검증에 활용

  create() + validate     beta.parse() 대신 권장
                          → ValidationError 발생 시에도 usage(토큰) 캡처 보장
    """)
    print(SEP)


# ──────────────────────────────────────────────────────────────
# [5] 메인 실행
# ──────────────────────────────────────────────────────────────

def main():
    # 스키마 설계 검증
    _print_schema_guide()

    # 권장 패턴 요약
    _print_pattern_guide()

    # 클라이언트 생성
    client = AzureOpenAI(
        azure_endpoint=_ENDPOINT,
        api_key=_API_KEY,
        api_version=_API_VER,
    )

    # 모델별 케이스 실행
    for model_name, deployment in DEPLOYMENTS.items():
        if not deployment:
            print(f"\n  ⚠️  [{model_name}] 배포명 미설정 — 스킵")
            continue

        print(f"\n{SEP}")
        print(f"  🤖 모델: {model_name}  (deployment={deployment})")
        print(f"  🔗 엔드포인트: Chat Completions  ({_API_VER})")
        print(SEP)

        for case_name, review in CASES.items():
            _run_case(client, deployment, model_name, case_name, review)

    print(f"\n{SEP}")
    print("  ✅ 가이드 실행 완료")
    print(SEP + "\n")


if __name__ == "__main__":
    main()
