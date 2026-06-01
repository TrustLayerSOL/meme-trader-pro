"""CLI for bounded Pump.fun first-two-hour lifecycle raw collection."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.pumpfun_lifecycle_collector import collect_pumpfun_lifecycle


def main() -> int:
    args = parse_args()
    summary = collect_pumpfun_lifecycle(
        census_path=args.census_path,
        raw_path=args.raw_path,
        lane=args.lane,
        target_launches=args.target_launches,
        signatures_per_page=args.signatures_per_page,
        max_signature_pages_per_launch=args.max_signature_pages_per_launch,
        max_transactions_per_launch=args.max_transactions_per_launch,
        collection_method=args.collection_method,
        execute=args.execute,
    )
    for key in [
        "lane",
        "census_rows",
        "selected_launches",
        "target_launches",
        "max_lifecycle_seconds",
        "collection_method",
        "estimated_signature_requests",
        "estimated_transaction_requests_up_to",
        "network_calls",
        "launches_processed",
        "signatures_seen",
        "signatures_in_window",
        "transactions_fetched",
        "raw_inserted",
        "raw_updated",
        "warning_flags",
    ]:
        print(f"{key}={summary[key]}")
    print(f"raw_path={args.raw_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect bounded Pump.fun first-two-hour lifecycle raw transactions.")
    parser.add_argument("--census-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--raw-path", default="data/raw/helius_transactions.jsonl")
    parser.add_argument("--lane", choices=["existing", "regime"], default="existing")
    parser.add_argument("--target-launches", type=int, default=1500)
    parser.add_argument("--signatures-per-page", type=int, default=1000)
    parser.add_argument("--max-signature-pages-per-launch", type=int, default=1)
    parser.add_argument("--max-transactions-per-launch", type=int, default=100)
    parser.add_argument("--collection-method", choices=["signature_hydrate", "address_window"], default="signature_hydrate")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
