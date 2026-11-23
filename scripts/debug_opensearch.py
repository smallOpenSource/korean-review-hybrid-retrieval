
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.review_service import get_review_service
from app.core.opensearch_client import OpenSearchClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_opensearch():
    logger.info("Initializing ReviewService...")
    try:
        service = get_review_service()
        logger.info("ReviewService initialized.")
        
        logger.info("Fetching one document...")
        response = service._os.sync_client.search(
            index=service._index,
            body={"size": 1, "query": {"match_all": {}}}
        )
        hits = response['hits']['hits']
        if hits:
            import json
            print("Document Source:")
            print(json.dumps(hits[0]['_source'], indent=2, ensure_ascii=False))
        else:
            print("No documents found.")
            
    except Exception as e:
        logger.error("FAILED: %s", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_opensearch()
