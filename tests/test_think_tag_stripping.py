
import sys
import os
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from app.agents.llm_client import BaseLLMClient, LLMResponse, EmbeddingResponse

class TestLLMClient(BaseLLMClient):
    def is_available(self) -> bool:
        return True
    async def generate(self, *args, **kwargs) -> LLMResponse:
        pass
    async def embed(self, *args, **kwargs) -> EmbeddingResponse:
        pass

def test_think_tag_stripping():
    client = TestLLMClient()
    
    # Case 1: Simple think tag
    content = """<think>
    This is some reasoning.
    </think>
    {
        "sentiment": "positive"
    }"""
    
    result = client._try_parse_json(content)
    assert result == {"sentiment": "positive"}, f"Failed Case 1: {result}"
    print("Case 1 Passed")

    # Case 2: Inline think tag
    content = """<think>Reasoning</think> {"sentiment": "negative"}"""
    result = client._try_parse_json(content)
    assert result == {"sentiment": "negative"}, f"Failed Case 2: {result}"
    print("Case 2 Passed")

    # Case 3: Think tag with code block
    content = """<think>
    Reasoning...
    </think>
    ```json
    {
        "sentiment": "neutral"
    }
    ```"""
    result = client._try_parse_json(content)
    assert result == {"sentiment": "neutral"}, f"Failed Case 3: {result}"
    print("Case 3 Passed")

    # Case 4: Multiple think tags (though unlikely, good to test regex)
    content = """<think>R1</think><think>R2</think>{"key": "value"}"""
    result = client._try_parse_json(content)
    assert result == {"key": "value"}, f"Failed Case 4: {result}"
    print("Case 4 Passed")

if __name__ == "__main__":
    try:
        test_think_tag_stripping()
        print("All tests passed!")
    except AssertionError as e:
        print(f"Test Failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
