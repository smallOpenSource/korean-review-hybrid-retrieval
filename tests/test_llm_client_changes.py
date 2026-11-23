"""
tests/test_llm_client_changes.py

llm_client.py 수정 사항 단위 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
테스트 항목:
  [1] _is_reasoning_model() — reasoning 모델 감지 로직
  [2] generate() — temperature 조건부 제외 (reasoning 모델)
  [3] generate() — system prompt 삽입 (parse_json=True)
  [4] generate() — json_schema strict 모드 (스키마 제공 시)
  [5] generate() — json_object fallback (스키마 미제공 시)
"""

import asyncio
import json
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEP = "=" * 64
results = []


def check(name: str, ok: bool, msg: str = ""):
    mark = "✅ PASS" if ok else "❌ FAIL"
    print(f"  {mark}  {name}" + (f"\n         └─ {msg}" if msg else ""))
    results.append((name, ok, msg))


def section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ══════════════════════════════════════════════════════════════
# Mock 설정 — 실제 API 호출 없이 테스트
# ══════════════════════════════════════════════════════════════

@dataclass
class MockAzureSettings:
    azure_endpoint: str = "https://mock.openai.azure.com/"
    api_key: str = "mock-key"
    api_version: str = "2024-12-01-preview"
    deployment: str = "gpt-5-mini"
    timeout: int = 60
    rpm_limit: int = 200


@dataclass
class MockUsage:
    prompt_tokens: int = 100
    completion_tokens: int = 50


@dataclass
class MockChoice:
    class Message:
        content = '{"sentiment": "positive", "score": 4, "summary": "좋은 앱"}'
    message = Message()


@dataclass
class MockResponse:
    choices = [MockChoice()]
    usage = MockUsage()
    model = "gpt-5-mini"


# ══════════════════════════════════════════════════════════════
# [1] _is_reasoning_model() 테스트
# ══════════════════════════════════════════════════════════════

def test_is_temperature_unsupported():
    section("[1] _is_temperature_unsupported() — temperature 미지원 모델 감지")

    from app.agents.llm_client import AzureOpenAILLMClient

    client = AzureOpenAILLMClient.__new__(AzureOpenAILLMClient)

    # temperature 미지원 모델 (True)
    unsupported = ["o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini", "O4-mini", "O1", "gpt-5-mini", "gpt-5", "GPT-5-mini"]
    for model in unsupported:
        result = client._is_temperature_unsupported(model)
        check(f"unsupported: {model!r} → True", result, f"실제={result}")

    # temperature 지원 모델 (False)
    supported = ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]
    for model in supported:
        result = client._is_temperature_unsupported(model)
        check(f"supported: {model!r} → False", not result, f"실제={result}")


# ══════════════════════════════════════════════════════════════
# [2] temperature 조건부 제외 테스트
# ══════════════════════════════════════════════════════════════

def test_temperature_handling_gpt5():
    section("[2] generate() — temperature 조건부 제외")

    from app.agents.llm_client import AzureOpenAILLMClient

    captured_kwargs = {}

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return MockResponse()

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create

    client = AzureOpenAILLMClient.__new__(AzureOpenAILLMClient)
    client._settings = MockAzureSettings()
    client._client = mock_client

    # 2-1: gpt-4o → temperature 포함
    captured_kwargs.clear()
    asyncio.run(client.generate("test", model="gpt-4o", temperature=0.1, parse_json=False))
    has_temp = "temperature" in captured_kwargs
    check("2-1. gpt-4o → temperature 포함", has_temp, f"temperature={captured_kwargs.get('temperature')}")

    # 2-2: gpt-5-mini → temperature 제외
    captured_kwargs.clear()
    asyncio.run(client.generate("test", model="gpt-5-mini", temperature=0.1, parse_json=False))
    no_temp = "temperature" not in captured_kwargs
    check("2-2. gpt-5-mini → temperature 제외", no_temp, f"keys={list(captured_kwargs.keys())}")

    # 2-3: o1 → temperature 제외
    captured_kwargs.clear()
    asyncio.run(client.generate("test", model="o1", temperature=0.3, parse_json=False))
    no_temp = "temperature" not in captured_kwargs
    check("2-3. o1 → temperature 제외", no_temp, f"keys={list(captured_kwargs.keys())}")


# ══════════════════════════════════════════════════════════════
# [3] system prompt 삽입 테스트
# ══════════════════════════════════════════════════════════════

def test_system_prompt():
    section("[3] generate() — system prompt 삽입")

    from app.agents.llm_client import AzureOpenAILLMClient

    captured_kwargs = {}

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return MockResponse()

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create

    client = AzureOpenAILLMClient.__new__(AzureOpenAILLMClient)
    client._settings = MockAzureSettings()
    client._client = mock_client

    # 3-1: parse_json=True → system prompt 있음
    captured_kwargs.clear()
    asyncio.run(client.generate("test json", model="gpt-5-mini", parse_json=True))
    messages = captured_kwargs.get("messages", [])
    has_system = len(messages) >= 2 and messages[0]["role"] == "system"
    check(
        "3-1. parse_json=True → system prompt 삽입",
        has_system,
        f"messages[0].role={messages[0]['role'] if messages else 'N/A'}"
    )
    if has_system:
        check(
            "3-1. system prompt에 '한국어' 지시 포함",
            "Korean" in messages[0]["content"],
            f"content={messages[0]['content'][:60]}"
        )

    # 3-2: parse_json=False → system prompt 없음
    captured_kwargs.clear()
    asyncio.run(client.generate("test", model="gpt-5-mini", parse_json=False))
    messages = captured_kwargs.get("messages", [])
    no_system = len(messages) == 1 and messages[0]["role"] == "user"
    check(
        "3-2. parse_json=False → system prompt 없음",
        no_system,
        f"messages count={len(messages)}, roles={[m['role'] for m in messages]}"
    )


# ══════════════════════════════════════════════════════════════
# [4] json_schema strict 모드 테스트
# ══════════════════════════════════════════════════════════════

def test_json_schema_strict():
    section("[4] generate() — json_schema strict 모드")

    from app.agents.llm_client import AzureOpenAILLMClient

    captured_kwargs = {}

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return MockResponse()

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create

    client = AzureOpenAILLMClient.__new__(AzureOpenAILLMClient)
    client._settings = MockAzureSettings()
    client._client = mock_client

    test_schema = {
        "type": "object",
        "properties": {
            "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
            "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "summary": {"type": "string"},
        },
        "required": ["sentiment", "score", "summary"],
        "additionalProperties": False,
    }

    # 4-1: json_schema 제공 → json_schema strict 모드
    captured_kwargs.clear()
    asyncio.run(client.generate("test json", model="gpt-5-mini", parse_json=True, json_schema=test_schema))

    rf = captured_kwargs.get("response_format", {})
    is_schema_type = rf.get("type") == "json_schema"
    check("4-1. response_format.type == 'json_schema'", is_schema_type, f"실제={rf.get('type')}")

    js = rf.get("json_schema", {})
    is_strict = js.get("strict") is True
    check("4-2. json_schema.strict == True", is_strict, f"실제={js.get('strict')}")

    has_name = js.get("name") == "AnalysisResult"
    check("4-3. json_schema.name == 'AnalysisResult'", has_name, f"실제={js.get('name')}")

    schema_match = js.get("schema") == test_schema
    check("4-4. json_schema.schema 전달 확인", schema_match)


# ══════════════════════════════════════════════════════════════
# [5] json_object fallback 테스트
# ══════════════════════════════════════════════════════════════

def test_json_object_fallback():
    section("[5] generate() — json_object fallback (스키마 미제공)")

    from app.agents.llm_client import AzureOpenAILLMClient

    captured_kwargs = {}

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return MockResponse()

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create

    client = AzureOpenAILLMClient.__new__(AzureOpenAILLMClient)
    client._settings = MockAzureSettings()
    client._client = mock_client

    # 5-1: json_schema=None → json_object fallback
    captured_kwargs.clear()
    asyncio.run(client.generate("test json", model="gpt-5-mini", parse_json=True, json_schema=None))

    rf = captured_kwargs.get("response_format", {})
    is_json_object = rf.get("type") == "json_object"
    check("5-1. json_schema 미제공 → response_format.type == 'json_object'", is_json_object, f"실제={rf.get('type')}")


# ══════════════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════════════

def main():
    print(f"\n{SEP}")
    print("  llm_client.py 수정 사항 단위 테스트")
    print(SEP)

    try:
        test_is_temperature_unsupported()
        test_temperature_handling_gpt5()
        test_system_prompt()
        test_json_schema_strict()
        test_json_object_fallback()
    except Exception as e:
        import traceback
        print(f"\n  [FATAL] 예기치 않은 오류: {e}")
        traceback.print_exc()

    # 결과 요약
    section("결과 요약")
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    print(f"\n  총 {len(results)}개  ✅ {len(passed)}개 통과  ❌ {len(failed)}개 실패\n")

    if failed:
        print("  실패 항목:")
        for name, _, msg in failed:
            print(f"     • {name}")
            if msg:
                print(f"       └─ {msg}")

    if not failed:
        print(f"  ✅ 모든 테스트 통과")
    else:
        print(f"\n  ⚠️  {len(failed)}개 실패")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
