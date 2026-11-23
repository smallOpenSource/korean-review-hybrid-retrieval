
import sys
import os
import logging
import random
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.review_service import get_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def populate_data():
    logger.info("Initializing ReviewService...")
    service = get_review_service()
    
    # Fetch reviews with missing sentiment
    query = {
        "size": 1000,
        "query": {
            "bool": {
                "must_not": {
                    "exists": {"field": "sentiment"}
                }
            }
        }
    }
    
    logger.info("Fetching reviews without sentiment...")
    response = service._os.sync_client.search(index=service._index, body=query)
    hits = response['hits']['hits']
    logger.info(f"Found {len(hits)} reviews to update.")
    
    for hit in hits:
        review_id = hit['_id']
        source = hit['_source']
        
        # Generate dummy sentiment
        score = random.randint(1, 5)
        label = "positive" if score > 3 else "negative" if score < 3 else "neutral"
        
        sentiment = {
            "label": label,
            "score": float(score),
            "confidence": 0.9
        }
        
        # Update document
        update_body = {
            "doc": {
                "sentiment": sentiment,
                "analyzed": True
            }
        }
        
        try:
            service._os.sync_client.update(
                index=service._index,
                id=review_id,
                body=update_body
            )
            # logger.info(f"Updated review {review_id} with score {score}")
        except Exception as e:
            logger.error(f"Failed to update review {review_id}: {e}")
            
    logger.info("Data population completed.")

if __name__ == "__main__":
    populate_data()
