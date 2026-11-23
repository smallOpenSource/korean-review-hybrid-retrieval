import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.app_service import get_app_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_app_service():
    service = get_app_service()
    
    # Test get_all_apps
    apps = service.get_all_apps()
    logger.info(f"Total apps: {len(apps)}")
    if len(apps) != 68:
        logger.error(f"Expected 68 apps, got {len(apps)}")
        sys.exit(1)
        
    # Test get_app_by_code
    code = 'bank_k'
    app = service.get_app_by_code(code)
    if app:
        logger.info(f"Found app: {app['company_name']} ({app['package_id']})")
    else:
        logger.error(f"App not found: {code}")
        sys.exit(1)

if __name__ == "__main__":
    test_app_service()
