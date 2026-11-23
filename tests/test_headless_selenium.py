import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_headless_test():
    logger.info("Starting headless browser test...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Attempt to use installed Chrome
    # If Chrome is in standard path, Selenium finds it.
    
    chrome_options.add_argument("--disable-gpu")
    chrome_options.page_load_strategy = 'eager'
    
    service = Service(ChromeDriverManager().install())
    
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        logger.info("Browser initialized successfully.")
        
        # Test Dashboard
        url = "http://127.0.0.1:5952/"
        logger.info(f"Navigating to {url}...")
        driver.get(url)
        
        # Verify page content
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "종합 분석" not in body_text:
            logger.warning(f"Verification Failed: '종합 분석' text not found.")
        else:
            logger.info("Verification Successful: '종합 분석' text found.")
            
        if "총 리뷰 수" not in body_text:
             logger.warning(f"Verification Failed: '총 리뷰 수' text not found.")
        else:
             logger.info("Verification Successful: '총 리뷰 수' text found.")
        title = driver.title
        logger.info(f"Page Title: {title}")
        
        screenshot_path = "dashboard_headless.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved to {screenshot_path}")
        # Check for specific elements (simple check)
        page_source = driver.page_source
        if "종합 분석" in page_source:
            logger.info("Verification Passed: '종합 분석' text found.")
        else:
            logger.warning("Verification Failed: '종합 분석' text not found.")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
            logger.info("Browser closed.")

if __name__ == "__main__":
    run_headless_test()
