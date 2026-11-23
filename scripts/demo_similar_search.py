#!/usr/bin/env python3
"""
Similar-review retrieval demo on the indexed sample data.

For each query it prints:
  - Nori BM25 keyword hits (match query on `cleansed_content`, korean analyzer)
  - SimilarReviewService result: KNN candidates (BGE-M3) re-ordered by bge-reranker-v2-m3

Usage:
    python scripts/demo_index_samples.py            # once
    python scripts/demo_similar_search.py "지문 로그인이 안 돼요"
    python scripts/demo_similar_search.py --file samples/queries_sample.txt
"""
import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.core.opensearch_client import get_opensearch_client  # noqa: E402
from app.services.review_service import REVIEW_INDEX  # noqa: E402
from app.services.similar_review_service import get_similar_review_service  # noqa: E402


def read_queries(args) -> list:
    queries = list(args.query)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append(line)
    return queries


def keyword_search(query: str, k: int):
    body = {
        "query": {"match": {"cleansed_content": {"query": query}}},
        "_source": ["review_id", "app_name", "cleansed_content"],
    }
    response = get_opensearch_client().search(index=REVIEW_INDEX, query=body, size=k)
    return response["hits"]["hits"]


async def run(queries, k: int, candidate_k: int, min_similarity: float):
    service = get_similar_review_service()
    for query in queries:
        print("=" * 80)
        print(f"Query: {query}")

        print("\n[1] Nori BM25 keyword search")
        for hit in keyword_search(query, k):
            src = hit["_source"]
            print(f"  bm25={hit['_score']:.3f}  {src['review_id']}  [{src['app_name']}] {src['cleansed_content']}")

        result = await service.find_similar(
            content=query,
            k=k,
            candidate_k=candidate_k,
            min_similarity=min_similarity,
            use_rerank=True,
            include_trend=False,
        )
        print(f"\n[2] Vector search + rerank (method={result.search_method}, reranked={result.reranked})")
        for review in result.similar_reviews:
            rerank = f"{review.rerank_score:.3f}" if review.rerank_score is not None else "-"
            print(
                f"  cos={review.similarity_score:.3f} rerank={rerank}  {review.review_id}  "
                f"[{review.app_name}] {review.content}"
            )
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="*", help="Query text(s)")
    parser.add_argument("--file", help="File with one query per line")
    parser.add_argument("-k", type=int, default=5, help="Final results per query")
    parser.add_argument("--candidate-k", type=int, default=20, help="KNN candidates before rerank")
    parser.add_argument("--min-similarity", type=float, default=0.3)
    args = parser.parse_args()

    queries = read_queries(args)
    if not queries:
        queries = ["지문 로그인이 계속 실패해요"]
    asyncio.run(run(queries, args.k, args.candidate_k, args.min_similarity))
    return 0


if __name__ == "__main__":
    sys.exit(main())
