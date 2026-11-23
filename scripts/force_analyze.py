import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler.jobs.analyze_reviews import AnalyzeReviewsJob
from app.config.settings import get_settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Force starting analysis job...")
    job = AnalyzeReviewsJob()
    
    # Run analysis
    # This will fetch unanalyzed reviews and process them
    await job.run()
    logger.info("Analysis job finished.")

if __name__ == "__main__":
    asyncio.run(main())
