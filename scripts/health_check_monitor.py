#!/usr/bin/env python3
"""
Health Check Monitor Script
Periodically checks the health of the App Reviews system.
Checks:
- Web Server (Pages & APIs)
- Database Connection
- OpenSearch Connection
"""

import sys
import time
import requests
import logging
from datetime import datetime
from typing import List, Dict, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/health_check.log')
    ]
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:5952"

ENDPOINTS = [
    # Pages
    ("/", 200),
    ("/company_list", 200),
    ("/company_info/sec_c/", 200),
    ("/dept_review/ALL", 200),
    ("/complaint_board", 200),
    
    # APIs
    ("/api/v1/dashboard/summary", 200),
    ("/api/v1/dashboard/trends", 200),
    ("/api/v1/analysis/company/sec_c", 200),
    ("/api/v1/complaints", 200),
    ("/health", 200),
]

def check_endpoints() -> List[Tuple[str, bool, str]]:
    results = []
    for path, expected_status in ENDPOINTS:
        url = f"{BASE_URL}{path}"
        try:
            response = requests.get(url, timeout=15)
            status = response.status_code
            success = status == expected_status
            msg = f"Status: {status}"
            if not success:
                msg += f" (Expected {expected_status})"
            results.append((path, success, msg))
        except Exception as e:
            results.append((path, False, str(e)))
    return results

def print_report(results: List[Tuple[str, bool, str]]):
    print("\n=== Health Check Report ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_passed = True
    for path, success, msg in results:
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} {path:<40} {msg}")
        if not success:
            all_passed = False
            
    print("-" * 60)
    if all_passed:
        print("🎉 All systems operational.")
        logger.info("Health check passed.")
    else:
        print("⚠️ Some checks failed.")
        logger.error("Health check failed.")
        
    return all_passed

def main():
    logger.info("Starting health check...")
    results = check_endpoints()
    success = print_report(results)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
