#!/usr/bin/env python3
"""
Index the fictional sample reviews (samples/reviews_sample.jsonl) into OpenSearch.

Pipeline exercised:
  1. ReviewService.ensure_index()  -> creates `app_reviews` with the Nori analyzer
     and a 1024-dim knn_vector (HNSW, cosinesimil)
  2. EmbeddingService.embed_sync() -> BGE-M3 dense vectors
     (BGE API if BGE_EMBEDDING_API_URL is set, otherwise a local sentence-transformers model)
  3. Bulk indexing of ReviewDocument objects

Usage:
    python scripts/demo_index_samples.py [--recreate] [--file samples/reviews_sample.jsonl]

No MySQL, Redis or LLM API is needed for this demo. OpenSearch must be reachable
with the settings in .env (see docker-compose.yml).
"""
import argparse
import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.services.review_service import (  # noqa: E402
    REVIEW_INDEX,
    ReviewDocument,
    get_review_service,
)


def load_samples(path: str):
    reviews = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            doc = ReviewDocument(
                review_id=row["review_id"],
                app_id=row["app_id"],
                app_name=row["app_name"],
                company_code=row["company_code"],
                platform=row.get("platform", "android"),
                original_content=row["content"],
                cleansed_content=row["content"],
                rating=int(row["rating"]),
                review_date=datetime.fromisoformat(row["review_date"]),
            )
            if row.get("sentiment_label"):
                doc.sentiment = {"label": row["sentiment_label"]}
            if row.get("complaint_type"):
                doc.complaint = {"is_complaint": True, "type": row["complaint_type"]}
            reviews.append(doc)
    return reviews


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "samples", "reviews_sample.jsonl"))
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the index first")
    args = parser.parse_args()

    service = get_review_service()
    client = service._os.sync_client

    if args.recreate and client.indices.exists(index=REVIEW_INDEX):
        client.indices.delete(index=REVIEW_INDEX)
        print(f"Deleted index: {REVIEW_INDEX}")

    created = service.ensure_index()
    print(f"Index '{REVIEW_INDEX}': {'created' if created else 'already exists'}")

    reviews = load_samples(args.file)
    print(f"Loaded {len(reviews)} sample reviews from {os.path.relpath(args.file, PROJECT_ROOT)}")
    print("Embedding with BGE-M3 (first run downloads the model) ...")

    success, failure = service.index_reviews_bulk(reviews, generate_embeddings=True)
    missing_vectors = sum(1 for r in reviews if not r.content_embedding)
    print(f"Indexed: success={success}, failure={failure}, without_embedding={missing_vectors}")
    return 0 if failure == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
