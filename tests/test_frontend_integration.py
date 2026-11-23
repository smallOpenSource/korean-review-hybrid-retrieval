import sys
from pathlib import Path
import logging
import json
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_frontend_integration():
    app = create_app()
    client = app.test_client()
    
    # 1. Get the HTML page
    company_code = 'bank_k'
    logger.info(f"Requesting /company_info/{company_code}/...")
    response = client.get(f'/company_info/{company_code}/')
    
    if response.status_code != 200:
        logger.error(f"Failed to get page: {response.status_code}")
        sys.exit(1)
        
    html_content = response.data.decode('utf-8')
    
    # 2. Verify company_code is injected correctly in JS
    # Looking for: const companyCode = "bank_k";
    match = re.search(r'const companyCode = "([^"]+)";', html_content)
    if not match:
        logger.error("Could not find companyCode in HTML JS")
        sys.exit(1)
        
    extracted_code = match.group(1)
    logger.info(f"Found companyCode in HTML: {extracted_code}")
    
    if extracted_code != company_code:
        logger.error(f"Mismatch: expected {company_code}, got {extracted_code}")
        sys.exit(1)
        
    # 3. Simulate the JS fetch call
    api_url = f"/api/v1/analysis/company/{extracted_code}?days=30"
    logger.info(f"Simulating JS fetch to: {api_url}")
    
    api_response = client.get(api_url)
    
    if api_response.status_code != 200:
        logger.error(f"API call failed: {api_response.status_code}")
        sys.exit(1)
        
    data = json.loads(api_response.data)
    
    if data.get('status') != 'ok':
        logger.error(f"API returned error status: {data.get('status')}")
        sys.exit(1)
        
    # 4. Verify data structure for Chart.js
    chart_data = data.get('data', {})
    sentiment = chart_data.get('sentiment', {})
    trend = sentiment.get('trend', [])
    
    logger.info(f"Chart data received. Trend points: {len(trend)}")
    
    # Even if empty (no reviews), the structure must be correct
    if not isinstance(trend, list):
        logger.error("Trend data is not a list")
        sys.exit(1)
        
    logger.info("Frontend integration verification passed!")

if __name__ == "__main__":
    test_frontend_integration()
