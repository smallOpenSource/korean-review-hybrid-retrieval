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

def test_settings_api():
    app = create_app()
    client = app.test_client()
    
    # 1. Update settings
    new_settings = {
        'llm_provider': 'openai',
        'daily_collection_limit': '500',
        'auto_collect': False
    }
    
    logger.info("Updating settings...")
    response = client.post('/api/v1/settings/update', 
                          data=json.dumps(new_settings),
                          content_type='application/json')
    
    if response.status_code != 200:
        logger.error(f"Update failed: {response.status_code}")
        sys.exit(1)
        
    logger.info("Update successful.")
    
    # 2. Verify persistence (fetch page and check config)
    # Since we don't have a direct GET API for settings (it's rendered in HTML),
    # we can check the DB directly or trust the update success if we want to be strict.
    # But let's use the service directly to verify persistence.
    
    from app.services.settings_service import get_settings_service
    service = get_settings_service()
    saved_settings = service.get_all_settings()
    
    logger.info(f"Saved Settings: {saved_settings}")
    
    if saved_settings.get('llm_provider') != 'openai':
        logger.error("llm_provider not saved correctly")
        sys.exit(1)
        
    if saved_settings.get('daily_collection_limit') != '500':
        logger.error("daily_collection_limit not saved correctly")
        sys.exit(1)
        
    # Boolean check (stored as string 'true'/'false')
    if saved_settings.get('auto_collect') != 'false':
        logger.error(f"auto_collect not saved correctly: {saved_settings.get('auto_collect')}")
        sys.exit(1)
        
    logger.info("Settings persistence verification passed!")

if __name__ == "__main__":
    test_settings_api()
