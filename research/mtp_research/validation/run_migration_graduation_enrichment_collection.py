"""CLI for bounded migration/graduation enrichment collection."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.migration_graduation_enrichment_collection import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_RAW_DIR,
    DEFAULT_REPORT_DIR,
    run_migration_graduation_enrichment_collection,
)


def main() -> int:
    args = parse_args()
    result = run_migration_graduation_enrichment_collection(
        candidates_path=args.candidates_path,
        execute=args.execute,
        mint_limit=args.mint_limit,
        window=args.window,
        max_signature_pages_per_mint=args.max_signature_pages_per_mint,
        max_transactions_per_mint=args.max_transactions_per_mint,
        max_total_transactions=args.max_total_transactions,
        request_ceiling=args.request_ceiling,
        hard_stop_projected_requests=args.hard_stop_projected_requests,
        output_flush_interval_mints=args.output_flush_interval_mints,
        transaction_workers=args.transaction_workers,
        prefer_address_window_fetch=not args.disable_address_window_fetch,
        output_paths={
            "raw_dir": args.raw_dir,
            "jsonl_path": args.jsonl_path,
            "parquet_path": args.parquet_path,
            "checkpoint_path": args.checkpoint_path,
            "report_dir": args.report_dir,
        },
    )
    collection = result.get("collection", {})
    labels = result.get("labels", {})
    print(f"report_id={result['report_id']}")
    print(f"mode={result['execution']['mode']}")
    print(f"readiness_classification={result['readiness_classification']}")
    print(f"selected_mints={result['scope']['selected_mints']}")
    print(f"selected_creators={result['scope']['selected_creators']}")
    print(f"window={result['scope']['window']}")
    print(f"requests_used={result['requests']['requests_used']}")
    print(f"stopped_due_ceiling={result['requests']['stopped_due_ceiling']}")
    print(f"mints_attempted={collection.get('mints_attempted', 0)}")
    print(f"mints_completed={collection.get('mints_completed', 0)}")
    print(f"signatures_fetched={collection.get('signatures_fetched', 0)}")
    print(f"transactions_fetched={collection.get('transactions_fetched', 0)}")
    print(f"unique_migrated_graduated_mints_detected={labels.get('unique_migrated_graduated_mints_detected', 0)}")
    print(f"warnings={result.get('warnings', [])}")
    print(f"summary_json={result['outputs']['report_dir']}/migration_graduation_collection_summary.json")
    print(f"summary_md={result['outputs']['report_dir']}/migration_graduation_collection_summary.md")
    print(f"candidate_jsonl={result['outputs']['jsonl_path']}")
    print(f"candidate_parquet={result['outputs']['parquet_path']}")
    print(f"checkpoint_path={result['outputs']['checkpoint_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded migration/graduation enrichment collection.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--mint-limit", type=int, default=100)
    parser.add_argument("--window", default="24h", choices=["24h", "72h", "7d"])
    parser.add_argument("--max-signature-pages-per-mint", type=int, default=3)
    parser.add_argument("--max-transactions-per-mint", type=int, default=25)
    parser.add_argument("--max-total-transactions", type=int, default=2500)
    parser.add_argument("--request-ceiling", type=int, default=3000)
    parser.add_argument("--hard-stop-projected-requests", type=int, default=5000)
    parser.add_argument("--output-flush-interval-mints", type=int, default=25)
    parser.add_argument("--transaction-workers", type=int, default=8)
    parser.add_argument("--disable-address-window-fetch", action="store_true")
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--jsonl-path", default=DEFAULT_JSONL_PATH)
    parser.add_argument("--parquet-path", default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--checkpoint-path", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
