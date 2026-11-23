"""
Word Cloud Generation Job.
Generates word clouds from collected reviews.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from scheduler.utils import get_scheduler_config, get_app_config_loader

from app.core.mysql_client import get_mysql_client

logger = logging.getLogger(__name__)


class GenerateWordCloudJob:
    """
    Job for generating word clouds from review data.

    Generates daily, weekly, and monthly word clouds for:
    - All apps combined
    - Each category
    - Individual apps (high priority only)
    """

    def __init__(
        self,
        output_dir: Optional[str] = None
    ):
        """
        Initialize the job.

        Args:
            output_dir: Directory to save word cloud images
        """
        self._mysql_client = get_mysql_client()
        self._scheduler_config = get_scheduler_config()
        self._app_config = get_app_config_loader()

        job_config = self._scheduler_config.get_job_config('generate_wordcloud') or {}
        settings = job_config.get('settings', {})

        self._output_dir = Path(output_dir or settings.get('output_dir', '/var/data/wordclouds'))
        self._periods = settings.get('periods', ['daily', 'weekly', 'monthly'])
        self._min_word_freq = settings.get('min_word_freq', 5)
        self._max_words = settings.get('max_words', 200)

        # Lazy import for optional dependencies
        self._wordcloud = None
        self._mecab = None
        self._plt = None

    def _lazy_import(self):
        """Lazy import optional dependencies."""
        if self._wordcloud is None:
            try:
                from wordcloud import WordCloud
                import MeCab
                import matplotlib.pyplot as plt
                import matplotlib.font_manager as fm

                self._wordcloud = WordCloud
                mecab_dic = os.getenv('MECAB_KO_DIC_PATH', '')
                self._mecab = MeCab.Tagger(f'-d {mecab_dic}' if mecab_dic else '')
                self._plt = plt
                self._fm = fm
            except ImportError as e:
                logger.error(f"Failed to import word cloud dependencies: {e}")
                raise

    def _ensure_output_dir(self):
        """Ensure output directory exists."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> Dict[str, Any]:
        """
        Run the word cloud generation job.

        Returns:
            Job result summary
        """
        start_time = datetime.now()
        logger.info("Starting word cloud generation job")

        results = {
            'status': 'completed',
            'wordclouds_generated': 0,
            'errors': [],
            'files': [],
            'duration_seconds': 0
        }

        try:
            self._lazy_import()
            self._ensure_output_dir()
        except Exception as e:
            results['status'] = 'failed'
            results['errors'].append(str(e))
            return results

        # Generate for each period
        for period in self._periods:
            try:
                period_results = await self._generate_for_period(period)
                results['wordclouds_generated'] += period_results['count']
                results['files'].extend(period_results['files'])

                if period_results['errors']:
                    results['errors'].extend(period_results['errors'])

            except Exception as e:
                error_msg = f"Failed to generate {period} word clouds: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        end_time = datetime.now()
        results['duration_seconds'] = (end_time - start_time).total_seconds()

        logger.info(
            f"Word cloud generation completed: "
            f"{results['wordclouds_generated']} generated"
        )

        return results

    async def _generate_for_period(self, period: str) -> Dict[str, Any]:
        """
        Generate word clouds for a specific time period.

        Args:
            period: 'daily', 'weekly', or 'monthly'

        Returns:
            Generation results
        """
        results = {
            'count': 0,
            'files': [],
            'errors': []
        }

        # Calculate date range
        end_date = datetime.now()
        if period == 'daily':
            start_date = end_date - timedelta(days=1)
        elif period == 'weekly':
            start_date = end_date - timedelta(weeks=1)
        elif period == 'monthly':
            start_date = end_date - timedelta(days=30)
        else:
            logger.warning(f"Unknown period: {period}")
            return results

        # 1. Generate overall word cloud
        try:
            overall_file = await self._generate_overall(period, start_date, end_date)
            if overall_file:
                results['files'].append(overall_file)
                results['count'] += 1
        except Exception as e:
            results['errors'].append(f"Failed overall {period}: {e}")

        # 2. Generate per-category word clouds
        for category in self._app_config.get_categories():
            try:
                cat_file = await self._generate_for_category(
                    category.name, period, start_date, end_date
                )
                if cat_file:
                    results['files'].append(cat_file)
                    results['count'] += 1
            except Exception as e:
                results['errors'].append(f"Failed category {category.name} {period}: {e}")

        return results

    async def _generate_overall(
        self,
        period: str,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[str]:
        """
        Generate overall word cloud for all apps.

        Args:
            period: Time period name
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Path to generated file or None
        """
        # Fetch reviews from database
        reviews = await self._fetch_reviews(None, start_date, end_date)

        if not reviews:
            logger.info(f"No reviews found for overall {period} word cloud")
            return None

        # Extract text
        text = ' '.join([r.get('content', '') for r in reviews])

        # Generate word cloud
        filename = f"overall_{period}_{end_date.strftime('%Y%m%d')}.png"
        filepath = self._output_dir / filename

        await self._generate_wordcloud_image(text, filepath, f"전체 {period}")

        logger.info(f"Generated overall {period} word cloud: {filepath}")
        return str(filepath)

    async def _generate_for_category(
        self,
        category: str,
        period: str,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[str]:
        """
        Generate word cloud for a specific category.

        Args:
            category: Category name
            period: Time period name
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Path to generated file or None
        """
        # Get package IDs for this category
        apps = self._app_config.get_apps_by_category(category)
        package_ids = [app.package_id for app in apps]

        if not package_ids:
            return None

        # Fetch reviews
        reviews = await self._fetch_reviews(package_ids, start_date, end_date)

        if not reviews:
            logger.debug(f"No reviews found for category {category} {period}")
            return None

        # Extract text
        text = ' '.join([r.get('content', '') for r in reviews])

        # Generate word cloud
        filename = f"{category}_{period}_{end_date.strftime('%Y%m%d')}.png"
        filepath = self._output_dir / filename

        category_info = self._app_config.get_category(category)
        title = f"{category_info.display_name if category_info else category} {period}"

        await self._generate_wordcloud_image(text, filepath, title)

        logger.info(f"Generated {category} {period} word cloud: {filepath}")
        return str(filepath)

    async def _fetch_reviews(
        self,
        package_ids: Optional[List[str]],
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch reviews from database.

        Args:
            package_ids: List of package IDs to filter, or None for all
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of review dictionaries
        """
        try:
            with self._mysql_client.get_cursor() as cursor:
                query = """
                    SELECT content 
                    FROM reviews 
                    WHERE at >= %s AND at <= %s
                """
                params = [start_date, end_date]

                if package_ids:
                    placeholders = ', '.join(['%s'] * len(package_ids))
                    query += f" AND package_id IN ({placeholders})"
                    params.extend(package_ids)

                cursor.execute(query, tuple(params))
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Failed to fetch reviews: {e}")
            return []

    async def _generate_wordcloud_image(
        self,
        text: str,
        filepath: Path,
        title: str
    ) -> None:
        """
        Generate and save a word cloud image.

        Args:
            text: Text to generate word cloud from
            filepath: Path to save the image
            title: Title for the image
        """
        # Extract nouns using MeCab
        parsed = self._mecab.parse(text)
        nouns = []
        for line in parsed.split('\n'):
            if '\t' in line:
                word, features = line.split('\t')
                # NNG(일반명사), NNP(고유명사) 추출
                if features.startswith('NNG') or features.startswith('NNP'):
                    nouns.append(word)

        # Filter short words and count frequencies
        word_freq = {}
        for noun in nouns:
            if len(noun) >= 2:  # Skip single character words
                word_freq[noun] = word_freq.get(noun, 0) + 1

        # Filter by minimum frequency
        word_freq = {
            k: v for k, v in word_freq.items()
            if v >= self._min_word_freq
        }

        if not word_freq:
            logger.warning(f"No words found for word cloud: {title}")
            return

        # Generate word cloud
        # Use a font that supports Korean
        font_path = self._find_korean_font()
        
        # Create FontProperties for title
        font_prop = self._fm.FontProperties(fname=font_path) if font_path else None

        wc = self._wordcloud(
            font_path=font_path,
            width=800,
            height=600,
            max_words=self._max_words,
            background_color='white',
            colormap='viridis'
        )

        wc.generate_from_frequencies(word_freq)

        # Save image
        self._plt.figure(figsize=(10, 8))
        self._plt.imshow(wc, interpolation='bilinear')
        self._plt.axis('off')
        if font_prop:
            self._plt.title(title, fontsize=16, fontproperties=font_prop)
        else:
            self._plt.title(title, fontsize=16)
        self._plt.tight_layout()
        self._plt.savefig(filepath, dpi=150)
        self._plt.close()

    def _find_korean_font(self) -> str:
        """
        Find a Korean font on the system.

        Returns:
            Path to Korean font file
        """
        # Common Korean font paths
        font_paths = [
            # Explicit font path from environment (no font is bundled with this repo)
            os.getenv('KOREAN_FONT_PATH', ''),
            '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
            '/usr/share/fonts/nanum/NanumGothic.ttf',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/System/Library/Fonts/AppleGothic.ttf',
            'C:\\Windows\\Fonts\\malgun.ttf',
        ]

        for path in font_paths:
            if path and os.path.exists(path):
                return path

        # Return a default (may not support Korean)
        logger.warning("Korean font not found, word cloud may not display Korean correctly")
        return None


def run_generate_wordcloud_job(output_dir: str = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for running the word cloud generation job.

    Args:
        output_dir: Output directory for word cloud images

    Returns:
        Job result summary
    """
    job = GenerateWordCloudJob(
        output_dir=output_dir
    )
    return asyncio.run(job.run())
