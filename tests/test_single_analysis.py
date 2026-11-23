"""
Test single review analysis with Qwen3:14b.
Uses Ollama NATIVE API (/api/chat) with format parameter.
Based on updated guidance: Native API uses 'format', OpenAI API uses 'response_format'.
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
from pydantic import BaseModel, Field
from typing import List, Optional

# Define Pydantic schema for expected response
class SentimentResult(BaseModel):
    sentiment_label: str = Field(description="very_negative/negative/neutral/positive/very_positive")
    sentiment_score: int = Field(description="Score 1-5")
    emotions: List[str] = Field(default_factory=list)
    confidence: float = Field(description="0.0-1.0")

class CategoryResult(BaseModel):
    primary_category: str
    secondary_categories: List[str] = Field(default_factory=list)
    confidence: float

class ComplaintResult(BaseModel):
    is_complaint: bool
    complaint_type: str
    urgency: int = Field(description="1-4")
    severity: int = Field(description="1-5")
    confidence: float

class ReasoningSummary(BaseModel):
    summary: str

class AnalysisResult(BaseModel):
    sentiment: SentimentResult
    category: CategoryResult
    complaint: ComplaintResult
    confidence: float

class ReviewAnalysisResponse(BaseModel):
    result: AnalysisResult
    reasoning: ReasoningSummary

def remove_think_tags(content: str) -> str:
    """Remove Qwen3 think tags"""
    return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

async def test_single_review():
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
    
    # Build prompt
    prompt = f"""다음 앱 리뷰를 분석하고 JSON 형식으로 응답하세요.

[리뷰 정보]
앱: {row_dict['package_id']}
평점: {row_dict['score']}/5
내용: {row_dict['content']}

반드시 JSON 형식으로만 응답하세요."""

    # Ollama settings from .env
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen3:14b')
    api_key = os.getenv('OLLAMA_API_KEY', '')
    timeout = int(os.getenv('OLLAMA_TIMEOUT', '900'))
    
    print(f"\n🤖 Calling Ollama NATIVE API (/api/chat)")
    print(f"   Model: {model}")
    print(f"   Base URL: {base_url}")
    print(f"   Timeout: {timeout}s")
    print("-" * 80)
    
    # Get JSON schema from Pydantic model
    json_schema = ReviewAnalysisResponse.model_json_schema()
    
    # Build request payload for NATIVE API (/api/chat)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "당신은 앱 리뷰를 분석하는 전문가입니다. 정확한 JSON을 생성합니다."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "format": json_schema,  # Native API uses 'format' parameter
        "stream": False,
        "options": {
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/api/chat",  # NATIVE API endpoint
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                result = await response.json()
                
        elapsed = asyncio.get_event_loop().time() - start_time
        
        print(f"\n⏱️ Response time: {elapsed:.1f}s")
        
        # Native API response format
        if 'message' in result and 'content' in result['message']:
            raw_content = result['message']['content']
        else:
            print(f"Unexpected response structure: {json.dumps(result, indent=2)[:500]}")
            return
            
        print("\n📤 RAW RESPONSE:")
        print("=" * 80)
        print(raw_content[:3000])
        if len(raw_content) > 3000:
            print(f"... (truncated, total {len(raw_content)} chars)")
        print("=" * 80)
        
        # Remove <think> tags
        clean_content = remove_think_tags(raw_content)
        
        if clean_content != raw_content:
            print("\n📤 AFTER THINK TAG REMOVAL:")
            print("=" * 80)
            print(clean_content[:2000])
            print("=" * 80)
        
        # Try to parse with Pydantic
        try:
            parsed = ReviewAnalysisResponse.model_validate_json(clean_content)
            print("\n✅ PYDANTIC VALIDATION SUCCESS:")
            print(f"   Sentiment: {parsed.result.sentiment.sentiment_label} (score: {parsed.result.sentiment.sentiment_score})")
            print(f"   Emotions: {parsed.result.sentiment.emotions}")
            print(f"   Category: {parsed.result.category.primary_category}")
            print(f"   Is Complaint: {parsed.result.complaint.is_complaint}")
            print(f"   Complaint Type: {parsed.result.complaint.complaint_type}")
            print(f"   Urgency: {parsed.result.complaint.urgency}")
            print(f"   Overall Confidence: {parsed.result.confidence}")
            print(f"   Reasoning: {parsed.reasoning.summary[:150]}...")
        except Exception as e:
            print(f"\n❌ PYDANTIC VALIDATION FAILED: {type(e).__name__}: {e}")
            
            # Try raw JSON parse
            try:
                json_data = json.loads(clean_content)
                print("\n⚠️ Raw JSON parse succeeded (Pydantic failed):")
                print(json.dumps(json_data, indent=2, ensure_ascii=False)[:1500])
            except json.JSONDecodeError as je:
                print(f"\n❌ JSON parse also failed: {je}")
                
    except asyncio.TimeoutError:
        print(f"\n❌ Request timed out after {timeout}s")
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_single_review())
