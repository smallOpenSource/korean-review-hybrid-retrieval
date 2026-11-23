#!/usr/bin/env python3
"""
Department routing demo (hybrid scoring), no database required.

DepartmentRoutingService loads the department hierarchy from MySQL and falls back
to app/config/department_hierarchy.yaml (a generic, fictional org chart) when the
database is not reachable. For each text it computes:

  combined = 0.3 * keyword(IDF) score + 0.4 * BGE-M3 cosine + 0.3 * bge-reranker score

Usage:
    python scripts/demo_department_routing.py "카드 결제가 승인 거절돼요"
    python scripts/demo_department_routing.py --file samples/queries_sample.txt
"""
import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.services.department_routing_service import DepartmentRoutingService  # noqa: E402


def read_texts(args) -> list:
    texts = list(args.text)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    texts.append(line)
    return texts


async def run(texts, top_k: int):
    service = DepartmentRoutingService()
    for text in texts:
        result = await service.route(text, top_k=top_k)
        print("=" * 80)
        print(f"Text: {text}")
        primary = result.primary.to_dict()
        print(f"Primary  : {primary['code']} ({primary['division_name']} / {primary['name']})")
        print(f"  scores : {primary['scores']}  keywords={primary['matched_keywords']}")
        for cand in result.secondary:
            c = cand.to_dict()
            print(f"Secondary: {c['code']} ({c['name']}) role={c['role']} scores={c['scores']}")
        print(f"Escalation: {result.escalation_required} level={result.escalation_level} "
              f"urgency={result.urgency} sla_hours={result.sla_hours}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text", nargs="*", help="Complaint text(s)")
    parser.add_argument("--file", help="File with one text per line")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    texts = read_texts(args) or ["카드 결제가 승인 거절돼요"]
    asyncio.run(run(texts, args.top_k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
