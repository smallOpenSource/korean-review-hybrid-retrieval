"""
Test Qwen3:14b with recommended settings from tech support.
Key changes: format='json', num_predict=4096, system prompt, Thinking mode params.
"""

import asyncio
import sys
import os
import re
import json
import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from scheduler.utils.database import get_db_session
from sqlalchemy import text

async def test_recommended_settings():
    """Test with tech support recommended settings"""
    
    # Fetch one unanalyzed review from MariaDB
    with get_db_session() as session:
        result = session.execute(text("""
            SELECT review_id, package_id, content, score, at
            FROM reviews 
            WHERE analyzed = 0 
            AND content IS NOT NULL 
            AND content != ''
            ORDER BY created_at DESC
            LIMIT 1
        """))
        row = result.fetchone()
        
        if not row:
            print("No unanalyzed reviews found")
            return
            
        row_dict = dict(row._mapping)
        print("=" * 80)
        print("📝 Test Review")
        print("=" * 80)
        print(f"Review ID: {row_dict['review_id']}")
        print(f"Package ID: {row_dict['package_id']}")
        print(f"Score: {row_dict['score']}")
        content_preview = row_dict['content'][:200] if len(row_dict['content']) > 200 else row_dict['content']
        print(f"Content: {content_preview}...")
        print("=" * 80)
    
    # Build prompt with explicit JSON examples (per recommendation)
    prompt = f"""다음 앱 리뷰를 분석하고 유효한 JSON 형식으로만 응답하세요.

[리뷰 정보]
앱: {row_dict['package_id']}
평점: {row_dict['score']}/5
내용: {row_dict['content']}

[JSON 형식 - 정확히 따라주세요]
{{
  "result": {{
    "sentiment": {{"sentiment_label": "very_negative", "sentiment_score": 1, "emotions": ["분노"], "confidence": 0.95}},
    "category": {{"primary_category": "오류", "secondary_categories": [], "confidence": 0.9}},
    "complaint": {{"is_complaint": true, "complaint_type": "error_report", "urgency": 3, "severity": 4, "confidence": 0.95}},
    "confidence": 0.93
  }},
  "reasoning": {{"summary": "분석 요약"}}
}}

JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."""

    # Settings from .env
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen3:14b')
    api_key = os.getenv('OLLAMA_API_KEY', '')
    timeout = int(os.getenv('OLLAMA_TIMEOUT', '900'))
    
    print(f"\n🤖 Testing with RECOMMENDED SETTINGS")
    print(f"   Model: {model}")
    print(f"   Base URL: {base_url}")
    print(f"   Timeout: {timeout}s")
    print("-" * 80)
    
    # RECOMMENDED PAYLOAD per tech support
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "당신은 앱 리뷰 분석 전문가입니다. 반드시 유효한 JSON으로만 응답하세요."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "format": "json",  # ← JSON 모드 활성화 (핵심!)
        "stream": False,
        "options": {
            "num_predict": 4096,      # ← 2048 → 4096 (핵심!)
            "temperature": 0.6,       # Thinking mode 권장
            "top_p": 0.95,            # 안정적인 샘플링
            "top_k": 20,              # Qwen3 Thinking 최적값
            "repeat_penalty": 1.1,    # 반복 방지
            "num_ctx": 8192           # 컨텍스트 윈도우 확보
        }
    }
    
    print(f"\n📋 Payload options:")
    print(f"   format: 'json'")
    print(f"   num_predict: {payload['options']['num_predict']}")
    print(f"   temperature: {payload['options']['temperature']}")
    print(f"   top_p: {payload['options']['top_p']}")
    print(f"   top_k: {payload['options']['top_k']}")
    print(f"   num_ctx: {payload['options']['num_ctx']}")
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/api/chat",  # Native API
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                data = await response.json()
                
        elapsed = asyncio.get_event_loop().time() - start_time
        
        print(f"\n⏱️ Response time: {elapsed:.1f}s")
        
        # Extract content
        if 'message' in data and 'content' in data['message']:
            content = data['message']['content']
        else:
            print(f"Unexpected response structure: {json.dumps(data, indent=2)[:500]}")
            return
            
        print("\n📤 RAW RESPONSE:")
        print("=" * 80)
        print(content[:3000])
        if len(content) > 3000:
            print(f"... (truncated, total {len(content)} chars)")
        print("=" * 80)
        
        # Check for think tags (should be removed by format: "json")
        has_think_tags = '<think>' in content or '</think>' in content
        print(f"\n📊 Think tags present: {'❌ YES (unexpected!)' if has_think_tags else '✅ NO (as expected)'}")
        
        # Post-process (safety net)
        clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        clean_content = clean_content.strip('`').strip()
        if clean_content.startswith('json'):
            clean_content = clean_content[4:].strip()
        
        # Try JSON parsing
        try:
            parsed = json.loads(clean_content)
            print("\n✅ JSON PARSING SUCCESS!")
            print(json.dumps(parsed, indent=2, ensure_ascii=False)[:2000])
            
            # Validate structure
            if 'result' in parsed:
                result = parsed['result']
                if 'sentiment' in result:
                    print(f"\n📊 Analysis Summary:")
                    print(f"   Sentiment: {result['sentiment'].get('sentiment_label')}")
                    print(f"   Score: {result['sentiment'].get('sentiment_score')}")
                    print(f"   Is Complaint: {result.get('complaint', {}).get('is_complaint')}")
                    print(f"   Confidence: {result.get('confidence')}")
                    
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON PARSING FAILED: {e}")
            print(f"   Clean content: {clean_content[:500]}")
            
    except asyncio.TimeoutError:
        print(f"\n❌ Request timed out after {timeout}s")
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 QWEN3 RECOMMENDED SETTINGS TEST")
    print("=" * 80)
    asyncio.run(test_recommended_settings())
