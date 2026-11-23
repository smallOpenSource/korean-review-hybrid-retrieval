
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.llm_client import get_llm_client, LLMProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_provider(provider_name: str):
    logger.info(f"Testing provider: {provider_name}")
    
    try:
        # Load env vars
        load_dotenv()
        
        # Get client for specific provider if possible, or just use unified client and force model?
        # The unified client selects provider based on model or fallback.
        # To test specific provider, we should try to instantiate it directly or use a model known to be handled by it.
        
        client = get_llm_client()
        
        logger.info(f"Using task_type: sentiment_analysis")
        
        # We can't easily force a provider with UnifiedLLMClient as it iterates.
        # But we can check if the configured primary model for the task matches the provider we want to test.
        # Or we can temporarily mock the config or client internals.
        # For this test, let's just call generate and see which provider handles it.
        # To test specific providers, we might need to access the internal clients directly.
        
        if hasattr(client, '_clients') and provider_name.lower() in [p.value for p in LLMProvider]:
            provider_enum = LLMProvider(provider_name.lower())
            if provider_enum in client._clients:
                specific_client = client._clients[provider_enum]
                # Specific clients might have different generate signatures?
                # BaseLLMClient.generate(self, prompt, model, ...)
                
                # We need to know the model name for this provider
                model = client._get_model_for_provider(provider_enum, 'sentiment_analysis')
                
                logger.info(f"Directly testing {provider_name} with model {model}")
                response = await specific_client.generate(
                    prompt="Hello, are you working?",
                    model=model
                )
                logger.info(f"Response from {provider_name}: {response.content}")
                return

        # Fallback to unified call if we can't access internals
        response = await client.generate(
            prompt="Hello, are you working?",
            task_type='sentiment_analysis'
        )
        
        logger.info(f"Response from {provider_name}: {response.content}")
        logger.info(f"Provider used: {response.provider}")
        
    except Exception as e:
        logger.error(f"Failed to test {provider_name}: {e}")

async def main():
    providers = ['gemini', 'ollama', 'groq', 'openai']
    
    print("Starting LLM Provider Tests...")
    for provider in providers:
        print(f"\n--- Testing {provider} ---")
        await test_provider(provider)
    print("\nTests Completed.")

if __name__ == "__main__":
    asyncio.run(main())
