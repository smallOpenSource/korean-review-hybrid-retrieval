"""
Services module for business logic.
"""

from .review_service import ReviewService, get_review_service
from .dedup_service import DedupService, get_dedup_service
from .word_analysis_service import WordAnalysisService, get_word_analysis_service
from .similar_review_service import SimilarReviewService, get_similar_review_service

__all__ = [
    'ReviewService',
    'get_review_service',
    'DedupService',
    'get_dedup_service',
    'WordAnalysisService',
    'get_word_analysis_service',
    'SimilarReviewService',
    'get_similar_review_service',
]
