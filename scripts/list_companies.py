import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.app_service import get_app_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def list_companies():
    service = get_app_service()
    apps = service.get_all_apps()
    
    print(f"Found {len(apps)} apps:")
    for app in apps:
        print(f"{app['company_name']}|{app['company_code']}")

if __name__ == "__main__":
    list_companies()
