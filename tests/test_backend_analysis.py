import sys
from pathlib import Path
import logging
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_backend_analysis():
    app = create_app()
    client = app.test_client()
    
    company_code = 'bank_k'
    logger.info(f"Requesting /api/v1/analysis/company/{company_code}...")
    
    response = client.get(f'/api/v1/analysis/company/{company_code}?days=30')
    
    if response.status_code != 200:
        logger.error(f"Failed: Status code {response.status_code}")
        logger.error(f"Response: {response.data.decode('utf-8')}")
        sys.exit(1)
        
    data = json.loads(response.data)
    logger.info(f"Status: {data.get('status')}")
    
    result = data.get('data', {})
    package_id = result.get('package_id')
    logger.info(f"Package ID: {package_id}")
    
    if package_id != 'com.example.bank_k':
        logger.error(f"Expected com.example.bank_k, got {package_id}")
        sys.exit(1)
        
    sentiment_trend = result.get('sentiment', {}).get('trend', [])
    logger.info(f"Sentiment Trend Points: {len(sentiment_trend)}")
    
    if not sentiment_trend:
        logger.warning("No sentiment trend data found (might be empty DB, but API worked)")
    else:
        logger.info(f"First trend point: {sentiment_trend[0]}")
            
    logger.info("Backend analysis verification passed!")

if __name__ == "__main__":
    test_backend_analysis()
