import requests
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_endpoints():
    base_url = "http://127.0.0.1:5952"
    endpoints = [
        "/",
        "/api/v1/dashboard/summary?days=30"
    ]
    
    success = True
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        logger.info(f"Testing {url}...")
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                logger.info(f"SUCCESS: {url} returned 200 OK")
                logger.info(f"Response snippet: {response.text[:100]}...")
            else:
                logger.error(f"FAILURE: {url} returned {response.status_code}")
                success = False
        except requests.exceptions.RequestException as e:
            logger.error(f"ERROR: Failed to connect to {url}: {e}")
            success = False
            
    if success:
        logger.info("All headless checks passed!")
        sys.exit(0)
    else:
        logger.error("Some checks failed.")
        sys.exit(1)

if __name__ == "__main__":
    test_endpoints()
