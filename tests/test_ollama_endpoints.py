import os
"""
Ollama Server Endpoint Discovery Test.
Tests various endpoints to find working embedding and rerank APIs.
"""

import requests
import json

# Ollama Server Configuration
BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
API_KEY = os.environ.get("OLLAMA_API_KEY", "")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# Test data
TEST_TEXT = "테스트 문장입니다."
TEST_QUERY = "앱이 자주 멈춰요"
TEST_DOCS = ["앱이 느려요", "로그인이 안됩니다", "앱이 자꾸 종료됩니다"]


def test_endpoint(url: str, payload: dict, description: str) -> dict:
    """Test a single endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)[:200]}...")
    
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            print(f"SUCCESS ✅")
            return {"success": True, "data": data, "url": url}
        else:
            print(f"Response: {response.text[:500]}")
            print(f"FAILED ❌")
            return {"success": False, "status": response.status_code, "error": response.text}
            
    except Exception as e:
        print(f"Error: {e}")
        print(f"FAILED ❌")
        return {"success": False, "error": str(e)}


def discover_endpoints():
    """Try various endpoint patterns to find working APIs."""
    
    print("\n" + "="*60)
    print("EMBEDDING ENDPOINT DISCOVERY")
    print("="*60)
    
    # Embedding endpoint candidates
    embedding_endpoints = [
        (f"{BASE_URL}/embeddings", {"texts": [TEST_TEXT], "model": "bge-m3:latest"}),
        (f"{BASE_URL}/embeddings", {"input": TEST_TEXT, "model": "bge-m3:latest"}),
        (f"{BASE_URL}/v1/embeddings", {"input": TEST_TEXT, "model": "bge-m3:latest"}),
        (f"{BASE_URL}/v1/embeddings", {"input": [TEST_TEXT], "model": "bge-m3:latest"}),
        (f"{BASE_URL}/api/embeddings", {"prompt": TEST_TEXT, "model": "bge-m3:latest"}),
        (f"{BASE_URL}/api/embed", {"input": TEST_TEXT, "model": "bge-m3:latest"}),
    ]
    
    embedding_result = None
    for url, payload in embedding_endpoints:
        result = test_endpoint(url, payload, f"Embedding: {url}")
        if result.get("success"):
            embedding_result = result
            break
    
    print("\n" + "="*60)
    print("RERANK ENDPOINT DISCOVERY")
    print("="*60)
    
    # Rerank endpoint candidates
    rerank_endpoints = [
        (f"{BASE_URL}/rerank", {"query": TEST_QUERY, "documents": TEST_DOCS, "model": "xitao/bge-reranker-v2-m3:latest"}),
        (f"{BASE_URL}/v1/rerank", {"query": TEST_QUERY, "documents": TEST_DOCS, "model": "xitao/bge-reranker-v2-m3:latest"}),
        (f"{BASE_URL}/api/rerank", {"query": TEST_QUERY, "documents": TEST_DOCS, "model": "xitao/bge-reranker-v2-m3:latest"}),
        (f"{BASE_URL}/v1/rerank", {"query": TEST_QUERY, "passages": TEST_DOCS, "model": "xitao/bge-reranker-v2-m3:latest"}),
    ]
    
    rerank_result = None
    for url, payload in rerank_endpoints:
        result = test_endpoint(url, payload, f"Rerank: {url}")
        if result.get("success"):
            rerank_result = result
            break
    
    # Summary
    print("\n" + "="*60)
    print("DISCOVERY SUMMARY")
    print("="*60)
    
    if embedding_result:
        print(f"✅ Embedding endpoint found: {embedding_result['url']}")
        print(f"   Response structure: {list(embedding_result['data'].keys())}")
    else:
        print("❌ No working embedding endpoint found")
    
    if rerank_result:
        print(f"✅ Rerank endpoint found: {rerank_result['url']}")
        print(f"   Response structure: {list(rerank_result['data'].keys())}")
    else:
        print("❌ No working rerank endpoint found")
    
    return embedding_result, rerank_result


def test_models_list():
    """Check available models on the server."""
    print("\n" + "="*60)
    print("AVAILABLE MODELS")
    print("="*60)
    
    try:
        # Try /api/tags (Ollama native)
        response = requests.get(f"{BASE_URL}/api/tags", headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            print(f"Found {len(models)} models:")
            for m in models[:20]:  # Limit to 20
                print(f"  - {m.get('name', m)}")
            return
    except:
        pass
    
    try:
        # Try /v1/models (OpenAI compatible)
        response = requests.get(f"{BASE_URL}/v1/models", headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            print(f"Found {len(models)} models:")
            for m in models[:20]:
                print(f"  - {m.get('id', m)}")
            return
    except:
        pass
    
    print("Could not retrieve model list")


if __name__ == "__main__":
    # First check available models
    test_models_list()
    
    # Then discover endpoints
    discover_endpoints()
