#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BGE Model Download Script

Downloads bge-m3-ko embedding model and bge-reranker-v2-m3 rerank model
for local CPU inference.

Usage:
    python scripts/download_models.py [--cache-dir ./models] [--embedding-only] [--rerank-only]

Models:
    - upskyy/bge-m3-ko: Korean-optimized embedding model (1024 dimensions)
    - BAAI/bge-reranker-v2-m3: Cross-encoder reranker model
"""

import argparse
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default models
DEFAULT_EMBEDDING_MODEL = "upskyy/bge-m3-ko"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_CACHE_DIR = "./models"


def check_dependencies():
    """Check if required packages are installed."""
    missing = []

    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")
    except ImportError:
        missing.append("torch")

    try:
        import sentence_transformers
        logger.info(f"sentence-transformers version: {sentence_transformers.__version__}")
    except ImportError:
        missing.append("sentence-transformers")

    try:
        import FlagEmbedding
        logger.info("FlagEmbedding installed")
    except ImportError:
        missing.append("FlagEmbedding")

    if missing:
        logger.error(f"Missing packages: {', '.join(missing)}")
        logger.error("Install with: pip install " + " ".join(missing))
        return False

    return True


def download_embedding_model(model_name: str, cache_dir: str) -> bool:
    """Download embedding model using sentence-transformers."""
    logger.info(f"Downloading embedding model: {model_name}")
    logger.info(f"Cache directory: {cache_dir}")

    try:
        from sentence_transformers import SentenceTransformer

        # Create cache directory
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # Download model
        logger.info("Downloading... This may take several minutes.")
        model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            device="cpu"
        )

        # Test embedding
        test_text = "테스트 문장입니다."
        embedding = model.encode(test_text, normalize_embeddings=True)

        logger.info(f"Model downloaded successfully!")
        logger.info(f"Embedding dimensions: {len(embedding)}")
        logger.info(f"Model location: {cache_dir}")

        return True

    except Exception as e:
        logger.error(f"Failed to download embedding model: {e}")
        return False


def download_rerank_model(model_name: str, cache_dir: str) -> bool:
    """Download rerank model using FlagEmbedding."""
    logger.info(f"Downloading rerank model: {model_name}")
    logger.info(f"Cache directory: {cache_dir}")

    try:
        from FlagEmbedding import FlagReranker

        # Create cache directory
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # Set HuggingFace cache
        os.environ["HF_HOME"] = cache_dir
        os.environ["TRANSFORMERS_CACHE"] = cache_dir

        # Download model
        logger.info("Downloading... This may take several minutes.")
        model = FlagReranker(
            model_name,
            use_fp16=False,  # CPU doesn't support fp16
            device="cpu"
        )

        # Test reranking
        test_query = "한국어 테스트 쿼리"
        test_docs = ["관련 문서입니다.", "관련 없는 문서입니다."]
        pairs = [[test_query, doc] for doc in test_docs]
        scores = model.compute_score(pairs, normalize=True)

        logger.info(f"Model downloaded successfully!")
        logger.info(f"Test scores: {scores}")
        logger.info(f"Model location: {cache_dir}")

        return True

    except Exception as e:
        logger.error(f"Failed to download rerank model: {e}")
        return False


def get_model_size(cache_dir: str) -> str:
    """Calculate total size of downloaded models."""
    total_size = 0
    cache_path = Path(cache_dir)

    if cache_path.exists():
        for file in cache_path.rglob("*"):
            if file.is_file():
                total_size += file.stat().st_size

    # Convert to human readable
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total_size < 1024:
            return f"{total_size:.2f} {unit}"
        total_size /= 1024

    return f"{total_size:.2f} TB"


def main():
    parser = argparse.ArgumentParser(
        description="Download BGE models for local inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Download all models
    python scripts/download_models.py

    # Download to custom directory
    python scripts/download_models.py --cache-dir /path/to/models

    # Download only embedding model
    python scripts/download_models.py --embedding-only

    # Download only rerank model
    python scripts/download_models.py --rerank-only
        """
    )

    parser.add_argument(
        "--cache-dir",
        default=DEFAULT_CACHE_DIR,
        help=f"Directory to cache models (default: {DEFAULT_CACHE_DIR})"
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Embedding model name (default: {DEFAULT_EMBEDDING_MODEL})"
    )
    parser.add_argument(
        "--rerank-model",
        default=DEFAULT_RERANK_MODEL,
        help=f"Rerank model name (default: {DEFAULT_RERANK_MODEL})"
    )
    parser.add_argument(
        "--embedding-only",
        action="store_true",
        help="Download only embedding model"
    )
    parser.add_argument(
        "--rerank-only",
        action="store_true",
        help="Download only rerank model"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("BGE Model Download Script")
    print("=" * 60)
    print()

    # Check dependencies
    if not check_dependencies():
        print()
        print("Please install missing dependencies first.")
        sys.exit(1)

    print()
    success = True
    download_embedding = not args.rerank_only
    download_rerank = not args.embedding_only

    # Download embedding model
    if download_embedding:
        print("-" * 60)
        if not download_embedding_model(args.embedding_model, args.cache_dir):
            success = False
        print()

    # Download rerank model
    if download_rerank:
        print("-" * 60)
        if not download_rerank_model(args.rerank_model, args.cache_dir):
            success = False
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Cache directory: {args.cache_dir}")
    print(f"Total size: {get_model_size(args.cache_dir)}")
    print()

    if success:
        print("All models downloaded successfully!")
        print()
        print("To use these models, set in .env:")
        print(f"  BGE_LOCAL_MODEL_CACHE_DIR={args.cache_dir}")
        print(f"  BGE_LOCAL_EMBEDDING_MODEL={args.embedding_model}")
        print(f"  BGE_LOCAL_RERANK_MODEL={args.rerank_model}")
        print("  BGE_LOCAL_DEVICE=cpu")
    else:
        print("Some models failed to download. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
