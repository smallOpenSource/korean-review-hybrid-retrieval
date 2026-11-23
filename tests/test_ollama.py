import os
import requests
import json

# Ollama 설정

# 레거시
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_MODEL = "gpt-oss:20b"
OLLAMA_EMBEDDING_MODEL = "bge-m3:latest"


# 미니PC로 진행.
#OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
#OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
#OLLAMA_MODEL = "qwen/qwen3-8b"
#OLLAMA_EMBEDDING_MODEL = "text-embedding-bge-m3"


# 공통 헤더 설정
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {OLLAMA_API_KEY}"
}

# 1. 채팅 테스트 (OpenAI 호환 API)
def test_chat():
    print("=== 채팅 테스트 (OpenAI 호환) ===")
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": "안녕하세요. 간단한 자기소개 부탁드립니다."}
        ],
        "stream": False
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        print(f"상태 코드: {response.status_code}")
        response.raise_for_status()
        
        result = response.json()
        print(f"답변: {result['choices'][0]['message']['content']}")
        print()
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        if 'response' in locals():
            print(f"응답: {response.text}")

# 2. 스트리밍 채팅 테스트
def test_streaming_chat():
    print("=== 스트리밍 채팅 테스트 ===")
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": "1부터 5까지 세어주세요."}
        ],
        "stream": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            if 'content' in delta:
                                print(delta['content'], end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        print("\n")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

# 3. 임베딩 테스트 (OpenAI 호환)
def test_embedding():
    print("=== 임베딩 테스트 (OpenAI 호환) ===")
    url = f"{OLLAMA_BASE_URL}/v1/embeddings"
    
    payload = {
        "model": OLLAMA_EMBEDDING_MODEL,
        "input": "이것은 임베딩 테스트 문장입니다."
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        print(f"상태 코드: {response.status_code}")
        response.raise_for_status()
        
        result = response.json()
        embedding = result['data'][0]['embedding']
        print(f"임베딩 차원: {len(embedding)}")
        print(f"임베딩 벡터 샘플 (처음 5개): {embedding[:5]}")
        print()
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        if 'response' in locals():
            print(f"응답: {response.text}")

# OpenAI 라이브러리 사용 예제 (선택사항)
def test_with_openai_library():
    print("=== OpenAI 라이브러리 사용 예제 ===")
    try:
        from openai import OpenAI
        
        client = OpenAI(
            base_url=f"{OLLAMA_BASE_URL}/v1",
            api_key=OLLAMA_API_KEY
        )
        
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "user", "content": "Python이란 무엇인가요?"}
            ]
        )
        
        print(response.choices[0].message.content)
        print()
        
    except ImportError:
        print("OpenAI 라이브러리가 설치되지 않았습니다. pip install openai")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

# 실행
if __name__ == "__main__":
    test_chat()
    # test_streaming_chat()  # 스트리밍이 필요하면 주석 해제
    test_embedding()
    # test_with_openai_library()  # OpenAI 라이브러리 테스트
    print("✅ 테스트 완료!")
