"""CLI for the dry-run migration targeted discovery plan."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.migration_targeted_discovery_plan import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RAW_TRANSACTIONS_PATH,
    build_migration_targeted_discovery_plan,
    write_migration_targeted_discovery_plan_outputs,
)


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("--dry-run is required; this command must not fetch data")
    report = build_migration_targeted_discovery_plan(raw_transactions_path=args.raw_transactions_path)
    paths = write_migration_targeted_discovery_plan_outputs(report, output_dir=args.output_dir)
    summary = report["evidence_summary"]
    print(f"report_id={report['report_id']}")
    print(f"classification={report['classification']}")
    print(f"raw_transaction_rows_scanned={summary['raw_transaction_rows_scanned']}")
    print(f"exact_migration_event_count={summary['exact_migration_event_count']}")
    print(f"exact_migration_mint_count={summary['exact_migration_mint_count']}")
    print(f"migration_like_false_positive_count={summary['migration_like_false_positive_count']}")
    print(f"network_calls_used={report['network_calls_used']}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    print(f"json_path={paths['json_path']}")
    print(f"markdown_path={paths['markdown_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run targeted migration discovery planner.")
    parser.add_argument("--raw-transactions-path", default=DEFAULT_RAW_TRANSACTIONS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
