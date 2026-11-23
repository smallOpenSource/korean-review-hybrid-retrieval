
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_data():
    logger.info("Initializing ReviewService...")
    service = get_review_service()
    
    # Fetch 5 reviews that have sentiment
    query = {
        "size": 5,
        "query": {
            "exists": {"field": "sentiment"}
        }
    }
    
    logger.info("Fetching reviews to reset...")
    response = service._os.sync_client.search(index=service._index, body=query)
    hits = response['hits']['hits']
    logger.info(f"Found {len(hits)} reviews to reset.")
    
    for hit in hits:
        review_id = hit['_id']
        
        # Update document to remove sentiment and set analyzed to false
        # Scripted update to remove field
        update_body = {
            "script": {
                "source": "ctx._source.remove('sentiment'); ctx._source.analyzed = false",
                "lang": "painless"
            }
        }
        
        try:
            service._os.sync_client.update(
                index=service._index,
                id=review_id,
                body=update_body
            )
            logger.info(f"Reset review {review_id}")
        except Exception as e:
            logger.error(f"Failed to reset review {review_id}: {e}")
            
    logger.info("Data reset completed.")

if __name__ == "__main__":
    reset_data()
