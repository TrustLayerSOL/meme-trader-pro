"""CLI for bounded pre-launch funding-link pilot."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.pre_launch_funding_collection import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_RAW_PATH,
    DEFAULT_REPORT_DIR,
    run_pre_launch_funding_collection,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_pre_launch_funding_collection(
        candidates_path=args.candidates_path,
        execute=args.execute,
        max_creators=args.max_creators,
        lookback_hours=args.lookback_hours,
        max_signature_pages_per_creator=args.max_signature_pages_per_creator,
        max_transactions_per_creator=args.max_transactions_per_creator,
        max_total_transactions=args.max_total_transactions,
        request_ceiling=args.request_ceiling,
        hard_stop_projected_requests=args.hard_stop_projected_requests,
        transaction_workers=args.transaction_workers,
        output_paths={
            "raw_path": args.raw_path,
            "jsonl_path": args.jsonl_path,
            "parquet_path": args.parquet_path,
            "checkpoint_path": args.checkpoint_path,
            "report_dir": args.report_dir,
        },
    )
    funding = report.get("funding", {})
    collection = report.get("collection", {})
    print(f"report_id={report['report_id']}")
    print(f"mode={report['execution']['mode']}")
    print(f"readiness_classification={report.get('readiness_classification')}")
    print(f"selected_creators={report['scope']['selected_creators']}")
    print(f"launches_covered={collection.get('launches_covered', report['scope']['launches_covered_by_selected_creators'])}")
    print(f"requests_used={report['requests']['requests_used']}")
    print(f"transactions_fetched={collection.get('transactions_fetched', 0)}")
    print(f"funding_source_coverage={funding.get('funding_source_coverage', {})}")
    print(f"repeated_funder_coverage={funding.get('repeated_funder_coverage', {})}")
    print(f"t009_feasible={report.get('t009_feasible', False)}")
    print(f"warnings={report.get('warnings', [])}")
    print(f"summary_json={report['outputs']['report_dir']}/funding_link_pilot_summary.json")
    print(f"summary_md={report['outputs']['report_dir']}/funding_link_pilot_summary.md")
    print(f"funding_jsonl={report['outputs']['jsonl_path']}")
    print(f"funding_parquet={report['outputs']['parquet_path']}")
    print(f"raw_path={report['outputs']['raw_path']}")
    print(f"checkpoint_path={report['outputs']['checkpoint_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded pre-launch funding-link pilot.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--max-creators", type=int, default=50)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--max-signature-pages-per-creator", type=int, default=2)
    parser.add_argument("--max-transactions-per-creator", type=int, default=50)
    parser.add_argument("--max-total-transactions", type=int, default=2500)
    parser.add_argument("--request-ceiling", type=int, default=3000)
    parser.add_argument("--hard-stop-projected-requests", type=int, default=5000)
    parser.add_argument("--transaction-workers", type=int, default=16)
    parser.add_argument("--raw-path", default=DEFAULT_RAW_PATH)
    parser.add_argument("--jsonl-path", default=DEFAULT_JSONL_PATH)
    parser.add_argument("--parquet-path", default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--checkpoint-path", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
