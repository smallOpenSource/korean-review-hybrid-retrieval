import asyncio
import logging
import os
from dotenv import load_dotenv
from app.agents.llm_client import get_llm_client, LLMProvider

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_fallback():
    load_dotenv(override=True)
    print("Testing UnifiedLLMClient Fallback Logic...")
    
    client = get_llm_client()
    
    print("\n1. Checking Available Providers:")
    providers = client._get_available_providers()
    print(f"Available providers: {[p.value for p in providers]}")
    
    print("\n2. Testing Generation:")
    try:
        response = await client.generate(
            prompt="Hello, are you working?",
            task_type="sentiment_analysis",
            parse_json=False
        )
        print(f"\nSuccess!")
        print(f"Provider: {response.provider}")
        print(f"Model: {response.model}")
        print(f"Content: {response.content}")
        print(f"Is Fallback: {response.is_fallback}")
    except Exception as e:
        print(f"\nGeneration Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_fallback())
