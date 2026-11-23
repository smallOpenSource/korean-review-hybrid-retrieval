"""
Application settings loaded from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)


def _parse_bool(value: str) -> bool:
    """Parse string to boolean."""
    return value.lower() in ('true', '1', 'yes', 'on')


def _parse_list(value: str, separator: str = ',') -> List[str]:
    """Parse comma-separated string to list."""
    if not value:
        return []
    return [item.strip() for item in value.split(separator) if item.strip()]


@dataclass
class FlaskConfig:
    """Flask application configuration."""
    app_name: str = field(default_factory=lambda: os.getenv('FLASK_APP', 'pybo'))
    env: str = field(default_factory=lambda: os.getenv('FLASK_ENV', 'development'))
    debug: bool = field(default_factory=lambda: _parse_bool(os.getenv('FLASK_DEBUG', 'false')))
    secret_key: str = field(default_factory=lambda: os.getenv('SECRET_KEY', ''))


@dataclass
class MySQLConfig:
    """MySQL database configuration."""
    host: str = field(default_factory=lambda: os.getenv('MYSQL_HOST', '127.0.0.1'))
    port: int = field(default_factory=lambda: int(os.getenv('MYSQL_PORT', '3306')))
    user: str = field(default_factory=lambda: os.getenv('MYSQL_USER', ''))
    password: str = field(default_factory=lambda: os.getenv('MYSQL_PASSWORD', ''))
    database: str = field(default_factory=lambda: os.getenv('MYSQL_DATABASE', 'summary'))
    charset: str = field(default_factory=lambda: os.getenv('MYSQL_CHARSET', 'utf8mb4'))

    @property
    def connection_string(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?charset={self.charset}"


@dataclass
class OpenSearchConfig:
    """OpenSearch configuration with SSL and authentication."""
    hosts: List[str] = field(default_factory=lambda: _parse_list(os.getenv('OPENSEARCH_HOSTS', 'https://localhost:9200')))
    user: str = field(default_factory=lambda: os.getenv('OPENSEARCH_USER', ''))
    password: str = field(default_factory=lambda: os.getenv('OPENSEARCH_PASSWORD', ''))
    ssl_verify: bool = field(default_factory=lambda: _parse_bool(os.getenv('OPENSEARCH_SSL_VERIFY', 'false')))
    index_reviews: str = field(default_factory=lambda: os.getenv('OPENSEARCH_INDEX_REVIEWS', 'app_reviews'))
    index_analytics: str = field(default_factory=lambda: os.getenv('OPENSEARCH_INDEX_ANALYTICS', 'review_analytics'))

    @property
    def http_auth(self) -> tuple:
        return (self.user, self.password)


@dataclass
class RedisSentinelConfig:
    """Redis Sentinel configuration."""
    sentinel_hosts: List[str] = field(default_factory=lambda: _parse_list(os.getenv('REDIS_SENTINEL_HOSTS', 'localhost:26379')))
    master_name: str = field(default_factory=lambda: os.getenv('REDIS_SENTINEL_MASTER_NAME', 'mymaster'))
    password: Optional[str] = field(default_factory=lambda: os.getenv('REDIS_SENTINEL_PASSWORD') or None)
    db: int = field(default_factory=lambda: int(os.getenv('REDIS_DB', '0')))
    socket_timeout: float = field(default_factory=lambda: float(os.getenv('REDIS_SOCKET_TIMEOUT', '5')))

    @property
    def sentinel_list(self) -> List[tuple]:
        """Parse sentinel hosts to list of tuples (host, port)."""
        result = []
        for host_port in self.sentinel_hosts:
            if ':' in host_port:
                host, port = host_port.rsplit(':', 1)
                result.append((host, int(port)))
            else:
                result.append((host_port, 26379))
        return result


@dataclass
class GeminiConfig:
    """Gemini LLM configuration."""
    api_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''))
    api_keys: List[str] = field(default_factory=list)
    project_id: str = field(default_factory=lambda: os.getenv('GEMINI_PROJECT_ID', ''))

    # Primary models
    model_realtime: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_REALTIME', 'gemini-2.0-flash'))
    model_insight: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_INSIGHT', 'gemini-1.5-pro'))
    model_query: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_QUERY', 'gemini-2.5-flash'))
    model_embedding: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_EMBEDDING', 'gemini-embedding-001'))

    # Secondary models (for rate limit scenarios)
    model_realtime_secondary: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_REALTIME_SECONDARY', ''))
    model_insight_secondary: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_INSIGHT_SECONDARY', ''))
    model_query_secondary: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_QUERY_SECONDARY', 'gemini-2.0-flash'))

    # Timeouts
    timeout: int = field(default_factory=lambda: int(os.getenv('GEMINI_TIMEOUT', '30')))
    
    # API Key Rotation
    max_retries: int = field(default_factory=lambda: int(os.getenv('GEMINI_MAX_RETRIES', '200')))
    
    # Model Rotation (for rate limit handling)
    rotation_models: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Load multiple API keys and rotation models from environment."""
        keys = []
        
        # Method 1: GEMINI_API_KEYS (comma-separated)
        keys_str = os.getenv('GEMINI_API_KEYS', '')
        if keys_str:
            keys = _parse_list(keys_str)
        
        # Method 2: GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc
        if not keys:
            for i in range(1, 11):  # Support up to 10 keys
                key = os.getenv(f'GEMINI_API_KEY_{i}', '')
                if key:
                    keys.append(key)
        
        # Fallback to single api_key if no multi-keys
        if not keys and self.api_key:
            keys = [self.api_key]
        
        self.api_keys = keys
        
        # Load rotation models from environment
        models_str = os.getenv('GEMINI_ROTATION_MODELS', '')
        if models_str:
            self.rotation_models = [m.strip() for m in models_str.split(',') if m.strip()]
        else:
            # Default rotation order (fastest to most capable)
            self.rotation_models = [
                'gemini-2.0-flash-lite',
                'gemini-2.0-flash',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash',
                'gemini-2.5-pro'
            ]


@dataclass
class OllamaConfig:
    """Ollama LLM configuration (fallback provider #1)."""
    base_url: str = field(default_factory=lambda: os.getenv('OLLAMA_BASE_URL', ''))
    base_urls: List[str] = field(default_factory=list)  # Multiple endpoints for load balancing
    api_key: str = field(default_factory=lambda: os.getenv('OLLAMA_API_KEY', ''))  # Bearer token
    model: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'llama3.1'))
    embedding_model: str = field(default_factory=lambda: os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text'))
    timeout: int = field(default_factory=lambda: int(os.getenv('OLLAMA_TIMEOUT', '60')))
    
    # Load balancing
    _current_index: int = field(default=0, init=False, repr=False)
    
    def __post_init__(self):
        """Load multiple Ollama base URLs from environment."""
        urls = []
        
        # Method 1: OLLAMA_BASE_URLS (comma-separated)
        urls_str = os.getenv('OLLAMA_BASE_URLS', '')
        if urls_str:
            urls = _parse_list(urls_str)
        
        # Method 2: Fallback to single OLLAMA_BASE_URL
        if not urls and self.base_url:
            urls = [self.base_url]
        
        self.base_urls = urls
    
    def get_endpoint(self) -> str:
        """Get next endpoint using round-robin load balancing."""
        if not self.base_urls:
            return self.base_url
        
        # Round-robin selection
        endpoint = self.base_urls[self._current_index % len(self.base_urls)]
        self._current_index += 1
        return endpoint


@dataclass
class GroqConfig:
    """Groq LLM configuration (PRIMARY provider with 5-key rotation)."""
    api_key: str = field(default_factory=lambda: os.getenv('GROQ_API_KEY', ''))
    api_keys: List[str] = field(default_factory=list)  # Multi-key support
    api_url: str = field(default_factory=lambda: os.getenv('GROQ_API_URL', 'https://api.groq.com/openai/v1/chat/completions'))
    model: str = field(default_factory=lambda: os.getenv('GROQ_MODEL', 'meta-llama/llama-4-maverick-17b-128e-instruct'))
    timeout: int = field(default_factory=lambda: int(os.getenv('GROQ_TIMEOUT', '60')))

    def __post_init__(self):
        """Load 5 Groq API keys from environment."""
        keys = []

        # Method 1: GROQ_API_KEYS (comma-separated)
        keys_str = os.getenv('GROQ_API_KEYS', '')
        if keys_str:
            keys = _parse_list(keys_str)

        # Method 2: GROQ_API_KEY_1, GROQ_API_KEY_2, ..., GROQ_API_KEY_5
        if not keys:
            for i in range(1, 6):
                key = os.getenv(f'GROQ_API_KEY_{i}', '')
                if key:
                    keys.append(key)

        # Fallback to single api_key
        if not keys and self.api_key:
            keys = [self.api_key]

        self.api_keys = keys


@dataclass
class OpenAIConfig:
    """OpenAI LLM configuration (fallback provider #3)."""
    api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    api_url: str = field(default_factory=lambda: os.getenv('OPENAI_API_URL', 'https://api.openai.com/v1/chat/completions'))
    embedding_api_url: str = field(default_factory=lambda: os.getenv('OPENAI_EMBEDDING_API_URL', 'https://api.openai.com/v1/embeddings'))
    model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4o-mini'))
    embedding_model: str = field(default_factory=lambda: os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'))
    timeout: int = field(default_factory=lambda: int(os.getenv('OPENAI_TIMEOUT', '60')))


@dataclass
class AzureOpenAIConfig:
    """Azure OpenAI LLM configuration (PRIMARY provider)."""
    azure_endpoint: str = field(default_factory=lambda: os.getenv('AZURE_OPENAI_ENDPOINT', ''))
    api_key: str = field(default_factory=lambda: os.getenv('AZURE_OPENAI_API_KEY', ''))
    api_version: str = field(default_factory=lambda: os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview'))
    deployment: str = field(default_factory=lambda: os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-5-mini'))
    timeout: int = field(default_factory=lambda: int(os.getenv('AZURE_OPENAI_TIMEOUT', '120')))
    # Rate limiting (RPM = Requests Per Minute)
    rpm_limit: int = field(default_factory=lambda: int(os.getenv('AZURE_OPENAI_RPM', '200')))


@dataclass
class LocalEmbeddingConfig:
    """Local embedding model configuration for API unavailability scenarios."""
    model_path: str = field(default_factory=lambda: os.getenv('LOCAL_EMBEDDING_MODEL_PATH', ''))
    device: str = field(default_factory=lambda: os.getenv('LOCAL_EMBEDDING_DEVICE', 'cuda'))


@dataclass
class BGEConfig:
    """BGE Embedding and Rerank configuration."""
    # API Configuration (Primary)
    embedding_api_url: str = field(default_factory=lambda: os.getenv('BGE_EMBEDDING_API_URL', ''))
    embedding_api_key: str = field(default_factory=lambda: os.getenv('BGE_EMBEDDING_API_KEY', ''))
    embedding_model: str = field(default_factory=lambda: os.getenv('BGE_EMBEDDING_MODEL', 'bge-m3:latest'))
    rerank_api_url: str = field(default_factory=lambda: os.getenv('BGE_RERANK_API_URL', ''))
    rerank_api_key: str = field(default_factory=lambda: os.getenv('BGE_RERANK_API_KEY', ''))
    rerank_model: str = field(default_factory=lambda: os.getenv('BGE_RERANK_MODEL', 'xitao/bge-reranker-v2-m3:latest'))

    # Local Model Configuration (Fallback)
    local_embedding_model: str = field(default_factory=lambda: os.getenv('BGE_LOCAL_EMBEDDING_MODEL', 'upskyy/bge-m3-ko'))
    local_rerank_model: str = field(default_factory=lambda: os.getenv('BGE_LOCAL_RERANK_MODEL', 'BAAI/bge-reranker-v2-m3'))
    local_device: str = field(default_factory=lambda: os.getenv('BGE_LOCAL_DEVICE', 'cpu'))
    local_batch_size: int = field(default_factory=lambda: int(os.getenv('BGE_LOCAL_BATCH_SIZE', '32')))
    local_model_cache_dir: str = field(default_factory=lambda: os.getenv('BGE_LOCAL_MODEL_CACHE_DIR', './models'))

    # Embedding dimensions (bge-m3 uses 1024)
    embedding_dimensions: int = field(default_factory=lambda: int(os.getenv('BGE_EMBEDDING_DIMENSIONS', '1024')))

    # API 배치 호출 시 서브배치 크기 (타임아웃 방지)
    embed_batch_dop: int = field(default_factory=lambda: int(os.getenv('EMBED_BATCH_DOP', '10')))


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    enabled: bool = field(default_factory=lambda: _parse_bool(os.getenv('RATE_LIMIT_ENABLED', 'true')))
    tier: str = field(default_factory=lambda: os.getenv('RATE_LIMIT_TIER', 'free'))


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    file_path: str = field(default_factory=lambda: os.getenv('LOG_FILE_PATH', 'logs/app.log'))
    format: str = field(default_factory=lambda: os.getenv('LOG_FORMAT', 'json'))


@dataclass
class AppConfig:
    """Application-level configuration."""
    name: str = field(default_factory=lambda: os.getenv('APP_NAME', 'AppReviewsAnalysis'))
    version: str = field(default_factory=lambda: os.getenv('APP_VERSION', '2.0.0'))
    timezone: str = field(default_factory=lambda: os.getenv('TIMEZONE', 'Asia/Seoul'))


@dataclass
class AgentConfidenceThresholds:
    """Agent별 신뢰도 임계값"""
    sentiment: float = field(default_factory=lambda: float(os.getenv('AGENT_SENTIMENT_THRESHOLD', '0.7')))
    category: float = field(default_factory=lambda: float(os.getenv('AGENT_CATEGORY_THRESHOLD', '0.65')))
    complaint: float = field(default_factory=lambda: float(os.getenv('AGENT_COMPLAINT_THRESHOLD', '0.75')))
    insight: float = field(default_factory=lambda: float(os.getenv('AGENT_INSIGHT_THRESHOLD', '0.6')))
    unified: float = field(default_factory=lambda: float(os.getenv('AGENT_UNIFIED_THRESHOLD', '0.7')))
    base: float = field(default_factory=lambda: float(os.getenv('AGENT_BASE_THRESHOLD', '0.7')))


@dataclass
class OllamaAdvancedConfig:
    """Ollama 고급 파라미터"""
    top_k: int = field(default_factory=lambda: int(os.getenv('OLLAMA_TOP_K', '20')))
    repeat_penalty: float = field(default_factory=lambda: float(os.getenv('OLLAMA_REPEAT_PENALTY', '1.1')))
    num_ctx: int = field(default_factory=lambda: int(os.getenv('OLLAMA_NUM_CTX', '8192')))
    top_p: float = field(default_factory=lambda: float(os.getenv('OLLAMA_TOP_P', '0.95')))


@dataclass
class BGETimeoutConfig:
    """BGE API 타임아웃 설정"""
    embedding: int = field(default_factory=lambda: int(os.getenv('BGE_EMBEDDING_TIMEOUT', '30')))
    batch: int = field(default_factory=lambda: int(os.getenv('BGE_BATCH_TIMEOUT', '60')))
    rerank: int = field(default_factory=lambda: int(os.getenv('BGE_RERANK_TIMEOUT', '60')))


@dataclass
class FallbackDepartmentConfig:
    """Ultimate Fallback 부서 정보"""
    code: str = field(default_factory=lambda: os.getenv('FALLBACK_DEPT_CODE', 'CUSTOMER_SERVICE.CALL_CENTER'))
    name: str = field(default_factory=lambda: os.getenv('FALLBACK_DEPT_NAME', '콜센터운영부'))
    division_code: str = field(default_factory=lambda: os.getenv('FALLBACK_DIV_CODE', 'CUSTOMER_SERVICE'))
    division_name: str = field(default_factory=lambda: os.getenv('FALLBACK_DIV_NAME', '고객서비스본부'))
    description: str = field(default_factory=lambda: os.getenv('FALLBACK_DEPT_DESC', '기본 고객 응대 (Ultimate Fallback)'))


@dataclass
class Settings:
    """Main settings container that aggregates all configurations."""
    flask: FlaskConfig = field(default_factory=FlaskConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    opensearch: OpenSearchConfig = field(default_factory=OpenSearchConfig)
    redis: RedisSentinelConfig = field(default_factory=RedisSentinelConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    groq: GroqConfig = field(default_factory=GroqConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    azure_openai: AzureOpenAIConfig = field(default_factory=AzureOpenAIConfig)
    bge: BGEConfig = field(default_factory=BGEConfig)
    local_embedding: LocalEmbeddingConfig = field(default_factory=LocalEmbeddingConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    app: AppConfig = field(default_factory=AppConfig)

    # Agent configuration
    agent_thresholds: AgentConfidenceThresholds = field(default_factory=AgentConfidenceThresholds)
    ollama_advanced: OllamaAdvancedConfig = field(default_factory=OllamaAdvancedConfig)
    bge_timeouts: BGETimeoutConfig = field(default_factory=BGETimeoutConfig)
    fallback_department: FallbackDepartmentConfig = field(default_factory=FallbackDepartmentConfig)

    # LLM Fallback Order
    llm_fallback_order: List[str] = field(default_factory=lambda: _parse_list(os.getenv('LLM_FALLBACK_ORDER', 'gemini,ollama,groq,openai')))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Use this function to access settings throughout the application.
    """
    return Settings()
