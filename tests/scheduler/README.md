# Scheduler Test Suite

This directory contains test files for the scheduler module.

## Test Structure

```
test/scheduler/
├── test_collector.py          # Play Store collector tests (TODO)
├── test_jobs.py                # Job execution tests (TODO)
├── test_database.py            # Database operations tests (TODO)
└── test_integration.py         # Integration tests (TODO)
```

## Running Tests

```bash
# From project root
pytest test/scheduler/

# With coverage
pytest test/scheduler/ --cov=scheduler --cov-report=html

# Specific test file
pytest test/scheduler/test_collector.py -v
```

## Test Requirements

Tests require the following:
- Python 3.10+
- pytest
- pytest-asyncio
- pytest-cov

Install test dependencies:
```bash
pip install pytest pytest-asyncio pytest-cov
```

## Writing Tests

### Example Test Structure

```python
import pytest
from scheduler.collectors.play_store_collector import PlayStoreCollector

@pytest.mark.asyncio
async def test_collector_initialization():
    collector = PlayStoreCollector()
    assert collector is not None

@pytest.mark.asyncio
async def test_get_reviews():
    collector = PlayStoreCollector()
    reviews, token = await collector.get_reviews(
        package_id='com.example.app',
        count=10
    )
    assert len(reviews) > 0
```

## Future Plans

- [ ] Unit tests for Play Store collector
- [ ] Unit tests for database operations
- [ ] Unit tests for job tracking
- [ ] Integration tests for end-to-end workflows
- [ ] Mock tests for external API calls
- [ ] Performance benchmarks
