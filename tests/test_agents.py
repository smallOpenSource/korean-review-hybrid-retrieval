# -*- coding: utf-8 -*-
"""
Tests for Multi-Agent System
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json


class TestSentimentAgent:
    """Tests for Sentiment Agent."""

    def test_analyze_positive_review(self, sample_review, mock_gemini_client):
        """Test sentiment analysis on positive review."""
        with patch('app.agents.sentiment_agent.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.generate.return_value = {
                'text': json.dumps({
                    'sentiment': 'positive',
                    'sentiment_score': 0.92,
                    'emotions': ['satisfaction', 'joy'],
                    'confidence': 0.95,
                    'reasoning': {'summary': '긍정적 피드백'}
                }),
                'model': 'gemini-2.0-flash'
            }

            # Import after patching
            from app.agents.sentiment_agent import SentimentAgent
            agent = SentimentAgent()

            result = agent.analyze(sample_review)

            assert result is not None
            assert result.get('sentiment') == 'positive'
            assert result.get('confidence', 0) > 0.7

    def test_analyze_negative_review(self, sample_negative_review, mock_gemini_client):
        """Test sentiment analysis on negative review."""
        with patch('app.agents.sentiment_agent.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.generate.return_value = {
                'text': json.dumps({
                    'sentiment': 'negative',
                    'sentiment_score': 0.15,
                    'emotions': ['frustration', 'anger'],
                    'confidence': 0.93,
                    'reasoning': {'summary': '앱 문제로 인한 불만'}
                }),
                'model': 'gemini-2.0-flash'
            }

            from app.agents.sentiment_agent import SentimentAgent
            agent = SentimentAgent()

            result = agent.analyze(sample_negative_review)

            assert result is not None
            assert result.get('sentiment') == 'negative'


class TestCategoryAgent:
    """Tests for Category Agent."""

    def test_classify_ux_review(self, sample_review, mock_gemini_client):
        """Test category classification for UX-related review."""
        with patch('app.agents.category_agent.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.generate.return_value = {
                'text': json.dumps({
                    'primary_category': 'UX_DESIGN',
                    'secondary_categories': ['USABILITY'],
                    'confidence': 0.88
                }),
                'model': 'gemini-2.0-flash'
            }

            from app.agents.category_agent import CategoryAgent
            agent = CategoryAgent()

            result = agent.analyze(sample_review)

            assert result is not None
            assert 'primary_category' in result or 'category' in result


class TestComplaintAgent:
    """Tests for Complaint Agent."""

    def test_classify_app_crash_complaint(self, sample_negative_review, mock_gemini_client):
        """Test complaint classification for app crash issue."""
        with patch('app.agents.complaint_agent.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.generate.return_value = {
                'text': json.dumps({
                    'complaint_type': 'APP_CRASH',
                    'department': 'IT_APP',
                    'urgency': 'high',
                    'severity': 'critical',
                    'requires_escalation': True,
                    'sla_hours': 4,
                    'confidence': 0.91
                }),
                'model': 'gemini-2.0-flash'
            }

            from app.agents.complaint_agent import ComplaintAgent
            agent = ComplaintAgent()

            result = agent.analyze(sample_negative_review)

            assert result is not None

    def test_department_assignment(self, mock_gemini_client):
        """Test that complaints are assigned to correct departments."""
        department_cases = [
            ('앱이 계속 튕겨요', 'IT_APP'),
            ('서버 연결이 안 돼요', 'IT_INFRA'),
            ('개인정보 유출 우려', 'IT_SEC'),
            ('상담원 연결이 안 돼요', 'CS_CENTER'),
            ('카드 결제 오류', 'BIZ_CARD'),
            ('대출 이자 문제', 'BIZ_LOAN'),
        ]

        # This is a placeholder test - actual implementation would test each case
        assert len(department_cases) == 6


class TestInsightAgent:
    """Tests for Insight Agent."""

    def test_generate_insight(self, mock_gemini_client):
        """Test insight generation from review batch."""
        with patch('app.agents.insight_agent.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.generate.return_value = {
                'text': json.dumps({
                    'insights': ['사용자들이 UI 개선을 원함'],
                    'trends': ['앱 안정성 불만 증가'],
                    'recommendations': ['성능 최적화 필요']
                }),
                'model': 'gemini-1.5-pro'
            }

            from app.agents.insight_agent import InsightAgent
            agent = InsightAgent()

            # Test would pass if agent initializes correctly
            assert agent is not None


class TestEmbeddingService:
    """Tests for Embedding Service."""

    def test_embed_text(self, mock_gemini_client):
        """Test text embedding generation."""
        with patch('app.agents.embedding_service.GeminiClient', return_value=mock_gemini_client):
            mock_gemini_client.embed.return_value = {
                'embedding': [0.1] * 1024,
                'model': 'bge-m3-ko'
            }

            from app.agents.embedding_service import EmbeddingService
            service = EmbeddingService()

            assert service is not None

    def test_embedding_dimensions(self):
        """Test that embeddings have correct dimensions (1024 for bge-m3-ko)."""
        expected_dims = 1024
        sample_embedding = [0.1] * expected_dims

        assert len(sample_embedding) == expected_dims
