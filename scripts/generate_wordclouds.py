#!/usr/bin/env python3
"""
Script to generate wordclouds for all companies.
Run this periodically or on-demand to update wordcloud images.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.wordcloud_service import get_wordcloud_service
from app.services.app_service import get_app_service
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Generate wordclouds for all companies."""
    logger.info("Starting wordcloud generation for all companies")
    
    # Get services
    wordcloud_service = get_wordcloud_service()
    app_service = get_app_service()
    
    # Get all apps
    apps = app_service.get_all_apps()
    logger.info(f"Found {len(apps)} apps")
    
    # Generate for each app
    success_count = 0
    fail_count = 0
    
    for app in apps:
        company_code = app.get('company_code')
        package_id = app.get('package_id')
        company_name = app.get('company_name')
        
        if not company_code or not package_id:
            logger.warning(f"Skipping app without code/id: {app}")
            continue
        
        logger.info(f"Generating wordcloud for {company_name} ({company_code})")
        
        try:
            results = wordcloud_service.generate_for_company(
                app_id=package_id,
                company_code=company_code,
                days=90
            )
            
            if any(results.values()):
                success_count += 1
                logger.info(f"  ✓ Generated: pos={results.get('pos', False)}, neg={results.get('neg', False)}")
            else:
                fail_count += 1
                logger.warning(f"  ✗ Failed to generate any wordclouds")
                
        except Exception as e:
            fail_count += 1
            logger.error(f"  ✗ Error: {e}")
    
    logger.info(f"\nCompleted: {success_count} successful, {fail_count} failed")
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
