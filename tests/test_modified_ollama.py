"""
Test modified OllamaLLMClient - comparing with/without format parameter.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from scheduler.utils.database import get_db_session
from sqlalchemy import text
from app.agents.llm_client import OllamaLLMClient
import json

async def test_without_format():
    """Test without parse_json (no format parameter)"""
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
    
    prompt = f"""다음 앱 리뷰를 분석하고 JSON 형식으로 응답하세요.

[리뷰 정보]
앱: {row_dict['package_id']}
평점: {row_dict['score']}/5
내용: {row_dict['content']}

다음 JSON 형식으로만 응답하세요:
{{
  "sentiment_label": "very_negative/negative/neutral/positive/very_positive 중 하나",
  "sentiment_score": 1부터 5 사이의 정수,
  "is_complaint": true 또는 false,
  "complaint_type": "general_review/improvement_request/dissatisfaction/error_report 중 하나",
  "primary_category": "카테고리명",
  "confidence": 0.0부터 1.0 사이의 소수,
  "summary": "분석 요약 문자열"
}}

위 형식의 JSON만 출력하고, 다른 텍스트는 절대 포함하지 마세요."""

    client = OllamaLLMClient()
    
    print("\n🤖 Test 1: parse_json=False (no format parameter)...")
    print("-" * 80)
    
    try:
        response = await client.generate(
            prompt=prompt,
            model=os.getenv('OLLAMA_MODEL', 'qwen3:14b'),
            temperature=0.6,
            max_tokens=2048,
            parse_json=False  # No format parameter
        )
        
        print(f"\n⏱️ Response time: {response.latency_ms / 1000:.1f}s")
        
        print("\n📤 RAW RESPONSE:")
        print("=" * 80)
        print(response.content[:3000])
        print("=" * 80)
        
        # Try manual JSON parsing
        try:
            # Try to extract JSON from response
            import re
            clean_content = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
            
            # Find JSON in content
            start = clean_content.find('{')
            if start != -1:
                end = clean_content.rfind('}') + 1
                json_str = clean_content[start:end]
                parsed = json.loads(json_str)
                print("\n✅ MANUAL JSON PARSING SUCCESS:")
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
            else:
                print("\n❌ No JSON object found in response")
        except Exception as e:
            print(f"\n❌ Manual JSON parsing failed: {e}")
            
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        if client._session:
            await client._session.close()

if __name__ == "__main__":
    asyncio.run(test_without_format())
