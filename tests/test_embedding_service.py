"""
Test embedding service with new Ollama configuration.
"""

import asyncio
import os

# Set environment variables for testing

os.environ.setdefault('BGE_EMBEDDING_API_URL', 'http://localhost:8000/embeddings')
os.environ.setdefault('BGE_EMBEDDING_API_KEY', '')
os.environ['BGE_EMBEDDING_MODEL'] = 'BAAI/bge-m3'


# Must import after setting env vars
from app.agents.embedding_service import BGEAPIClient


async def test_embedding():
    """Test the embedding API client."""
    print("="*60)
    print("EMBEDDING SERVICE TEST")
    print("="*60)
    
    client = BGEAPIClient()
    
    # Check availability
    print(f"API Available: {client.is_available()}")
    
    if not client.is_available():
        print("❌ Embedding API not configured")
        return
    
    # Test single embedding
    print("\n--- Single Embedding Test ---")
    try:
        result = await client.embed("테스트 문장입니다. 앱이 자주 멈춰요.")
        print(f"✅ Success!")
        print(f"   Model: {result.model}")
        print(f"   Source: {result.source}")
        print(f"   Dimensions: {result.dimensions}")
        print(f"   Latency: {result.latency_ms}ms")
        print(f"   First 5 values: {result.embedding[:5]}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    # Test batch embedding
    print("\n--- Batch Embedding Test ---")
    try:
        texts = ["앱이 느려요", "로그인이 안됩니다", "앱이 자꾸 종료됩니다"]
        results = await client.embed_batch(texts)
        print(f"✅ Success! Got {len(results)} embeddings")
        for i, r in enumerate(results):
            print(f"   [{i}] Dimensions: {r.dimensions}, Latency: {r.latency_ms}ms")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    await client.close()


if __name__ == "__main__":
    asyncio.run(test_embedding())
