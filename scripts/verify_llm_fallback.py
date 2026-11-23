import os
import sys
from app.agents.llm_client import get_llm_client, LLMProvider

def verify_order():
    client = get_llm_client()
    providers = client._get_available_providers()
    print(f"Current Fallback Order: {[p.value for p in providers]}")

if __name__ == "__main__":
    verify_order()
