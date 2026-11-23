import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scheduler.utils.config_loader import get_scheduler_config

def verify_config():
    config = get_scheduler_config()
    
    print("=== Database Config ===")
    print(config.database)
    
    print("\n=== Redis Config ===")
    print(config.redis)
    
    sentinels = config.redis.get('sentinel', {}).get('sentinels', [])
    print(f"\nSentinels count: {len(sentinels)}")
    for s in sentinels:
        print(f"- {s}")

if __name__ == "__main__":
    verify_config()
