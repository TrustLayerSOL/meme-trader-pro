"""CLI for bounded creator/funder transfer graph pilot."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.p0_creator_funder_transfer_graph_collection import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_EARLY_BUYER_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_RAW_DIR,
    DEFAULT_REPORT_DIR,
    DEFAULT_TARGET_PATH,
    DEFAULT_TOP_HOLDER_PATH,
    run_creator_funder_transfer_graph_collection,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_creator_funder_transfer_graph_collection(
        target_path=args.target_path,
        candidates_path=args.candidates_path,
        early_buyer_path=args.early_buyer_path,
        top_holder_path=args.top_holder_path,
        execute=args.execute,
        lookback_hours=args.lookback_hours,
        max_pages_per_address=args.max_pages_per_address,
        max_transactions_per_address=args.max_transactions_per_address,
        max_total_transactions=args.max_total_transactions,
        request_ceiling=args.request_ceiling,
        credit_cap=args.credit_cap,
        transaction_workers=args.transaction_workers,
        output_paths={
            "raw_dir": args.raw_dir,
            "jsonl_path": args.jsonl_path,
            "parquet_path": args.parquet_path,
            "checkpoint_path": args.checkpoint_path,
            "report_dir": args.report_dir,
        },
    )
    quality = report.get("quality", {})
    print(f"report_id={report['report_id']}")
    print(f"mode={report['execution']['mode']}")
    print(f"readiness_classification={report.get('readiness_classification')}")
    print(f"creators_selected={report['scope']['creators_selected']}")
    print(f"candidate_funders_selected={report['scope']['candidate_funders_selected']}")
    print(f"launches_covered={report['scope']['launches_covered']}")
    print(f"creators_attempted={report.get('collection', {}).get('creators_attempted', 0)}")
    print(f"creators_completed={report.get('collection', {}).get('creators_completed', 0)}")
    print(f"requests_used={report['requests']['requests_used']}")
    print(f"actual_helius_credits_estimate={report['requests']['actual_helius_credits_estimate']}")
    print(f"transactions_fetched={report.get('collection', {}).get('transactions_fetched', 0)}")
    print(f"raw_responses_preserved={report.get('raw', {}).get('raw_responses_preserved', 0)}")
    print(f"candidate_funder_coverage={quality.get('candidate_funder_coverage', {})}")
    print(f"shared_funder_coverage={quality.get('shared_funder_coverage', {})}")
    print(f"time_linked_funding_coverage={quality.get('time_linked_funding_coverage', {})}")
    print(f"creator_wallet_relation_coverage={quality.get('creator_wallet_relation_coverage', {})}")
    print(f"warnings={report.get('warnings', [])}")
    print(f"summary_json={report['outputs']['report_dir']}/creator_funder_transfer_graph_pilot_summary.json")
    print(f"summary_md={report['outputs']['report_dir']}/creator_funder_transfer_graph_pilot_summary.md")
    print(f"jsonl_path={report['outputs']['jsonl_path']}")
    print(f"parquet_path={report['outputs']['parquet_path']}")
    print(f"raw_path={report['outputs']['raw_path']}")
    print(f"checkpoint_path={report['outputs']['checkpoint_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded creator/funder transfer graph pilot.")
    parser.add_argument("--target-path", default=DEFAULT_TARGET_PATH)
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--early-buyer-path", default=DEFAULT_EARLY_BUYER_PATH)
    parser.add_argument("--top-holder-path", default=DEFAULT_TOP_HOLDER_PATH)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--max-pages-per-address", type=int, default=2)
    parser.add_argument("--max-transactions-per-address", type=int, default=200)
    parser.add_argument("--max-total-transactions", type=int, default=5000)
    parser.add_argument("--request-ceiling", type=int, default=25000)
    parser.add_argument("--credit-cap", type=int, default=25000)
    parser.add_argument("--transaction-workers", type=int, default=16)
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--jsonl-path", default=DEFAULT_JSONL_PATH)
    parser.add_argument("--parquet-path", default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--checkpoint-path", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
