"""CLI for the bounded P0 top-holder replay pilot."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.p0_top_holder_replay_pilot import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_RAW_PATH,
    DEFAULT_REPORT_DIR,
    DEFAULT_TARGET_CSV_PATH,
    run_p0_top_holder_replay_pilot,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_p0_top_holder_replay_pilot(
        target_csv_path=args.target_csv_path,
        execute=args.execute,
        max_mints=args.max_mints,
        max_pages_per_mint=args.max_pages_per_mint,
        max_transactions_per_mint=args.max_transactions_per_mint,
        max_total_transactions=args.max_total_transactions,
        request_ceiling=args.request_ceiling,
        transaction_workers=args.transaction_workers,
        output_paths={
            "raw_path": args.raw_path,
            "jsonl_path": args.jsonl_path,
            "parquet_path": args.parquet_path,
            "checkpoint_path": args.checkpoint_path,
            "report_dir": args.report_dir,
        },
    )
    replay = report.get("replay_quality", {})
    print(f"report_id={report['report_id']}")
    print(f"mode={report['execution']['mode']}")
    print(f"readiness_classification={report.get('readiness_classification')}")
    print(f"selected_mints={report['scope']['selected_mints']}")
    print(f"selected_milestones={report['scope']['selected_milestones']}")
    print(f"mints_completed={report['collection']['mints_completed']}")
    print(f"milestones_completed={report['collection']['milestones_completed']}")
    print(f"requests_used={report['requests']['requests_used']}")
    print(f"network_calls_made={report['network_calls_made']}")
    print(f"transactions_fetched={report['collection']['transactions_fetched']}")
    print(f"replay_quality={replay}")
    print(f"warnings={report.get('warnings', [])}")
    print(f"summary_json={report['outputs']['report_dir']}/top_holder_replay_pilot_summary.json")
    print(f"summary_md={report['outputs']['report_dir']}/top_holder_replay_pilot_summary.md")
    print(f"replay_jsonl={report['outputs']['jsonl_path']}")
    print(f"replay_parquet={report['outputs']['parquet_path']}")
    print(f"raw_path={report['outputs']['raw_path']}")
    print(f"checkpoint_path={report['outputs']['checkpoint_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded P0 top-holder replay pilot.")
    parser.add_argument("--target-csv-path", default=DEFAULT_TARGET_CSV_PATH)
    parser.add_argument("--max-mints", type=int, default=25)
    parser.add_argument("--max-pages-per-mint", type=int, default=2)
    parser.add_argument("--max-transactions-per-mint", type=int, default=200)
    parser.add_argument("--max-total-transactions", type=int, default=5_000)
    parser.add_argument("--request-ceiling", type=int, default=500)
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
