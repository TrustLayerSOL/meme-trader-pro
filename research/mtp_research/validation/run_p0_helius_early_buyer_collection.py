"""CLI for the bounded P0 early-buyer wallet-history pilot."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.p0_helius_early_buyer_collection import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_RAW_PATH,
    DEFAULT_REPORT_DIR,
    DEFAULT_TARGET_CSV_PATH,
    run_p0_early_buyer_wallet_history_collection,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_p0_early_buyer_wallet_history_collection(
        target_csv_path=args.target_csv_path,
        execute=args.execute,
        max_wallets=args.max_wallets,
        lookback_days=args.lookback_days,
        max_pages_per_wallet=args.max_pages_per_wallet,
        max_transactions_per_wallet=args.max_transactions_per_wallet,
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
    history = report.get("history", {})
    print(f"report_id={report['report_id']}")
    print(f"mode={report['execution']['mode']}")
    print(f"readiness_classification={report.get('readiness_classification')}")
    print(f"selected_wallets={report['scope']['selected_wallets']}")
    print(f"wallets_completed={report['collection']['wallets_completed']}")
    print(f"wallets_with_prior_history={report['collection']['wallets_with_prior_history']}")
    print(f"launches_covered={report['collection']['launches_covered']}")
    print(f"requests_used={report['requests']['requests_used']}")
    print(f"network_calls_made={report['network_calls_made']}")
    print(f"transactions_fetched={report['collection']['transactions_fetched']}")
    print(f"prior_history_coverage={history.get('prior_history_coverage', {})}")
    print(f"warnings={report.get('warnings', [])}")
    print(f"summary_json={report['outputs']['report_dir']}/early_buyer_wallet_history_pilot_summary.json")
    print(f"summary_md={report['outputs']['report_dir']}/early_buyer_wallet_history_pilot_summary.md")
    print(f"history_jsonl={report['outputs']['jsonl_path']}")
    print(f"history_parquet={report['outputs']['parquet_path']}")
    print(f"raw_path={report['outputs']['raw_path']}")
    print(f"checkpoint_path={report['outputs']['checkpoint_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded P0 early-buyer wallet-history pilot.")
    parser.add_argument("--target-csv-path", default=DEFAULT_TARGET_CSV_PATH)
    parser.add_argument("--max-wallets", type=int, default=1_000)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--max-pages-per-wallet", type=int, default=1)
    parser.add_argument("--max-transactions-per-wallet", type=int, default=25)
    parser.add_argument("--max-total-transactions", type=int, default=25_000)
    parser.add_argument("--request-ceiling", type=int, default=25_000)
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
