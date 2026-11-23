# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

App Reviews Analysis System - A multi-agent LLM platform for analyzing Google Play Store reviews of Korean financial apps. Combines automated review collection, sentiment/category/complaint classification, vector search with OpenSearch KNN, and intelligent department routing.

## Development Commands

### Setup
```bash
# Copy environment template and configure
cp .env.example .env
# Edit .env with actual credentials

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

**Flask Application (Development):**
```bash
./run.sh
# Or explicitly:
FLASK_ENV=development ./run.sh
```

**Flask Application (Production):**
```bash
FLASK_ENV=production ./run.sh
# Uses Gunicorn with 4 workers (configurable via GUNICORN_WORKERS)
```

**Scheduler (Separate Process):**
```bash
python -m scheduler.main
# Must run separately from Flask app for review collection/analysis/sync
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_specific.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run only unit tests (skip slow/integration)
pytest -m "not slow and not integration"
```

### Database Operations
```bash
# Apply migrations (if using Alembic)
flask db upgrade

# Check MySQL connection
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE
```

## Architecture Overview

### Three-Stage Data Pipeline

This system follows a strict sequential pipeline that MUST be understood:

1. **COLLECT** (`scheduler/jobs/collect_reviews.py`)
   - Fetches reviews from Google Play Store
   - Stores in MySQL with `analyzed=0, synced_to_opensearch=0`
   - NO embeddings generated at this stage

2. **ANALYZE** (`scheduler/jobs/analyze_reviews.py`)
   - Queries MySQL for `WHERE analyzed=0`
   - Calls LLM agents (Sentiment/Category/Complaint)
   - Updates MySQL with results: `analyzed=1`
   - Does NOT update OpenSearch (that's Sync job's responsibility)

3. **SYNC** (`scheduler/jobs/sync_to_opensearch.py`)
   - Queries MySQL for `WHERE analyzed=1 AND synced_to_opensearch=0`
   - **Generates embeddings** using BGE-M3-KO (1024 dimensions)
   - Indexes to OpenSearch with vectors
   - Updates MySQL: `synced_to_opensearch=1`

4. **APPLICATION** (Flask)
   - All queries run against OpenSearch (NOT MySQL)
   - Supports semantic search (KNN), BM25 full-text, aggregations

**CRITICAL:** MySQL is the source of truth. OpenSearch is the search index. The scheduler sync job is the ONLY component that writes to OpenSearch.

### Multi-Agent System

All agents inherit from `BaseAgent` (`app/agents/base_agent.py`) which provides:
- LLM prompt template management with versioning
- JSON response parsing and validation
- Confidence scoring and quality flagging
- Reasoning extraction (steps, evidence, alternatives)
- Batch processing with asyncio

**Agent Types:**
- `SentimentAgent`: 5-level sentiment (very_negative → very_positive)
- `CategoryAgent`: Product category classification
- `ComplaintAgent`: Complaint detection + department routing
- `InsightAgent`: Strategic insights from review patterns
- `UnifiedAnalysisAgent`: Combined 3-in-1 analysis (optimization)

### LLM Provider Fallback Chain

LLMClient (`app/agents/llm_client.py`) implements automatic fallback:

1. **Primary:** Google Gemini (2.0 Flash, 2.5 Flash, 1.5 Pro)
   - Rate limit: 15 RPM (free tier)
   - Multi-key rotation support
2. **Fallback 1:** Ollama (local - Qwen/Llama models)
3. **Fallback 2:** Groq (Llama-3.3-70B)
4. **Fallback 3:** OpenAI (GPT-4o-mini)

Each provider has token counting, rate limiting, retry logic with exponential backoff.

### Search Architecture

**OpenSearch Index (`app_reviews`):**
- Nori analyzer for Korean morphological analysis
- KNN vector search with 1024-dim embeddings (BGE-M3-KO)
- BM25 full-text search
- Reranking with BGE-Reranker-v2-M3

**Search Flow:**
1. Initial search (BM25 or KNN)
2. Rerank results with BGE reranker
3. Return top-K results

## Key Files Reference

### Critical Entry Points
- `app/__init__.py` - Flask factory, blueprint registration
- `scheduler/main.py` - APScheduler setup and job registration
- `app/agents/base_agent.py` - Multi-agent framework foundation
- `app/agents/llm_client.py` - Unified LLM interface with fallback

### Configuration
- `.env` - All runtime configuration (copy from `.env.example`)
- `app/config/settings.py` - Dataclass-based config loader
- `app/config/prompts.yaml` - Agent prompt templates (versioned)
- `app/config/llm_models.yaml` - LLM provider specifications
- `scheduler/config/scheduler_config.yaml` - Job schedules (high/medium/low priority)

### Core Infrastructure
- `app/core/opensearch_client.py` - KNN + BM25 search wrapper
- `app/core/mysql_client.py` - Connection pooling (DBUtils)
- `app/core/redis_client.py` - Sentinel-aware caching
- `app/core/rate_limiter.py` - Token bucket algorithm

### Services
- `app/services/review_service.py` - Core search/aggregation operations
- `app/services/similar_review_service.py` - KNN semantic search
- `app/services/department_routing_service.py` - Complaint-to-department logic

### API Endpoints
- `app/api/v1/reviews.py` - Review CRUD
- `app/api/v1/analysis.py` - LLM analysis endpoints
- `app/api/v1/search.py` - Search endpoints
- `app/api/v1/complaints.py` - Complaint management

## Important Patterns

### Adding a New Agent

1. Create `app/agents/your_agent.py` inheriting from `BaseAgent`
2. Define prompt template in `app/config/prompts.yaml`
3. Implement `analyze()` method with JSON schema validation
4. Add to unified orchestration if needed

Example:
```python
from app.agents.base_agent import BaseAgent

class YourAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_type="your_agent", version="1.0.0")

    async def analyze(self, content: str) -> dict:
        # Use self.llm_client.generate_content()
        # Parse and validate JSON response
        return result
```

### Database Schema Updates

MySQL uses year-based partitioning on `reviews` table. When adding columns:
1. Update schema in `migrations/` or DDL files
2. Ensure backward compatibility for existing reviews
3. Update `analyze_reviews.py` if analysis fields change
4. Update `sync_to_opensearch.py` to sync new fields to OpenSearch
5. Update OpenSearch mapping in `app/core/opensearch_client.py`

### Working with OpenSearch

**Creating/updating index:**
```python
from app.core.opensearch_client import OpenSearchClient

client = OpenSearchClient()
# Index uses Nori analyzer for Korean + KNN vectors
# Mapping defined in opensearch_client.py
```

**Important:** Never write to OpenSearch directly from Flask routes. Always update MySQL and let the sync job handle OpenSearch.

### Rate Limiting

Gemini free tier: 15 RPM. LLMClient handles this automatically:
- Token bucket algorithm per model
- Automatic fallback on rate limit
- API key rotation if multiple keys configured

To test fallback: Set `GEMINI_API_KEY` to invalid value and verify Ollama is called.

## Common Workflows

### Adding Analysis to Reviews

1. Create/update agent in `app/agents/`
2. Update prompt in `app/config/prompts.yaml`
3. Modify `scheduler/jobs/analyze_reviews.py` to call new agent
4. Update MySQL schema to store results
5. Update `sync_to_opensearch.py` to index new fields
6. Update OpenSearch mapping if needed

### Debugging Pipeline Issues

**Review not appearing in search:**
```bash
# Check if collected
mysql> SELECT analyzed, synced_to_opensearch FROM reviews WHERE review_id = 'xxx';

# Check scheduler logs
tail -f logs/scheduler.log

# Verify OpenSearch index
curl -u "$OPENSEARCH_USER:$OPENSEARCH_PASSWORD" https://localhost:9200/app_reviews/_search?q=review_id:xxx
```

**LLM analysis failing:**
- Check `logs/app.log` for rate limit errors
- Verify fallback chain is working (should see provider switches)
- Confirm prompt templates exist in `prompts.yaml`

### Performance Tuning

**Batch sizes:**
- Analysis job: 10-100 reviews per batch (configured in `analyze_reviews.py`)
- Sync job: Bulk index 1000 at a time (in `sync_to_opensearch.py`)

**Caching:**
- Redis Sentinel for high availability
- TTL configured per cache key type
- Embedding cache to avoid regenerating vectors

**Search optimization:**
- Use `size` parameter to limit results
- Use aggregations instead of fetching all docs
- Leverage reranking only when needed (top-100 → top-10)

## Environment Variables

Critical variables (see `.env.example` for complete list):

**LLM Configuration:**
- `GEMINI_API_KEY` - Primary LLM provider
- `GEMINI_MODEL_REALTIME` - Fast analysis model (gemini-2.0-flash)
- `OLLAMA_BASE_URL` - Fallback local LLM
- `LLM_FALLBACK_ORDER` - Provider fallback sequence

**Database:**
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD` - Source of truth
- `OPENSEARCH_HOSTS` - Search index
- `REDIS_SENTINEL_HOSTS` - High-availability cache

**Embeddings:**
- `BGE_EMBEDDING_API_URL` - Primary embedding service
- `BGE_LOCAL_EMBEDDING_MODEL` - Fallback to local model
- `BGE_EMBEDDING_DIMENSIONS` - 1024 for bge-m3-ko

## Documentation References

- `docs/data_pipeline.md` - Detailed pipeline architecture (updated 2025-12-21)
- `README.md` - Project overview and quick start
- `app/config/prompts.yaml` - All agent prompt templates
- `.env.example` - Complete configuration reference

## Tech Stack Summary

- **Backend:** Flask 2.x, Gunicorn, APScheduler
- **LLM:** Google Gemini (primary), Ollama/Groq/OpenAI (fallback)
- **Search:** OpenSearch 2.x with KNN + Nori analyzer
- **Embeddings:** BGE-M3-KO (1024-dim, Korean-optimized)
- **Database:** MySQL 8.x with year partitioning
- **Cache:** Redis Sentinel (6.x+)
- **Frontend:** Jinja2, Tailwind CSS, Alpine.js, ECharts
- **Validation:** Pydantic for API schemas
