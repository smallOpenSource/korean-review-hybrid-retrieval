"""
OpenSearch content_embedding IS NULL인 review_id 추출 → MariaDB synced_to_opensearch=0 리셋.
리셋 후 sync_to_opensearch를 다시 실행하면 임베딩이 재생성됨.

Usage:
    python scripts/fix_missing_embeddings.py          # dry-run (조회만)
    python scripts/fix_missing_embeddings.py --apply  # 실제 update
"""

import os
import sys
import json
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env
_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV, override=True)

# OpenSearch config
OS_HOST = os.environ["OPENSEARCH_HOSTS"]
OS_USER = os.environ.get("OPENSEARCH_USER", "")
OS_PASS = os.environ.get("OPENSEARCH_PASSWORD", "")
OS_INDEX = os.environ.get("OPENSEARCH_INDEX_REVIEWS", "app_reviews")

# MariaDB config (from scheduler)
DB_HOST = os.environ.get("SCHEDULER_DB_HOST", os.environ.get("MYSQL_HOST", "db-host.example.com"))
DB_PORT = int(os.environ.get("SCHEDULER_DB_PORT", os.environ.get("MYSQL_PORT", "3306")))
DB_USER = os.environ.get("SCHEDULER_DB_USER", os.environ.get("MYSQL_USER", ""))
DB_PASS = os.environ.get("SCHEDULER_DB_PASSWORD", os.environ.get("MYSQL_PASSWORD", ""))
DB_NAME = os.environ.get("SCHEDULER_DB_NAME", "app_reviews_scheduler")

SEP = "=" * 60


def _os_request(method, path, body=None, timeout=120):
    """OpenSearch HTTP 요청 헬퍼."""
    url = f"{OS_HOST}/{path}"
    kwargs = dict(auth=(OS_USER, OS_PASS), verify=False, timeout=timeout)
    if method == "POST":
        resp = requests.post(url, json=body, **kwargs)
    elif method == "DELETE":
        resp = requests.delete(url, json=body, **kwargs)
    else:
        resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


def fetch_null_embedding_review_ids() -> list[str]:
    """OpenSearch scroll API로 content_embedding IS NULL인 review_id를 추출."""
    print(f"\n{SEP}")
    print(f"[1] OpenSearch에서 content_embedding IS NULL 조회")
    print(SEP)

    all_ids = []

    # Initial search with scroll
    body = {
        "size": 1000,
        "_source": ["review_id"],
        "query": {
            "bool": {
                "must_not": [{"exists": {"field": "content_embedding"}}]
            }
        }
    }

    data = _os_request("POST", f"{OS_INDEX}/_search?scroll=5m", body)
    scroll_id = data.get("_scroll_id")
    hits = data.get("hits", {}).get("hits", [])

    for hit in hits:
        rid = hit.get("_source", {}).get("review_id")
        if rid:
            all_ids.append(rid)

    print(f"  ... {len(all_ids)} IDs 추출됨")

    # Scroll through remaining
    while hits:
        data = _os_request("POST", "_search/scroll", {
            "scroll": "5m",
            "scroll_id": scroll_id
        })
        scroll_id = data.get("_scroll_id")
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits:
            rid = hit.get("_source", {}).get("review_id")
            if rid:
                all_ids.append(rid)

        if hits:
            print(f"  ... {len(all_ids)} IDs 추출됨")

    # Clear scroll
    if scroll_id:
        try:
            _os_request("DELETE", "_search/scroll", {"scroll_id": scroll_id}, timeout=10)
        except Exception:
            pass

    print(f"  ✅ 총 {len(all_ids)}건 추출 완료")
    return all_ids


def update_mariadb(review_ids: list[str], apply: bool = False):
    """MariaDB에서 synced_to_opensearch = 0 으로 리셋."""
    print(f"\n{SEP}")
    print(f"[2] MariaDB synced_to_opensearch 리셋")
    print(SEP)

    if not review_ids:
        print("  ⚠️  리셋할 review_id가 없습니다")
        return

    import pymysql

    if not apply:
        print(f"  🔍 DRY-RUN: {len(review_ids)}건 리셋 대상 (--apply 옵션으로 실행)")
        for rid in review_ids[:5]:
            print(f"     - {rid}")
        if len(review_ids) > 5:
            print(f"     - ... 외 {len(review_ids) - 5}건")
        return

    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4"
    )

    try:
        with conn.cursor() as cur:
            batch_size = 1000
            updated = 0

            for i in range(0, len(review_ids), batch_size):
                batch = review_ids[i:i + batch_size]
                placeholders = ",".join(["%s"] * len(batch))
                sql = f"UPDATE reviews SET synced_to_opensearch = 0 WHERE review_id IN ({placeholders})"
                affected = cur.execute(sql, batch)
                updated += affected
                print(f"  ... {updated}/{len(review_ids)} 업데이트 완료")

            conn.commit()
            print(f"  ✅ 총 {updated}건 리셋 완료 (MariaDB)")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="content_embedding NULL 리뷰 재동기화 준비")
    parser.add_argument("--apply", action="store_true", help="실제 MariaDB update 수행")
    args = parser.parse_args()

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"\n{'*' * 60}")
    print(f"  content_embedding NULL 리뷰 재동기화 스크립트")
    print(f"  모드: {'⚡ APPLY' if args.apply else '🔍 DRY-RUN'}")
    print(f"{'*' * 60}")

    review_ids = fetch_null_embedding_review_ids()
    update_mariadb(review_ids, apply=args.apply)

    print(f"\n{SEP}")
    print(f"[완료]")
    print(SEP)
    if args.apply and review_ids:
        print(f"  다음 명령으로 재동기화:")
        print(f"  python -m scheduler.main --run-once sync_to_opensearch --fetch-all")
    elif review_ids:
        print(f"  --apply 옵션을 추가하여 실제 실행하세요:")
        print(f"  python scripts/fix_missing_embeddings.py --apply")


if __name__ == "__main__":
    main()
