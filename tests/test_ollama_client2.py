"""
Test updated OllamaLLMClient using the actual LLM client from app.
Simulates what the analyze job does with proper system+user prompts.
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from scheduler.utils.database import get_db_session
from sqlalchemy import text
from app.agents.llm_client import OllamaLLMClient

async def test_ollama_with_system_prompt():
    """Test OllamaLLMClient with system + user prompts like the real analyze job"""
    
    # Fetch one review
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
        print(f"Content: {row_dict['content'][:100]}...")
        print("=" * 80)
    
    # Build proper prompt with system + user (like UnifiedAgent does)
    # System prompt per tech support recommendation
    system_prompt = """당신은 앱 리뷰 분석 전문가입니다.

**출력 규칙**:
1. 유효한 JSON만 출력
2. ASCII 따옴표만 사용 (한글 따옴표 '', "" 사용 금지)
3. 문자열 내 따옴표는 \\" 로 이스케이프
4. JSON 외 텍스트 절대 포함 금지"""
    
    user_prompt = f"""리뷰 분석:

앱: {row_dict['package_id']}
평점: {row_dict['score']}/5
내용: {row_dict['content']}

JSON 형식:
{{
  "result": {{
    "sentiment": {{"sentiment_label": "negative", "sentiment_score": 2, "emotions": ["불만"], "confidence": 0.9}},
    "category": {{"primary_category": "오류", "secondary_categories": [], "confidence": 0.95}},
    "complaint": {{"is_complaint": true, "complaint_type": "error_report", "urgency": 3, "severity": 4, "confidence": 0.9}},
    "confidence": 0.91
  }},
  "reasoning": {{"summary": "분석 요약"}}
}}

ASCII 문자로 유효한 JSON만 출력하세요."""
    
    # Combine as the prompt (OllamaLLMClient currently only takes single prompt)
    # In production, this should be handled by adding system role to messages
    full_prompt = f"[시스템]\n{system_prompt}\n\n[사용자]\n{user_prompt}"
    
    print(f"\n🤖 Testing OllamaLLMClient with system+user prompt...")
    print("-" * 80)
    
    client = OllamaLLMClient()
    
    try:
        response = await client.generate(
            prompt=full_prompt,
            model=os.getenv('OLLAMA_MODEL', 'qwen3:14b'),
            temperature=0.6,
            max_tokens=4096,
            parse_json=True
        )
        
        print(f"\n⏱️ Response time: {response.latency_ms / 1000:.1f}s")
        print(f"📊 Provider: {response.provider}")
        print(f"📊 Model: {response.model}")
        
        print("\n📤 RESPONSE CONTENT:")
        print("=" * 80)
        print(response.content[:2000])
        if len(response.content) > 2000:
            print(f"... (truncated)")
        print("=" * 80)
        
        if response.parsed_json:
            print("\n✅ JSON PARSING SUCCESS:")
            print(json.dumps(response.parsed_json, indent=2, ensure_ascii=False)[:1500])
            
            # Validate structure
            if 'result' in response.parsed_json:
                result = response.parsed_json['result']
                if 'sentiment' in result:
                    print(f"\n📊 Analysis Summary:")
                    print(f"   Sentiment: {result['sentiment'].get('sentiment_label')}")
                    print(f"   Score: {result['sentiment'].get('sentiment_score')}")
                    print(f"   Is Complaint: {result.get('complaint', {}).get('is_complaint')}")
                    print(f"   Confidence: {result.get('confidence')}")
        else:
            print("\n❌ JSON parsing failed (parsed_json is None)")
            print(f"   Content length: {len(response.content)}")
            
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        if client._session:
            await client._session.close()

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 OLLAMA CLIENT TEST WITH SYSTEM PROMPT")
    print("=" * 80)
    asyncio.run(test_ollama_with_system_prompt())
