"""
Unified LLM Client with multi-provider fallback support.
Supports: Gemini (primary) -> Ollama -> Groq -> OpenAI (fallback order)
"""

import json
import logging
import asyncio
import time
import re
import aiohttp
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.config.settings import get_settings
from app.config.llm_config import get_llm_config, LLMConfig
from app.core.rate_limiter import (
    get_rate_limiter,
    RateLimiter,
    RateLimitExceeded
)

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OLLAMA = "ollama"
    GROQ = "groq"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"


class RateLimitError(Exception):
    """Groq-specific rate limit exception (HTTP 429)."""
    def __init__(self, model: str, limit_type: str, retry_after: float = None, message: str = ""):
        self.model = model
        self.limit_type = limit_type  # "RPM" or "RPD"
        self.retry_after = retry_after
        self.message = message
        super().__init__(f"Groq rate limit ({limit_type}): {message}")


class AzureRateLimitError(Exception):
    """Azure OpenAI rate limit exception (HTTP 429)."""
    def __init__(self, model: str, retry_after: float = None, message: str = ""):
        self.model = model
        self.retry_after = retry_after
        self.message = message
        super().__init__(f"Azure OpenAI rate limit: {message}")


@dataclass
class JSONParsingResult:
    """JSON 파싱 결과"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    original_content: Optional[str] = None


@dataclass
class LLMResponse:
    """Response from LLM call."""
    content: str
    parsed_json: Optional[Dict[str, Any]]
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    timestamp: datetime
    is_fallback: bool = False
    is_secondary_model: bool = False


@dataclass
class EmbeddingResponse:
    """Response from embedding call."""
    embedding: List[float]
    model: str
    provider: str
    input_tokens: int
    latency_ms: int
    dimensions: int


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    provider: LLMProvider

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        **kwargs
    ) -> LLMResponse:
        """Generate text completion."""
        pass

    @abstractmethod
    async def embed(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """Generate text embedding."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available."""
        pass

    def normalize_typographic_quotes(self, content: str) -> str:
        """
        Normalize typographic quotes to ASCII (industry standard for LLM JSON).
        
        Converts:
        - U+2018/U+2019 (smart single quotes) → U+0027 (ASCII ')
        - U+201C/U+201D (smart double quotes) → U+0022 (ASCII ")
        - U+2032/U+2033 (prime symbols) → ASCII quotes
        - U+FF02/U+FF07 (fullwidth quotes) → ASCII quotes
        """
        replacements = {
            # Smart single quotes
            '\u2018': "'",  # LEFT SINGLE QUOTATION MARK
            '\u2019': "'",  # RIGHT SINGLE QUOTATION MARK
            '\u201a': "'",  # SINGLE LOW-9 QUOTATION MARK
            '\u201b': "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
            # Smart double quotes
            '\u201c': '"',  # LEFT DOUBLE QUOTATION MARK
            '\u201d': '"',  # RIGHT DOUBLE QUOTATION MARK
            '\u201e': '"',  # DOUBLE LOW-9 QUOTATION MARK
            '\u201f': '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
            # Prime symbols
            '\u2032': "'",  # PRIME
            '\u2033': '"',  # DOUBLE PRIME
            # Fullwidth characters (CJK)
            '\uff02': '"',  # FULLWIDTH QUOTATION MARK
            '\uff07': "'",  # FULLWIDTH APOSTROPHE
        }
        
        for old, new in replacements.items():
            content = content.replace(old, new)
        
        return content

    def _clean_response_content(self, content: str) -> str:
        """Remove <think> tags, normalize quotes, and clean artifacts from response."""
        # 1. Remove <think>...</think> blocks (including multiline)
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # 2. Normalize typographic quotes to ASCII (industry standard)
        content = self.normalize_typographic_quotes(content)
        return content.strip()

    def _try_parse_json(self, content: str) -> JSONParsingResult:
        """
        Try to parse JSON from content with enhanced cleaning and detailed error tracking.

        Implements Layer 3 from groq_model_guide.md:
        - Removes BOM (Byte Order Mark)
        - Removes control characters
        - Normalizes quotes and cleans artifacts

        Returns:
            JSONParsingResult with success status, data, or error details
        """
        try:
            # NEW: Step 1 - Remove BOM (Byte Order Mark)
            content = content.lstrip('\ufeff')

            # NEW: Step 2 - Remove control characters
            import re
            content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)

            # Step 3 - Clean response content (existing)
            content = self._clean_response_content(content)

            # Remove markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Find JSON object/array
            start_idx = content.find('{')
            if start_idx == -1:
                start_idx = content.find('[')

            if start_idx != -1:
                bracket_count = 0
                start_char = content[start_idx]
                end_char = '}' if start_char == '{' else ']'

                for i, char in enumerate(content[start_idx:], start_idx):
                    if char == start_char:
                        bracket_count += 1
                    elif char == end_char:
                        bracket_count -= 1
                        if bracket_count == 0:
                            content = content[start_idx:i + 1]
                            break

            # Parse JSON
            data = json.loads(content)
            return JSONParsingResult(success=True, data=data)

        except json.JSONDecodeError as e:
            # ENHANCED: More detailed error tracking
            logger.warning(
                f"JSON decode failed: {e.msg} at line {e.lineno}, col {e.colno}. "
                f"Content preview: {content[:200]}..."
            )
            return JSONParsingResult(
                success=False,
                error=str(e),
                error_type="JSONDecodeError",
                original_content=content[:1000]  # Increased from 500
            )
        except ValueError as e:
            logger.warning(f"Value error during JSON parsing: {e}")
            return JSONParsingResult(
                success=False,
                error=str(e),
                error_type="ValueError",
                original_content=content[:1000]  # Increased from 500
            )
        except Exception as e:
            logger.error(f"Unexpected error during JSON parsing: {type(e).__name__}: {e}")
            return JSONParsingResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                original_content=content[:1000]  # Increased from 500
            )


class GeminiLLMClient(BaseLLMClient):
    """Gemini API client."""

    provider = LLMProvider.GEMINI

    def __init__(self, key_rotator=None):
        self._settings = get_settings().gemini
        self._key_rotator = key_rotator
        self._initialized = False
        self._models = {}
        self._current_api_key = None

    def is_available(self) -> bool:
        """Check if Gemini is configured."""
        if self._key_rotator:
            return bool(self._key_rotator.get_key_count() > 0)
        return bool(self._settings.api_key)
    
    def _get_current_api_key(self) -> str:
        """현재 사용할 API 키 반환."""
        if self._key_rotator:
            return self._key_rotator.get_current_key()
        return self._settings.api_key

    def _initialize(self):
        """Initialize Gemini API."""
        try:
            import google.generativeai as genai
            api_key = self._get_current_api_key()
            genai.configure(api_key=api_key)
            self._genai = genai
            self._initialized = True
            self._current_api_key = api_key
            logger.info(f"Gemini API initialized with key ...{api_key[-8:]}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            raise
    
    def reinitialize_with_new_key(self):
        """새 키로 재초기화."""
        self._initialized = False
        self._models.clear()
        self._current_api_key = None
        self._initialize()

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using Gemini API with optional JSON schema enforcement."""
        self._initialize()
        start_time = time.monotonic()

        if model not in self._models:
            self._models[model] = self._genai.GenerativeModel(model)

        # Enhance prompt with JSON schema if provided
        enhanced_prompt = prompt
        if json_schema and parse_json:
            schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
            enhanced_prompt = f"""{prompt}

IMPORTANT: You MUST respond with valid JSON matching this exact schema:
```json
{schema_str}
```

Rules:
1. Output ONLY valid JSON, no markdown, no explanations
2. All required fields must be present
3. Use exact field names and types from schema
4. Ensure proper JSON syntax (commas, quotes, brackets)"""

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": 0.95,
        }

        if parse_json:
            generation_config["response_mime_type"] = "application/json"

        timeout = self._settings.timeout
        logger.debug(f"Calling Gemini with timeout={timeout}s, json_mode={parse_json}, schema={'provided' if json_schema else 'none'}")

        try:
            response = await asyncio.to_thread(
                self._models[model].generate_content,
                enhanced_prompt,
                generation_config=generation_config,
                request_options={'timeout': timeout}
            )
        except Exception as e:
            if "deadline_exceeded" in str(e).lower() or "timeout" in str(e).lower():
                logger.error(f"Gemini request timed out after {timeout}s")
            raise

        content = response.text
        latency_ms = int((time.monotonic() - start_time) * 1000)

        parsed_json = None
        parsing_error = None
        if parse_json:
            parse_result = self._try_parse_json(content)
            if parse_result.success:
                parsed_json = parse_result.data
            else:
                parsing_error = parse_result.error
                logger.error(
                    f"JSON parsing failed for Gemini response. "
                    f"Error: {parse_result.error_type} - {parse_result.error}"
                )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=model,
            provider=self.provider.value,
            input_tokens=len(prompt) // 4,
            output_tokens=len(content) // 4,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            is_fallback=False
        )

    async def embed(
        self,
        text: str,
        model: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        **kwargs
    ) -> EmbeddingResponse:
        """Generate embedding using Gemini."""
        self._initialize()
        start_time = time.monotonic()
        
        timeout = self._settings.timeout
        logger.debug(f"Calling Gemini embedding with timeout={timeout}s")

        try:
            response = await asyncio.to_thread(
                self._genai.embed_content,
                model=f"models/{model}",
                content=text,
                task_type=task_type,
                request_options={'timeout': timeout}
            )
        except Exception as e:
            if "deadline_exceeded" in str(e).lower() or "timeout" in str(e).lower():
                logger.error(f"Gemini embedding request timed out after {timeout}s")
            raise

        latency_ms = int((time.monotonic() - start_time) * 1000)
        embedding = response['embedding']

        return EmbeddingResponse(
            embedding=embedding,
            model=model,
            provider=self.provider.value,
            input_tokens=len(text) // 4,
            latency_ms=latency_ms,
            dimensions=len(embedding)
        )




class OllamaLLMClient(BaseLLMClient):
    """Ollama API client with Bearer token authentication."""

    provider = LLMProvider.OLLAMA

    def __init__(self):
        self._settings = get_settings().ollama
        self._session: Optional[aiohttp.ClientSession] = None

    def is_available(self) -> bool:
        """Check if Ollama is configured."""
        return bool(self._settings.base_url)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        # Check if session exists and is valid for current loop
        if self._session:
            if self._session.closed:
                self._session = None
            elif self._session._loop != asyncio.get_running_loop():
                # Loop mismatch - close old session (if possible) and create new
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = None

        if self._session is None:
            headers = {"Content-Type": "application/json"}
            if self._settings.api_key:
                headers["Authorization"] = f"Bearer {self._settings.api_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using Ollama Native API (/api/chat) with JSON schema support."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Use Native API endpoint (/api/chat) for format parameter support
        endpoint = self._settings.get_endpoint()
        url = f"{endpoint}/api/chat"

        timeout = self._settings.timeout
        logger.debug(f"Calling Ollama Native API with timeout={timeout}s")

        # Load advanced parameters from centralized settings
        settings = get_settings()
        advanced = settings.ollama_advanced

        payload = {
            "model": model or self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",  # ★ ENABLED: 7.8B model supports JSON mode
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,  # Use requested max_tokens instead of forcing 4096
                "top_p": 0.9,              # ★ ADDED: Nucleus sampling for quality
                "top_k": advanced.top_k,
                "repeat_penalty": 1.1,     # ★ ADDED: Prevent repetitive syntax errors
                "num_ctx": advanced.num_ctx
            }
        }

        # JSON mode is now always enabled for 7.8B model
        # Previous issues with 2.4B model should not occur with 7.8B

        try:
            # aiohttp requires ClientTimeout object with granular settings
            # sock_connect: Fast fail on connection issues (10s)
            # sock_read: Patient wait for model inference (300s = 5min)
            # total: No overall timeout (None) - let sock_read handle it
            timeout_obj = aiohttp.ClientTimeout(
                sock_connect=10,
                sock_read=300,
                total=None
            )
            async with session.post(url, json=payload, timeout=timeout_obj) as response:
                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError:
            logger.error(f"Ollama request timed out after {timeout}s")
            raise
        except aiohttp.ServerDisconnectedError as e:
            logger.error(f"Ollama server disconnected: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama request failed: {type(e).__name__}: {e}")
            raise

        # Native API response format: {"message": {"content": "..."}}
        content = data.get('message', {}).get('content', '')
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Remove <think> tags from Qwen3 responses
        content = self._clean_response_content(content)

        parsed_json = None
        parsing_error = None
        if parse_json:
            parse_result = self._try_parse_json(content)
            if parse_result.success:
                parsed_json = parse_result.data
            else:
                # ★★★ Attempt JSON repair ★★★
                logger.warning(
                    f"JSON parsing failed: {parse_result.error_type} - {parse_result.error}. "
                    f"Attempting JSON repair..."
                )
                logger.debug(f"Original content (first 500 chars): {content[:500]}")

                try:
                    repaired_content = self._repair_json(content)
                    repair_result = self._try_parse_json(repaired_content)

                    if repair_result.success:
                        parsed_json = repair_result.data
                        logger.info("JSON repair successful")
                    else:
                        parsing_error = repair_result.error
                        logger.error(
                            f"JSON repair also failed: {repair_result.error_type} - {repair_result.error}"
                        )
                        logger.error(f"Full response: {content}")
                except Exception as repair_error:
                    parsing_error = str(repair_error)
                    logger.error(f"JSON repair raised exception: {repair_error}")
                    logger.error(f"Full response: {content}")

        # Estimate tokens from content length if not provided
        prompt_tokens = data.get('prompt_eval_count', len(prompt) // 4)
        output_tokens = data.get('eval_count', len(content) // 4)

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=model or self._settings.model,
            provider=self.provider.value,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            is_fallback=True
        )

    async def embed(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """Generate embedding using Ollama (OpenAI compatible)."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Use OpenAI-compatible endpoint with round-robin load balancing
        endpoint = self._settings.get_endpoint()
        url = f"{endpoint}/v1/embeddings"
        
        timeout = self._settings.timeout
        logger.debug(f"Calling Ollama embedding with timeout={timeout}s")

        payload = {
            "model": model or self._settings.embedding_model,
            "input": text
        }

        try:
            # Granular timeout for OpenAI-compatible endpoint
            timeout_obj = aiohttp.ClientTimeout(
                sock_connect=10,
                sock_read=300,
                total=None
            )
            async with session.post(url, json=payload, timeout=timeout_obj) as response:
                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError:
            logger.error(f"Ollama embedding request timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Ollama embedding request failed: {type(e).__name__}: {e}")
            raise

        latency_ms = int((time.monotonic() - start_time) * 1000)
        embedding = data['data'][0]['embedding']

        return EmbeddingResponse(
            embedding=embedding,
            model=model or self._settings.embedding_model,
            provider=self.provider.value,
            input_tokens=data.get('usage', {}).get('prompt_tokens', len(text) // 4),
            latency_ms=latency_ms,
            dimensions=len(embedding)
        )

    def _repair_json(self, text: str) -> str:
        """
        Attempt to repair common JSON syntax errors.

        Repairs:
        - Remove markdown code blocks (```json ... ```)
        - Trim whitespace
        - Remove trailing commas (invalid in JSON standard)
        - Convert single quotes to double quotes (property names and values)

        Args:
            text: Original response text

        Returns:
            Repaired JSON string

        Note:
            This is a best-effort repair. Complex JSON errors may still fail.
        """
        import re

        # 1. Remove markdown code blocks
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)

        # 2. Trim whitespace
        text = text.strip()

        # 3. Remove trailing commas before } or ]
        # Example: {"key": "value",} → {"key": "value"}
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        # 4. Convert single quotes to double quotes (property names)
        # Example: {'key': → {"key":
        text = re.sub(r"'([^']*)'(\s*:)", r'"\1"\2', text)

        # 5. Convert single quotes to double quotes (string values)
        # Example: : 'value' → : "value"
        text = re.sub(r":\s*'([^']*)'", r': "\1"', text)

        return text




class GroqLLMClient(BaseLLMClient):
    """Groq API client with 5-key rotation support."""

    provider = LLMProvider.GROQ

    def __init__(self, key_rotator=None):
        self._settings = get_settings().groq
        self._key_rotator = key_rotator
        self._session: Optional[aiohttp.ClientSession] = None
        self._current_api_key = None

    def is_available(self) -> bool:
        """Check if Groq is configured."""
        if self._key_rotator:
            return bool(self._key_rotator.get_key_count() > 0)
        return bool(self._settings.api_key)

    def _get_current_api_key(self) -> str:
        """Get current API key from rotator or settings."""
        if self._key_rotator:
            return self._key_rotator.get_current_key()
        return self._settings.api_key

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with current API key."""
        current_key = self._get_current_api_key()

        # Recreate session if API key changed
        if self._session is None or self._session.closed or self._current_api_key != current_key:
            if self._session and not self._session.closed:
                await self._session.close()

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {current_key}"
            }
            self._session = aiohttp.ClientSession(headers=headers)
            self._current_api_key = current_key

        return self._session

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using Groq API with optional JSON schema enforcement."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Enhance prompt with JSON schema if provided
        enhanced_prompt = prompt
        if json_schema and parse_json:
            schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
            enhanced_prompt = f"""{prompt}

IMPORTANT: You MUST respond with valid JSON matching this exact schema:
```json
{schema_str}
```

Rules:
1. Output ONLY valid JSON, no markdown, no explanations
2. All required fields must be present
3. Use exact field names and types from schema
4. Ensure proper JSON syntax (commas, quotes, brackets)"""

        payload = {
            "model": model or self._settings.model,
            "messages": [{"role": "user", "content": enhanced_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Force JSON mode if schema provided or parse_json is True
        if parse_json:
            payload["response_format"] = {"type": "json_object"}

        timeout = self._settings.timeout
        logger.debug(f"Calling Groq with timeout={timeout}s, json_mode={parse_json}, schema={'provided' if json_schema else 'none'}")

        try:
            async with session.post(
                self._settings.api_url,
                json=payload,
                timeout=timeout
            ) as response:
                # HTTP 400 Bad Request Detection (DEBUG)
                if response.status == 400:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'No message')
                        error_type = error_data.get('error', {}).get('type', 'unknown')
                        logger.error(f"Groq HTTP 400 Bad Request - Type: {error_type}, Message: {error_msg}")
                        logger.error(f"Request model: {payload['model']}, parse_json: {parse_json}, schema: {'provided' if json_schema else 'none'}")
                        logger.error(f"Request payload sample: {json.dumps(payload, ensure_ascii=False)[:300]}")
                    except Exception as e:
                        error_text = await response.text()
                        logger.error(f"Groq HTTP 400 Bad Request (raw response): {error_text[:500]}")
                        logger.error(f"Failed to parse error JSON: {e}")

                # HTTP 429 Rate Limit Detection
                if response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get('error', {}).get('message', '')

                    # Parse retry-after from headers or error message
                    retry_after = response.headers.get('retry-after')
                    if not retry_after and 'try again in' in error_msg.lower():
                        # Match formats: "32.5s", "8m49.4592s", "1h30m15.5s"
                        time_match = re.search(r'try again in ([\d.]+(?:[hms][\d.]*)*)', error_msg, re.IGNORECASE)
                        if time_match:
                            time_str = time_match.group(1)
                            # Parse time components
                            hours = minutes = seconds = 0.0

                            # Extract hours
                            h_match = re.search(r'([\d.]+)h', time_str)
                            if h_match:
                                hours = float(h_match.group(1))

                            # Extract minutes
                            m_match = re.search(r'([\d.]+)m', time_str)
                            if m_match:
                                minutes = float(m_match.group(1))

                            # Extract seconds (includes standalone numbers)
                            s_match = re.search(r'([\d.]+)s', time_str)
                            if s_match:
                                seconds = float(s_match.group(1))
                            elif not h_match and not m_match:
                                # If no h/m/s suffix, assume seconds
                                seconds = float(time_str.rstrip('s'))

                            retry_after = hours * 3600 + minutes * 60 + seconds
                            logger.debug(f"Parsed retry_after from '{time_str}': {retry_after:.1f}s")

                    # Determine limit type
                    limit_type = 'RPM' if 'per minute' in error_msg.lower() else 'RPD'

                    logger.warning(f"Groq HTTP 429: {error_msg}")
                    raise RateLimitError(
                        model=model or self._settings.model,
                        limit_type=limit_type,
                        retry_after=retry_after,
                        message=error_msg
                    )

                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError:
            logger.error(f"Groq request timed out after {timeout}s")
            raise

        content = data["choices"][0]["message"]["content"]
        latency_ms = int((time.monotonic() - start_time) * 1000)
        usage = data.get("usage", {})

        parsed_json = None
        parsing_error = None
        if parse_json:
            parse_result = self._try_parse_json(content)
            if parse_result.success:
                parsed_json = parse_result.data
            else:
                parsing_error = parse_result.error
                logger.error(
                    f"JSON parsing failed for Groq response. "
                    f"Error: {parse_result.error_type} - {parse_result.error}"
                )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=data.get("model", model or self._settings.model),
            provider=self.provider.value,
            input_tokens=usage.get("prompt_tokens", len(prompt) // 4),
            output_tokens=usage.get("completion_tokens", len(content) // 4),
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            is_fallback=True
        )

    async def embed(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """Groq does not support embeddings - raise error."""
        raise NotImplementedError("Groq does not support embeddings")




class OpenAILLMClient(BaseLLMClient):
    """OpenAI API client."""

    provider = LLMProvider.OPENAI

    def __init__(self):
        self._settings = get_settings().openai
        self._session: Optional[aiohttp.ClientSession] = None

    def is_available(self) -> bool:
        """Check if OpenAI is configured."""
        return bool(self._settings.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.api_key}"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using OpenAI API with optional JSON schema enforcement."""
        start_time = time.monotonic()
        session = await self._get_session()

        # Enhance prompt with JSON schema if provided
        enhanced_prompt = prompt
        if json_schema and parse_json:
            schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
            enhanced_prompt = f"""{prompt}

IMPORTANT: You MUST respond with valid JSON matching this exact schema:
```json
{schema_str}
```

Rules:
1. Output ONLY valid JSON, no markdown, no explanations
2. All required fields must be present
3. Use exact field names and types from schema
4. Ensure proper JSON syntax (commas, quotes, brackets)"""

        payload = {
            "model": model or self._settings.model,
            "messages": [{"role": "user", "content": enhanced_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Force JSON mode if parse_json is True
        if parse_json:
            payload["response_format"] = {"type": "json_object"}

        timeout = self._settings.timeout
        logger.debug(f"Calling OpenAI with timeout={timeout}s, json_mode={parse_json}, schema={'provided' if json_schema else 'none'}")

        try:
            async with session.post(
                self._settings.api_url,
                json=payload,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError:
            logger.error(f"OpenAI request timed out after {timeout}s")
            raise

        content = data["choices"][0]["message"]["content"]
        latency_ms = int((time.monotonic() - start_time) * 1000)
        usage = data.get("usage", {})

        parsed_json = None
        parsing_error = None
        if parse_json:
            parse_result = self._try_parse_json(content)
            if parse_result.success:
                parsed_json = parse_result.data
            else:
                parsing_error = parse_result.error
                logger.error(
                    f"JSON parsing failed for OpenAI response. "
                    f"Error: {parse_result.error_type} - {parse_result.error}"
                )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=data.get("model", model or self._settings.model),
            provider=self.provider.value,
            input_tokens=usage.get("prompt_tokens", len(prompt) // 4),
            output_tokens=usage.get("completion_tokens", len(content) // 4),
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            is_fallback=True
        )

    async def embed(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """Generate embedding using OpenAI."""
        start_time = time.monotonic()
        session = await self._get_session()

        payload = {
            "model": model or self._settings.embedding_model,
            "input": text
        }
        
        timeout = self._settings.timeout
        logger.debug(f"Calling OpenAI embedding with timeout={timeout}s")

        try:
            async with session.post(
                self._settings.embedding_api_url,
                json=payload,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError:
            logger.error(f"OpenAI embedding request timed out after {timeout}s")
            raise

        latency_ms = int((time.monotonic() - start_time) * 1000)
        embedding = data["data"][0]["embedding"]

        return EmbeddingResponse(
            embedding=embedding,
            model=data.get("model", model or self._settings.embedding_model),
            provider=self.provider.value,
            input_tokens=data.get("usage", {}).get("prompt_tokens", len(text) // 4),
            latency_ms=latency_ms,
            dimensions=len(embedding)
        )


class AzureOpenAILLMClient(BaseLLMClient):
    """Azure OpenAI API client using openai.AzureOpenAI."""

    provider = LLMProvider.AZURE_OPENAI

    # Models that don't support temperature parameter (only default=1 allowed)
    # - o-series: reasoning models (o1, o3, o4-mini, etc.)
    # - gpt-5 series: gpt-5-mini, etc.
    _TEMPERATURE_UNSUPPORTED_PREFIXES = ('o1', 'o3', 'o4', 'gpt-5')

    def __init__(self):
        self._settings = get_settings().azure_openai
        self._client = None

    def _is_temperature_unsupported(self, deployment: str) -> bool:
        """Check if the deployment does not support temperature parameter."""
        name = deployment.lower().strip()
        for prefix in self._TEMPERATURE_UNSUPPORTED_PREFIXES:
            if name == prefix or name.startswith(prefix + '-') or name.startswith(prefix + ' '):
                return True
        return False

    def is_available(self) -> bool:
        """Check if Azure OpenAI is configured."""
        return bool(self._settings.azure_endpoint and self._settings.api_key)

    def _get_client(self):
        """Get or create AzureOpenAI client."""
        if self._client is None:
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                azure_endpoint=self._settings.azure_endpoint,
                api_key=self._settings.api_key,
                api_version=self._settings.api_version
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using Azure OpenAI API with optional JSON schema enforcement."""
        start_time = time.monotonic()
        client = self._get_client()

        # Use deployment name from settings (Azure uses deployment, not model)
        deployment = model or self._settings.deployment

        # Enhance prompt with JSON instruction
        # json_schema strict 모드: API가 구조를 강제하므로 프롬프트에 스키마 삽입 불필요
        # json_object 모드: Azure OpenAI requires "json" word in prompt
        enhanced_prompt = prompt
        if parse_json and not json_schema:
            if "json" not in prompt.lower():
                enhanced_prompt = f"{prompt}\n\nRespond with valid JSON only."

        messages = [{"role": "user", "content": enhanced_prompt}]

        # Add system message for structured output guidance (가이드 권장)
        if parse_json:
            messages.insert(0, {
                "role": "system",
                "content": (
                    "You are a review analyzer. "
                    "Always respond in Korean. "
                    "Output only valid JSON matching the requested schema."
                )
            })

        # Build request kwargs
        request_kwargs = {
            "model": deployment,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }

        # Models that don't support temperature (o-series, gpt-5-series)
        # Only the default value (1) is allowed, so we omit it entirely
        if self._is_temperature_unsupported(deployment):
            logger.debug(f"Temperature unsupported for {deployment}: skipping temperature parameter")
        else:
            request_kwargs["temperature"] = temperature

        # Force JSON mode if parse_json is True
        if parse_json:
            if json_schema:
                # Structured Output: json_schema + strict (가이드 권장 패턴)
                # gpt-5-mini / o4-mini 모두 지원, 구조 100% 보장
                request_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "AnalysisResult",
                        "strict": True,
                        "schema": json_schema,
                    },
                }
                logger.debug(f"Using json_schema strict mode for structured output")
            else:
                # Fallback: json_object (스키마 미제공 시)
                request_kwargs["response_format"] = {"type": "json_object"}

        timeout = self._settings.timeout
        logger.debug(f"Calling Azure OpenAI with deployment={deployment}, timeout={timeout}s, json_mode={parse_json}")

        try:
            # Use asyncio.to_thread for async compatibility (AzureOpenAI is sync)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                **request_kwargs
            )
        except asyncio.TimeoutError:
            logger.error(f"Azure OpenAI request timed out after {timeout}s")
            raise
        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__

            # Check for rate limit (HTTP 429)
            if "429" in error_str or "rate limit" in error_str.lower() or error_type == "RateLimitError":
                # Parse retry_after from error message
                # Azure OpenAI format: "Retry after X seconds" or "retry-after: X"
                retry_after = None
                retry_match = re.search(r'[Rr]etry[- ]?after[:\s]+(\d+(?:\.\d+)?)', error_str)
                if retry_match:
                    retry_after = float(retry_match.group(1))
                else:
                    # Default retry after 60 seconds if not specified
                    retry_after = 60.0

                logger.warning(f"Azure OpenAI HTTP 429: {error_str[:200]}, retry_after={retry_after}s")
                raise AzureRateLimitError(
                    model=deployment,
                    retry_after=retry_after,
                    message=error_str[:500]
                )

            logger.error(f"Azure OpenAI request failed: {error_type}: {e}")
            raise

        content = response.choices[0].message.content
        latency_ms = int((time.monotonic() - start_time) * 1000)
        usage = response.usage

        # gpt-5-mini: content가 None/빈 문자열인 경우 방어
        if not content or not content.strip():
            logger.warning(
                f"Azure OpenAI returned empty content for {deployment} "
                f"(tokens: in={usage.prompt_tokens if usage else 0}, out={usage.completion_tokens if usage else 0})"
            )
            if parse_json:
                raise ValueError(f"Empty response from {deployment} - cannot parse JSON")
            content = content or ""

        parsed_json = None
        parsing_error = None
        if parse_json:
            parse_result = self._try_parse_json(content)
            if parse_result.success:
                parsed_json = parse_result.data
            else:
                parsing_error = parse_result.error
                logger.error(
                    f"JSON parsing failed for Azure OpenAI response. "
                    f"Error: {parse_result.error_type} - {parse_result.error}"
                )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=response.model if hasattr(response, 'model') else deployment,
            provider=self.provider.value,
            input_tokens=usage.prompt_tokens if usage else len(prompt) // 4,
            output_tokens=usage.completion_tokens if usage else len(content) // 4,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            is_fallback=True
        )

    async def embed(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """Azure OpenAI embedding - not configured for this deployment."""
        raise NotImplementedError("Azure OpenAI embedding not configured for this deployment")


class UnifiedLLMClient:
    """
    Unified LLM client with automatic fallback support.
    Fallback order: Groq (primary with 5-key rotation) -> Ollama -> OpenAI
    """

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        llm_config: Optional[LLMConfig] = None,
        key_rotator = None,
        groq_key_rotator = None
    ):
        self._config = llm_config or get_llm_config()
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._key_rotator = key_rotator
        self._groq_key_rotator = groq_key_rotator

        # Initialize all available clients
        self._clients: Dict[LLMProvider, BaseLLMClient] = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize all available LLM clients."""
        # Initialize Gemini client with key rotator
        gemini_client_init = lambda: GeminiLLMClient(self._key_rotator)
        # Initialize Groq client with key rotator
        groq_client_init = lambda: GroqLLMClient(self._groq_key_rotator)

        client_classes = {
            LLMProvider.GEMINI: gemini_client_init,
            LLMProvider.OLLAMA: OllamaLLMClient,
            LLMProvider.GROQ: groq_client_init,
            LLMProvider.OPENAI: OpenAILLMClient,
            LLMProvider.AZURE_OPENAI: AzureOpenAILLMClient,
        }

        for provider, client_class in client_classes.items():
            try:
                client = client_class()
                if client.is_available():
                    self._clients[provider] = client
                    logger.info(f"LLM provider initialized: {provider.value}")
                else:
                    logger.debug(f"LLM provider not configured: {provider.value}")
            except Exception as e:
                logger.warning(f"Failed to initialize {provider.value}: {e}")

    def _get_available_providers(self) -> List[LLMProvider]:
        """Get list of available providers based on configuration and settings."""
        available = []
        
        # Get configured order from settings
        configured_order = get_settings().llm_fallback_order
        
        # Map string to enum
        provider_map = {
            'gemini': LLMProvider.GEMINI,
            'ollama': LLMProvider.OLLAMA,
            'groq': LLMProvider.GROQ,
            'openai': LLMProvider.OPENAI,
            'azure_openai': LLMProvider.AZURE_OPENAI
        }
        
        for provider_str in configured_order:
            provider_enum = provider_map.get(provider_str.lower())
            if provider_enum and provider_enum in self._clients and self._clients[provider_enum].is_available():
                available.append(provider_enum)
                
        if not available:
            logger.warning("No LLM providers configured! Checking defaults...")
            # Fallback to hardcoded default if nothing matches
            default_order = [
                LLMProvider.GEMINI,
                LLMProvider.OLLAMA,
                LLMProvider.GROQ,
                LLMProvider.OPENAI
            ]
            for p in default_order:
                if p in self._clients and self._clients[p].is_available():
                    available.append(p)
                    
        return available

    async def generate(
        self,
        prompt: str,
        task_type: str,
        generation_params: Optional[Dict[str, Any]] = None,
        parse_json: bool = True,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate text with automatic fallback to next provider on failure.

        Args:
            prompt: Input prompt
            task_type: Task type for model selection
            generation_params: Override generation parameters
            parse_json: Whether to parse response as JSON
            json_schema: Optional Pydantic JSON schema for response validation

        Returns:
            LLMResponse with generated content
        """
        mapping = self._config.task_mappings.get(task_type)
        if not mapping:
            raise ValueError(f"Unknown task type: {task_type}")

        params = {
            "temperature": mapping.temperature,
            "max_tokens": mapping.max_output_tokens,
            "parse_json": parse_json,
            "json_schema": json_schema  # NEW: Pass schema to provider clients
        }
        if generation_params:
            params.update(generation_params)

        available_providers = self._get_available_providers()
        if not available_providers:
            raise RuntimeError("No LLM providers available")

        last_error = None

        for provider in available_providers:
            client = self._clients[provider]
            model = self._get_model_for_provider(provider, task_type)

            try:
                logger.debug(f"Attempting generation with {provider.value}")
                
                # Log current Gemini key and model being used
                if provider == LLMProvider.GEMINI and self._key_rotator:
                    current_key_idx = self._key_rotator.get_current_index()
                    current_model_idx = self._key_rotator.get_current_model_index()
                    current_model = self._key_rotator.get_current_model()
                    total_keys = self._key_rotator.get_key_count()
                    total_models = self._key_rotator.get_model_count()
                    logger.info(
                        f"→ Using Gemini: key {current_key_idx}/{total_keys}, "
                        f"model {current_model_idx}/{total_models} ({current_model})"
                    )

                # Apply rate limiting for Gemini
                if provider == LLMProvider.GEMINI and self._rate_limiter:
                    if self._key_rotator:
                        # Check current key's rate limit
                        key_index = self._key_rotator.get_current_index()
                        try:
                            # Use key-specific rate limit check
                            rpm_allowed, _ = await self._rate_limiter.check_rpm_limit(model, key_index)
                            rpd_allowed, _ = await self._rate_limiter.check_rpd_limit(model, key_index)
                            
                            if not rpm_allowed or not rpd_allowed:
                                logger.warning(f"Rate limit for Gemini key {key_index}, rotating to next key")
                                self._key_rotator.rotate_to_next_key()
                                client.reinitialize_with_new_key()
                                
                                # Increment new key's counter
                                new_key_index = self._key_rotator.get_current_index()
                                await self._rate_limiter.increment_counters(model, new_key_index)
                            else:
                                # Increment current key's counter
                                await self._rate_limiter.increment_counters(model, key_index)
                        except Exception as e:
                            logger.warning(f"Rate limit check failed: {e}")
                    else:
                        try:
                            await self._rate_limiter.wait_and_acquire(model, timeout=10.0)
                        except RateLimitExceeded:
                            logger.warning(f"Rate limit exceeded for {provider.value}, trying next provider")
                            continue

                # Apply rate limiting for Azure OpenAI
                if provider == LLMProvider.AZURE_OPENAI and self._rate_limiter:
                    azure_settings = get_settings().azure_openai
                    rpm_limit = azure_settings.rpm_limit

                    # Check retry_after first (API-enforced cooldown)
                    # key_index=0 since Azure OpenAI uses single key
                    if not self._rate_limiter.is_retry_allowed('azure_openai', model, 0):
                        remaining = self._rate_limiter.get_retry_after('azure_openai', model, 0)
                        logger.warning(
                            f"Azure OpenAI still blocked for {remaining:.1f}s "
                            f"(retry_after from API), skipping to Ollama"
                        )
                        continue  # Skip to next provider (Ollama)

                    # Check Redis RPM limit before request
                    rpm_allowed, rpm_count = await self._rate_limiter.check_rpm_limit(model, 0, rpm_limit)

                    if not rpm_allowed:
                        from datetime import datetime
                        now = datetime.now()
                        seconds_until_next_minute = 60 - now.second
                        self._rate_limiter.set_retry_after('azure_openai', model, 0, seconds_until_next_minute)
                        logger.warning(
                            f"Azure OpenAI RPM limit ({rpm_count}/{rpm_limit}), "
                            f"waiting {seconds_until_next_minute}s, falling back to Ollama"
                        )
                        continue  # Skip to next provider (Ollama)

                    # Increment counter before request
                    await self._rate_limiter.increment_counters(model, 0)
                    logger.debug(f"Azure OpenAI RPM: {rpm_count + 1}/{rpm_limit}")

                # Apply rate limiting for Groq
                if provider == LLMProvider.GROQ and self._groq_key_rotator:
                    current_key_idx = self._groq_key_rotator.get_current_index()
                    total_keys = self._groq_key_rotator.get_key_count()
                    logger.info(f"→ Using Groq key {current_key_idx + 1}/{total_keys}")

                    # Check retry_after first (API-enforced cooldown)
                    if self._rate_limiter and not self._rate_limiter.is_retry_allowed('groq', model, current_key_idx):
                        remaining = self._rate_limiter.get_retry_after('groq', model, current_key_idx)
                        logger.warning(
                            f"Groq key {current_key_idx} still blocked for {remaining:.1f}s "
                            f"(retry_after from API), skipping to next provider"
                        )
                        continue  # Skip to next provider (Ollama)

                    # Check Redis RPM/RPD limits before request
                    if self._rate_limiter:
                        rpm_allowed, rpm_count = await self._rate_limiter.check_rpm_limit(model, current_key_idx)
                        rpd_allowed, rpd_count = await self._rate_limiter.check_rpd_limit(model, current_key_idx)

                        if not rpm_allowed:
                            logger.warning(f"Groq key {current_key_idx} RPM limit ({rpm_count}/30), rotating")
                            # Set retry_after to next minute (when RPM resets)
                            if self._rate_limiter:
                                import time
                                from datetime import datetime
                                now = datetime.now()
                                seconds_in_minute = now.second
                                seconds_until_next_minute = 60 - seconds_in_minute
                                self._rate_limiter.set_retry_after('groq', model, current_key_idx, seconds_until_next_minute)
                                logger.info(f"Set retry_after for Groq key {current_key_idx} for {seconds_until_next_minute}s (RPM reset)")
                            self._groq_key_rotator.rotate_to_next_key()
                            continue  # Skip to next provider iteration

                        if not rpd_allowed:
                            logger.warning(f"Groq key {current_key_idx} RPD limit ({rpd_count}/1000), rotating")
                            # Set retry_after to midnight (when RPD resets)
                            if self._rate_limiter:
                                seconds_until_midnight = self._rate_limiter._seconds_until_midnight()
                                self._rate_limiter.set_retry_after('groq', model, current_key_idx, seconds_until_midnight)
                                logger.info(f"Set retry_after for Groq key {current_key_idx} until midnight ({seconds_until_midnight:.0f}s)")
                            self._groq_key_rotator.rotate_to_next_key()
                            continue

                        # Increment counters before request
                        await self._rate_limiter.increment_counters(model, current_key_idx)

                response = await client.generate(
                    prompt=prompt,
                    model=model,
                    **params
                )

                if provider != LLMProvider.GEMINI:
                    response.is_fallback = True

                # Check if JSON parsing was required but failed
                if parse_json and response.parsed_json is None:
                    raise ValueError(f"Failed to parse JSON response from {provider.value}")

                logger.info(f"Generated response using {provider.value}/{model}")
                return response

            except RateLimitError as e:
                # Handle Groq HTTP 429 rate limit error
                if provider == LLMProvider.GROQ and self._groq_key_rotator:
                    current_key_idx = self._groq_key_rotator.get_current_index()
                    logger.warning(f"Groq HTTP 429 on key {current_key_idx}: {e.message}")

                    # Debug: Check retry_after and rate_limiter availability
                    logger.debug(f"DEBUG: retry_after={e.retry_after}, rate_limiter={self._rate_limiter is not None}")

                    # Store retry_after in Redis
                    if e.retry_after and self._rate_limiter:
                        self._rate_limiter.set_retry_after('groq', model, current_key_idx, e.retry_after)
                    elif not e.retry_after:
                        logger.warning(f"retry_after is None or 0, cannot store to Redis")
                    elif not self._rate_limiter:
                        logger.warning(f"rate_limiter is None, cannot store retry_after")

                    # Try all keys sequentially
                    total_keys = self._groq_key_rotator.get_key_count()
                    for retry in range(total_keys - 1):  # Already tried current key
                        self._groq_key_rotator.rotate_to_next_key()
                        new_key_idx = self._groq_key_rotator.get_current_index()

                        # Check if new key is still blocked by retry_after
                        if self._rate_limiter and not self._rate_limiter.is_retry_allowed('groq', model, new_key_idx):
                            remaining = self._rate_limiter.get_retry_after('groq', model, new_key_idx)
                            logger.info(f"Groq key {new_key_idx} blocked for {remaining:.1f}s, skipping")
                            continue

                        logger.info(f"Retry {retry + 2}/{total_keys} with Groq key {new_key_idx}")

                        try:
                            response = await client.generate(prompt=prompt, model=model, **params)
                            logger.info(f"✓ Success with Groq key {new_key_idx}")
                            return response
                        except RateLimitError as retry_error:
                            # Debug: Check retry_after for this retry
                            logger.debug(f"DEBUG (retry): retry_after={retry_error.retry_after}, rate_limiter={self._rate_limiter is not None}")

                            # Store retry_after for this key too
                            if retry_error.retry_after and self._rate_limiter:
                                self._rate_limiter.set_retry_after('groq', model, new_key_idx, retry_error.retry_after)
                            elif not retry_error.retry_after:
                                logger.warning(f"retry_after is None or 0 for key {new_key_idx}, cannot store to Redis")
                            elif not self._rate_limiter:
                                logger.warning(f"rate_limiter is None for key {new_key_idx}, cannot store retry_after")

                            logger.warning(f"Groq key {new_key_idx} also rate limited")
                            continue  # Try next key

                    # All keys exhausted or blocked
                    logger.error(f"All {total_keys} Groq keys rate limited → falling back to next provider")
                    last_error = e
                    continue  # Try next provider (Ollama)
                else:
                    # RateLimitError from non-Groq provider, re-raise as Exception
                    last_error = e
                    continue

            except AzureRateLimitError as e:
                # Handle Azure OpenAI HTTP 429 rate limit error
                logger.warning(f"Azure OpenAI HTTP 429: {e.message[:200]}")

                # Store retry_after in Redis
                if e.retry_after and self._rate_limiter:
                    self._rate_limiter.set_retry_after('azure_openai', model, 0, e.retry_after)
                    logger.info(f"Set retry_after for Azure OpenAI: {e.retry_after:.0f}s")

                last_error = e
                continue  # Skip to next provider (Ollama)

            except Exception as e:
                # Handle Gemini errors with two-tier rotation (model first, then key)
                if provider == LLMProvider.GEMINI and self._key_rotator:
                    from datetime import datetime, timedelta
                    import re
                    
                    # Get current state
                    current_key_idx = self._key_rotator.get_current_index()
                    current_model_idx = self._key_rotator.get_current_model_index()
                    current_model_name = self._key_rotator.get_current_model()
                    
                    logger.warning(f"Gemini error on key {current_key_idx}, model {current_model_name}: {str(e)[:150]}")
                    
                    # Parse retry_delay from error message (if 429)
                    retry_seconds = None
                    retry_until_str = ""
                    error_str = str(e)
                    
                    if "429" in error_str:
                        retry_match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_str, re.DOTALL)
                        if retry_match:
                            retry_seconds = int(retry_match.group(1))
                            retry_until = datetime.now() + timedelta(seconds=retry_seconds)
                            retry_until_str = f" (retry until {retry_until.strftime('%Y/%m/%d %H:%M:%S')})"
                        logger.warning(f"Rate limit 429 detected{retry_until_str}")
                    
                    # Two-tier rotation strategy info
                    settings = get_settings()
                    
                    max_models = self._key_rotator.get_model_count()
                    max_keys = self._key_rotator.get_key_count()
                    max_total_retries = settings.gemini.max_retries  # 200 by default
                    total_capacity = max_keys * max_models
                    
                    logger.info(
                        f"Starting rotation: {max_keys} keys × {max_models} models = {total_capacity} attempts, "
                        f"max retries: {max_total_retries}"
                    )
                    
                    total_retries = 0
                    
                    while total_retries < max_total_retries:
                        try:
                            # Determine whether to rotate model or key
                            # Inner loop: Try all models with current key
                            # Outer loop: After all models fail, rotate key and reset to first model
                            
                            attempts_with_current_key = total_retries % max_models
                            
                            if attempts_with_current_key == 0 and total_retries > 0:
                                # Exhausted all models, rotate to next key
                                prev_key_idx = self._key_rotator.get_current_index()
                                new_key, new_model = self._key_rotator.rotate_to_next_key()
                                client.reinitialize_with_new_key()
                                key_idx = self._key_rotator.get_current_index()
                                
                                cycle_num = (total_retries // (max_models * max_keys)) + 1
                                iteration = (total_retries // max_models) + 1
                                logger.info(
                                    f"→ KEY rotation: {prev_key_idx} → {key_idx}, reset to model: {new_model} "
                                    f"(iteration {iteration}, cycle {cycle_num})"
                                )
                            else:
                                # Rotate to next model (keep same key)
                                prev_model = self._key_rotator.get_current_model()
                                current_key, new_model = self._key_rotator.rotate_to_next_model()
                                key_idx = self._key_rotator.get_current_index()
                                
                                logger.info(
                                    f"→ MODEL rotation: {prev_model} → {new_model} (key {key_idx})"
                                )
                            
                            # Try with rotated model/key
                            response = await client.generate(
                                prompt=prompt,
                                model=new_model,
                                **params
                            )
                            
                            # Check JSON if needed
                            if parse_json and response.parsed_json is None:
                                raise ValueError(f"Failed to parse JSON response")
                            
                            logger.info(f"✓ Success with key {key_idx}, model: {new_model}")
                            return response
                            
                        except Exception as retry_error:
                            total_retries += 1
                            error_type = "429" if "429" in str(retry_error) else "other"
                            
                            key_idx = self._key_rotator.get_current_index()
                            model_name = self._key_rotator.get_current_model()
                            
                            logger.warning(
                                f"✗ Retry {total_retries}/{max_total_retries}: key {key_idx}, model {model_name} "
                                f"failed ({error_type})"
                            )
                            
                            # Log progress milestones
                            if total_retries % max_models == 0:
                                completed_keys = total_retries // max_models
                                logger.info(f"Completed all {max_models} models for {completed_keys} key(s)")
                            
                            if total_retries < max_total_retries:
                                continue
                            else:
                                # Exhausted all retries
                                break
                    
                    # All retries exhausted
                    total_keys_tried = (total_retries // max_models) + (1 if total_retries % max_models > 0 else 0)
                    logger.error(
                        f"Gemini rotation exhausted: {total_retries} attempts "
                        f"({total_keys_tried} keys × {max_models} models)"
                    )
                    raise RuntimeError(
                        f"All Gemini models and keys exhausted after {total_retries} attempts"
                    )
                
                # Content filter errors should NOT be retried with other providers
                # These are content-based rejections that will fail regardless of provider
                error_str = str(e)
                if 'content_filter' in error_str or 'ResponsibleAIPolicyViolation' in error_str:
                    logger.warning(f"Content filter error - not retrying with other providers: {error_str[:200]}")
                    raise RuntimeError(f"content_filter: {error_str}")

                last_error = e
                logger.warning(f"Generation failed with {provider.value}: {e}")
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def generate_with_retry(
        self,
        prompt: str,
        task_type: str,
        max_retries: int = 3,
        **kwargs
    ) -> LLMResponse:
        """Generate with automatic retry on transient failures."""
        retry_config = self._config.retry_config
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.generate(prompt, task_type, **kwargs)
            except RuntimeError:
                # All providers failed - retry if it might be transient (e.g. JSON error)
                # If it's a configuration error, it will likely fail again, but we rely on max_retries
                pass
            except Exception as e:
                last_error = e
                delay = retry_config.get('initial_delay_seconds', 1.0) * (
                    retry_config.get('backoff_multiplier', 2.0) ** attempt
                )
                delay = min(delay, retry_config.get('max_delay_seconds', 16.0))
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                await asyncio.sleep(delay)

        raise last_error

    async def embed(
        self,
        text: Union[str, List[str]],
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> Union[EmbeddingResponse, List[EmbeddingResponse]]:
        """
        Generate embeddings with automatic fallback.

        Args:
            text: Text or list of texts to embed
            task_type: Embedding task type

        Returns:
            EmbeddingResponse or list of EmbeddingResponse
        """
        # Embedding providers (Groq doesn't support embeddings)
        embedding_providers = [
            p for p in self._get_available_providers()
            if p != LLMProvider.GROQ
        ]

        if not embedding_providers:
            raise RuntimeError("No embedding providers available")

        if isinstance(text, str):
            texts = [text]
            single = True
        else:
            texts = text
            single = False

        last_error = None

        for provider in embedding_providers:
            client = self._clients[provider]
            model = self._get_embedding_model_for_provider(provider)

            try:
                results = []
                for t in texts:
                    response = await client.embed(
                        text=t,
                        model=model,
                        task_type=task_type
                    )
                    results.append(response)

                logger.info(f"Generated embeddings using {provider.value}/{model}")
                return results[0] if single else results

            except NotImplementedError:
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"Embedding failed with {provider.value}: {e}")
                continue

        raise RuntimeError(f"All embedding providers failed. Last error: {last_error}")

    def _get_model_for_provider(self, provider: LLMProvider, task_type: str) -> str:
        """Get the model name for a specific provider and task."""
        settings = get_settings()

        if provider == LLMProvider.GEMINI:
            mapping = self._config.task_mappings.get(task_type)
            return mapping.primary_model if mapping else "gemini-2.0-flash"
        elif provider == LLMProvider.OLLAMA:
            return settings.ollama.model
        elif provider == LLMProvider.GROQ:
            return settings.groq.model
        elif provider == LLMProvider.OPENAI:
            return settings.openai.model
        elif provider == LLMProvider.AZURE_OPENAI:
            return settings.azure_openai.deployment

        return "unknown"

    def _get_embedding_model_for_provider(self, provider: LLMProvider) -> str:
        """Get the embedding model name for a specific provider."""
        settings = get_settings()

        if provider == LLMProvider.GEMINI:
            return settings.gemini.model_embedding
        elif provider == LLMProvider.OLLAMA:
            return settings.ollama.embedding_model
        elif provider == LLMProvider.OPENAI:
            return settings.openai.embedding_model

        return "unknown"


# Backward compatibility aliases
GeminiClient = UnifiedLLMClient


# Singleton instance
_llm_client: Optional[UnifiedLLMClient] = None


def get_llm_client() -> UnifiedLLMClient:
    """
    Get unified LLM client instance.

    Note: Returns a new instance each time to avoid event loop binding issues
    in Flask's async context (run_async creates new loops).
    """
    from app.core.api_key_rotator import get_gemini_key_rotator
    from app.core.groq_key_rotator import get_groq_key_rotator
    from app.config.settings import get_settings

    settings = get_settings()

    # Initialize Gemini key rotator if multiple keys available
    key_rotator = None
    if settings.gemini.api_keys and len(settings.gemini.api_keys) > 1:
        key_rotator = get_gemini_key_rotator(
            api_keys=settings.gemini.api_keys,
            models=settings.gemini.rotation_models
        )

    # Initialize Groq key rotator if 1-5 keys available
    groq_key_rotator = None
    if settings.groq.api_keys and 1 <= len(settings.groq.api_keys) <= 5:
        groq_key_rotator = get_groq_key_rotator(
            api_keys=settings.groq.api_keys,
            model=settings.groq.model
        )

    return UnifiedLLMClient(
        key_rotator=key_rotator,
        groq_key_rotator=groq_key_rotator
    )


# Backward compatibility
def get_gemini_client() -> UnifiedLLMClient:
    """Get singleton LLM client (backward compatibility)."""
    return get_llm_client()
