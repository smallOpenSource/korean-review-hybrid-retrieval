#!/usr/bin/env python3
"""
Adversarial Stress Test Script
Attempts to break the API with invalid inputs, large payloads, and edge cases.
"""

import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:5952"

def test_analysis_edge_cases():
    logger.info("Testing Analysis API Edge Cases...")
    endpoint = f"{BASE_URL}/api/v1/analysis/analyze"
    
    cases = [
        ("Empty JSON", {}, 400),
        ("Missing Content", {"app_name": "Test"}, 400),
        ("Empty Content", {"content": "", "app_name": "Test"}, 400),
        ("Special Chars", {"content": "😊👍🔥", "app_name": "Test"}, 200),
        ("SQL Injection Attempt", {"content": "'; DROP TABLE reviews; --", "app_name": "Test"}, 200),
        ("Huge Content", {"content": "가" * 10000, "app_name": "Test"}, 200), # Moved to end
    ]
    
    failures = []
    for name, payload, expected_status in cases:
        try:
            response = requests.post(endpoint, json=payload, timeout=30) # Increased timeout
            if response.status_code != expected_status:
                failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
            else:
                logger.info(f"✅ {name} passed")
        except Exception as e:
            failures.append(f"{name}: Exception {str(e)}")
            
    return failures

def test_search_edge_cases():
    logger.info("Testing Search API Edge Cases...")
    endpoint = f"{BASE_URL}/api/v1/search"
    
    cases = [
        ("Empty Query", {"query": ""}, 200), # Should return empty or all
        ("XSS Attempt", {"query": "<script>alert(1)</script>"}, 200), # Should search literal
        ("Long Query", {"query": "a" * 1000}, 200),
    ]
    
    failures = []
    for name, payload, expected_status in cases:
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            if response.status_code != expected_status:
                failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
            else:
                logger.info(f"✅ {name} passed")
        except Exception as e:
            failures.append(f"{name}: Exception {str(e)}")
            
    return failures

def main():
    all_failures = []
    all_failures.extend(test_analysis_edge_cases())
    all_failures.extend(test_search_edge_cases())
    
    if all_failures:
        logger.error("❌ Stress Test Failed with the following errors:")
        for f in all_failures:
            logger.error(f)
        exit(1)
    else:
        logger.info("🎉 All Stress Tests Passed!")
        exit(0)

if __name__ == "__main__":
    main()
