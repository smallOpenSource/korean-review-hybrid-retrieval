# -*- coding: utf-8 -*-
"""
Pytest Configuration and Fixtures
"""
import pytest
from unittest.mock import Mock, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The app refuses to start without SECRET_KEY. For tests, use the value from
# the environment if present, otherwise a random per-run value.
import secrets
os.environ.setdefault('SECRET_KEY', secrets.token_hex(32))


@pytest.fixture
def app():
    """Create Flask application for testing."""
    from app import create_app

    app = create_app()
    app.config.update({
        'TESTING': True,
    })
    yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini LLM client."""
    mock = MagicMock()
    mock.generate.return_value = {
        'text': '{"sentiment": "positive", "confidence": 0.95}',
        'model': 'gemini-2.0-flash',
        'tokens_used': 100
    }
    return mock


@pytest.fixture
def mock_opensearch_client():
    """Mock OpenSearch client."""
    mock = MagicMock()
    mock.search.return_value = {
        'hits': {
            'total': {'value': 10},
            'hits': []
        }
    }
    mock.index.return_value = {'result': 'created'}
    return mock


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    mock = MagicMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = True
    return mock


@pytest.fixture
def sample_review():
    """Sample review data for testing."""
    return {
        'review_id': 'test_review_001',
        'app_id': 'com.example.app',
        'content': '앱이 정말 좋아요! 사용하기 편리하고 디자인도 예뻐요.',
        'rating': 5,
        'author': 'test_user',
        'timestamp': '2024-01-15T10:30:00Z',
        'version': '1.2.3'
    }


@pytest.fixture
def sample_negative_review():
    """Sample negative review for complaint testing."""
    return {
        'review_id': 'test_review_002',
        'app_id': 'com.example.app',
        'content': '로그인이 안 돼요. 앱이 자꾸 튕겨서 사용할 수가 없네요. 빨리 수정해주세요!',
        'rating': 1,
        'author': 'angry_user',
        'timestamp': '2024-01-16T14:20:00Z',
        'version': '1.2.3'
    }


@pytest.fixture
def sample_sentiment_result():
    """Sample sentiment analysis result."""
    return {
        'sentiment': 'positive',
        'sentiment_score': 0.92,
        'emotions': ['satisfaction', 'joy'],
        'confidence': 0.95,
        'reasoning': {
            'summary': '긍정적인 사용 경험을 표현',
            'key_factors': ['편리함', '디자인 만족']
        }
    }


@pytest.fixture
def sample_category_result():
    """Sample category classification result."""
    return {
        'primary_category': 'UX_DESIGN',
        'secondary_categories': ['USABILITY'],
        'confidence': 0.88,
        'related_features': ['UI', 'navigation'],
        'reasoning': {
            'summary': '사용자 경험 관련 피드백'
        }
    }


@pytest.fixture
def sample_complaint_result():
    """Sample complaint classification result."""
    return {
        'complaint_type': 'APP_CRASH',
        'department': 'IT_APP',
        'urgency': 'high',
        'severity': 'critical',
        'requires_escalation': True,
        'sla_hours': 4,
        'confidence': 0.91,
        'reasoning': {
            'summary': '앱 충돌 및 로그인 실패 문제'
        }
    }
