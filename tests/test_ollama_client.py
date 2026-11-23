#!/usr/bin/env python3
"""
Test Ollama LLM Client after timeout fix.
"""
import os
import asyncio
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.llm_client import get_llm_client

async def test_ollama_analyze():
    """Test Ollama client with analyze use case."""
    client = get_llm_client()
    
    # Test prompt similar to analyze job
    prompt = """Analyze the following review and extract sentiment, emotions, and complaints:

Review: "(가상 예시) 앱 접속이 자꾸 안 돼서 불편해요."

Return JSON format:
{
    "sentiment": "positive/negative/neutral",
    "emotions": ["emotion1", "emotion2"],
    "has_complaint": true/false,
    "complaint_category": "category or null"
}"""
    
    print("=== Testing Ollama LLM Client ===")
    print(f"Prompt: {prompt[:100]}...")
    
    try:
        response = await client.generate(
            prompt=prompt,
            task_type='realtime',  # Uses realtime model config
            parse_json=True
        )
        
        print(f"\n✓ Success!")
        print(f"Provider: {response.provider}")
        print(f"Model: {response.model}")
        print(f"Latency: {response.latency_ms}ms")
        print(f"Content: {response.content}")
        if response.parsed_json:
            print(f"Parsed JSON: {response.parsed_json}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_ollama_analyze())
    sys.exit(0 if success else 1)
