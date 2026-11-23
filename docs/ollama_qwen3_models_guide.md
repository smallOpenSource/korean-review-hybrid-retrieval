Qwen3의 추론 내용과 최종 답변을 분리하여 파싱하는 방법을 Ollama 환경에서 단계별로 설명하겠습니다.[1][2]

## 개념 설명

Qwen3는 Thinking Mode에서 `<think>추론 과정</think>최종 답변` 형태로 응답을 생성합니다. 이 두 부분을 분리하면:[3][2]
- **Thinking Content**: 모델의 단계별 추론 과정 (품질 향상에 기여)
- **Final Content**: 사용자에게 제공할 최종 답변

분리 후 필요에 따라 재조합하거나 최종 답변만 사용할 수 있습니다.[2][1]

## 방법 1: Ollama Python 라이브러리 사용 (권장)

Ollama 0.5.1 이상 버전에서는 `thinking` 속성을 통해 자동으로 분리된 내용을 제공합니다:[1]

```python
from ollama import chat

messages = [
    {
        'role': 'system',
        'content': '당신은 수학 문제를 해결하는 전문가입니다.'
    },
    {
        'role': 'user',
        'content': 'strawberry라는 단어에 r이 몇 개 있나요?'
    }
]

# Thinking mode 활성화 (기본값)
response = chat(
    model='qwen3:14b',
    messages=messages,
    think=True,  # 명시적으로 활성화
    options={
        'temperature': 0.6,  # Thinking mode 권장 파라미터
        'top_p': 0.95,
        'top_k': 20
    }
)

# 추론 과정과 최종 답변 분리
thinking_content = response.message.thinking if hasattr(response.message, 'thinking') else ""
final_content = response.message.content

print("=== 추론 과정 ===")
print(thinking_content)
print("\n=== 최종 답변 ===")
print(final_content)
```

**예상 출력**:
```
=== 추론 과정 ===
먼저 'strawberry'를 철자별로 분석해보겠습니다.
s-t-r-a-w-b-e-r-r-y
r이 나타나는 위치를 확인하면: 3번째, 8번째, 9번째
따라서 총 3개의 r이 있습니다.

=== 최종 답변 ===
'strawberry'에는 r이 3개 있습니다.
```

## 방법 2: 정규식을 이용한 수동 파싱

Ollama 버전이 낮거나 `thinking` 속성이 지원되지 않는 경우:[4][5]

```python
from ollama import chat
import re

messages = [
    {
        'role': 'user',
        'content': '127 곱하기 83은 얼마인가요?'
    }
]

response = chat(
    model='qwen3:14b',
    messages=messages
)

# 전체 응답에서 think 태그 파싱
full_response = response['message']['content']

# <think>...</think> 블록 추출
think_pattern = r'<think>(.*?)</think>'
think_match = re.search(think_pattern, full_response, re.DOTALL)

if think_match:
    thinking_content = think_match.group(1).strip()
    # think 태그 제거 후 최종 답변 추출
    final_content = re.sub(think_pattern, '', full_response, flags=re.DOTALL).strip()
else:
    thinking_content = ""
    final_content = full_response

print("=== 추론 과정 ===")
print(thinking_content)
print("\n=== 최종 답변 ===")
print(final_content)
```

## 방법 3: Pydantic과 통합 (JSON 출력용)

구조화된 JSON 출력이 필요한 경우:[5][6]

```python
from ollama import chat
from pydantic import BaseModel, Field
import re
import json

# Pydantic 스키마 정의
class MathSolution(BaseModel):
    problem: str = Field(description="수학 문제")
    answer: int = Field(description="계산 결과")
    steps: list[str] = Field(description="풀이 단계")

messages = [
    {
        'role': 'system',
        'content': 'JSON 형식으로 수학 문제의 답과 풀이 과정을 제공하세요.'
    },
    {
        'role': 'user',
        'content': '45 * 67의 값을 계산하고, 풀이 과정을 단계별로 설명해주세요.'
    }
]

# 1. Qwen3로 응답 생성
response = chat(
    model='qwen3:14b',
    messages=messages,
    format=MathSolution.model_json_schema(),  # JSON 스키마 전달
    options={'temperature': 0.6, 'top_p': 0.95}
)

# 2. Think 태그 제거
raw_content = response['message']['content']
clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()

# 3. Pydantic으로 검증 및 파싱
try:
    solution = MathSolution.model_validate_json(clean_content)
    print("=== 파싱 성공 ===")
    print(f"문제: {solution.problem}")
    print(f"답: {solution.answer}")
    print(f"풀이 단계:")
    for i, step in enumerate(solution.steps, 1):
        print(f"  {i}. {step}")
except Exception as e:
    print(f"파싱 오류: {e}")
    print(f"원본 응답: {clean_content}")
```

**예상 출력**:
```
=== 파싱 성공 ===
문제: 45 * 67
답: 3015
풀이 단계:
  1. 45를 40 + 5로 분해
  2. 40 * 67 = 2680
  3. 5 * 67 = 335
  4. 2680 + 335 = 3015
```

## 방법 4: 추론+답변 통합 (하이브리드)

추론 과정을 최종 답변에 자연스럽게 포함:[3]

```python
from ollama import chat

messages = [
    {
        'role': 'user',
        'content': '복잡한 논리 문제를 풀어주세요: 5명이 악수하면 총 몇 번 악수할까요?'
    }
]

response = chat(model='qwen3:14b', messages=messages)

# Think 태그 파싱
full_response = response['message']['content']
think_match = re.search(r'<think>(.*?)</think>(.*)', full_response, re.DOTALL)

if think_match:
    thinking = think_match.group(1).strip()
    answer = think_match.group(2).strip()
    
    # 추론 과정을 답변에 통합하여 재구성
    integrated_response = f"""
**풀이 과정**
{thinking}

**결론**
{answer}
"""
    print(integrated_response)
else:
    print(full_response)
```

**예상 출력**:
```
**풀이 과정**
각 사람이 다른 4명과 악수합니다.
5명 × 4번 = 20번
하지만 A가 B와 악수하는 것과 B가 A와 악수하는 것은 같은 악수이므로 중복을 제거해야 합니다.
20 ÷ 2 = 10번

**결론**
5명이 서로 악수하면 총 10번의 악수가 발생합니다.
```

## 실전 팁

| 시나리오 | 권장 방법 |
|---------|---------|
| Ollama 최신 버전 사용 | 방법 1 (thinking 속성 활용)[1] |
| 구버전 또는 호환성 고려 | 방법 2 (정규식 파싱)[5] |
| JSON API 응답 필요 | 방법 3 (Pydantic 통합)[6] |
| 사용자에게 상세 설명 제공 | 방법 4 (하이브리드 통합)[3] |
| 최종 답변만 필요 | think 태그 제거 후 final_content만 사용[2] |

모든 방법에서 Thinking Mode의 고품질 추론을 유지하면서 원하는 형태로 출력을 가공할 수 있습니다.[7][2][3]

[1](https://ollama.com/blog/thinking)
[2](https://github.com/QwenLM/Qwen3)
[3](https://qwenlm.github.io/blog/qwen3/)
[4](https://github.com/ollama/ollama-python/issues/529)
[5](https://www.reddit.com/r/LocalLLaMA/comments/1kffed0/qwen3_include_thinking_while_outputing_json_only/)
[6](https://docs.ollama.com/capabilities/structured-outputs)
[7](https://huggingface.co/Qwen/Qwen3-8B)
[8](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html)
[9](https://www.datacamp.com/fr/tutorial/qwen3-max-thinking)
[10](https://github.com/home-assistant/core/issues/140003)
[11](https://www.reddit.com/r/ollama/comments/1ka8s9s/how_to_disable_thinking_with_qwen3/)