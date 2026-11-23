"""
Wordcloud generation service for Korean text reviews.
"""

import os
import logging
from typing import Dict, List, Optional
from collections import Counter
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


class WordCloudService:
    """Service for generating wordclouds from review text."""
    
    def __init__(self, review_service=None, static_dir: str = None):
        """
        Initialize WordCloud service.
        
        Args:
            review_service: ReviewService instance for fetching reviews
            static_dir: Path to static directory for saving images
        """
        self.review_service = review_service
        self.static_dir = static_dir or os.path.join(
            os.path.dirname(__file__), '..', 'static', 'wc'
        )
        os.makedirs(self.static_dir, exist_ok=True)
        
    def _extract_keywords(self, text: str, min_length: int = 2) -> List[str]:
        """
        Extract keywords from text using simple tokenization.
        For Korean text, extracts words of minimum length.
        
        Args:
            text: Review text
            min_length: Minimum word length
            
        Returns:
            List of extracted keywords
        """
        if not text:
            return []
            
        # Remove special characters, keep Korean, numbers, spaces
        cleaned = re.sub(r'[^\w\s가-힣]', ' ', text)
        
        # Split by whitespace
        words = cleaned.split()
        
        # Filter by length and remove common stopwords
        stopwords = {
            '것', '수', '등', '및', '이', '그', '저', '때', '등등', '하다',
            '있다', '없다', '되다', '같다', '보다', '주다', '아니다', '이다',
            '하는', '있는', '없는', '되는', '같은', '보는', '주는'
        }
        
        keywords = [
            word for word in words 
            if len(word) >= min_length and word not in stopwords
        ]
        
        return keywords
        
    def generate_wordcloud_data(
        self, 
        app_id: str, 
        sentiment_type: str = 'POSITIVE',
        days: int = 90,
        max_words: int = 50
    ) -> Dict[str, int]:
        """
        Generate word frequency data for wordcloud.
        
        Args:
            app_id: Application ID
            sentiment_type: 'POSITIVE' or 'NEGATIVE'
            days: Number of days to look back
            max_words: Maximum number of words to include
            
        Returns:
            Dictionary of word: frequency
        """
        if not self.review_service:
            logger.error("ReviewService not initialized")
            return {}
            
        try:
            # Fetch reviews with specific sentiment
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Use OpenSearch to get reviews
            client = self.review_service._os.sync_client
            
            query = {
                "size": 500,  # Limit to recent reviews
                "_source": ["content"],
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"app_id": app_id}},
                            {"term": {"sentiment.label": sentiment_type}},
                            {"range": {"review_date": {
                                "gte": start_date.isoformat(),
                                "lte": end_date.isoformat()
                            }}}
                        ]
                    }
                },
                "sort": [{"review_date": {"order": "desc"}}]
            }
            
            result = client.search(
                index=self.review_service._index,
                body=query
            )
            
            # Extract text and generate keywords
            all_keywords = []
            for hit in result['hits']['hits']:
                content = hit['_source'].get('content', '')
                keywords = self._extract_keywords(content)
                all_keywords.extend(keywords)
            
            # Count frequency
            word_freq = Counter(all_keywords)
            
            # Return top N words
            top_words = dict(word_freq.most_common(max_words))
            
            logger.info(
                f"Generated {len(top_words)} words for {app_id} "
                f"({sentiment_type})"
            )
            
            return top_words
            
        except Exception as e:
            logger.error(f"Error generating wordcloud data: {e}")
            return {}
    
    def generate_simple_wordcloud_image(
        self,
        word_freq: Dict[str, int],
        output_path: str,
        sentiment_type: str = 'POSITIVE'
    ) -> bool:
        """
        Generate a simple text-based wordcloud image.
        This is a fallback implementation without external dependencies.
        
        Args:
            word_freq: Dictionary of word frequencies
            output_path: Path to save the image
            sentiment_type: 'POSITIVE' or 'NEGATIVE' for color selection
            
        Returns:
            True if successful, False otherwise
        """
        # For now, save as JSON for debugging
        # In production, this would use matplotlib or wordcloud library
        import json
        
        try:
            json_path = output_path.replace('.png', '.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'words': word_freq,
                    'sentiment': sentiment_type,
                    'generated_at': datetime.utcnow().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved wordcloud data to {json_path}")
            
            # Create placeholder image using PIL if available
            try:
                from PIL import Image, ImageDraw, ImageFont
                
                # Create image
                img = Image.new('RGB', (600, 400), color='white')
                draw = ImageDraw.Draw(img)
                
                # Add top words as text
                y_pos = 20
                color = (16, 185, 129) if sentiment_type == 'POSITIVE' else (239, 68, 68)
                
                for word, freq in list(word_freq.items())[:10]:
                    text = f"{word}: {freq}"
                    draw.text((20, y_pos), text, fill=color)
                    y_pos += 30
                
                img.save(output_path)
                logger.info(f"Generated simple wordcloud image at {output_path}")
                return True
                
            except ImportError:
                logger.warning("PIL not available, skipping image generation")
                return False
                
        except Exception as e:
            logger.error(f"Error generating wordcloud image: {e}")
            return False
    
    def generate_for_company(
        self,
        app_id: str,
        company_code: str,
        days: int = 90
    ) -> Dict[str, bool]:
        """
        Generate both positive and negative wordclouds for a company.
        
        Args:
            app_id: Application ID
            company_code: Company code for filename
            days: Number of days of data
            
        Returns:
            Dictionary with success status for pos and neg
        """
        results = {}
        
        for sentiment_type in ['POSITIVE', 'NEGATIVE']:
            suffix = 'pos' if sentiment_type == 'POSITIVE' else 'neg'
            filename = f"wc_{company_code}_{suffix}.png"
            output_path = os.path.join(self.static_dir, filename)
            
            # Generate word frequency data
            word_freq = self.generate_wordcloud_data(
                app_id=app_id,
                sentiment_type=sentiment_type,
                days=days
            )
            
            if word_freq:
                # Generate image
                success = self.generate_simple_wordcloud_image(
                    word_freq=word_freq,
                    output_path=output_path,
                    sentiment_type=sentiment_type
                )
                results[suffix] = success
            else:
                results[suffix] = False
                logger.warning(
                    f"No data for {company_code} {sentiment_type}"
                )
        
        return results


# Singleton instance
_wordcloud_service = None


def get_wordcloud_service():
    """Get or create WordCloudService instance."""
    global _wordcloud_service
    
    if _wordcloud_service is None:
        from app.services.review_service import get_review_service
        review_service = get_review_service()
        _wordcloud_service = WordCloudService(review_service=review_service)
    
    return _wordcloud_service
