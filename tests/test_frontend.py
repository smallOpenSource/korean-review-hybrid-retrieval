import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_frontend():
    app = create_app()
    client = app.test_client()
    
    logger.info("Requesting /company_list...")
    response = client.get('/company_list')
    
    if response.status_code != 200:
        logger.error(f"Failed: Status code {response.status_code}")
        sys.exit(1)
        
    content = response.data.decode('utf-8')
    logger.info(f"Content length: {len(content)}")
    
    # Check for new apps
    check_apps = ['pay_a', 'pay_b', 'bank_l']
    for app_code in check_apps:
        if app_code in content:
            logger.info(f"Found {app_code} in HTML")
        else:
            logger.error(f"Missing {app_code} in HTML")
            sys.exit(1)
            
    logger.info("Frontend verification passed!")

if __name__ == "__main__":
    test_frontend()
