"""CLI for strict-cohort holder-state offline replay rollout."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.holder_state_rollout import (
    build_missing_coverage_diagnostics,
    build_negative_balance_diagnostics,
    build_holder_state_rollout,
    write_missing_coverage_diagnostics,
    write_negative_balance_diagnostics,
    write_holder_state_rollout_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_DATASET_DIR = data_lake_path("data", "backtests", "holder_state")
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "holder_state_strict_cohort"
)
DEFAULT_NEGATIVE_BALANCE_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "holder_state_negative_balance"
)
DEFAULT_MISSING_COVERAGE_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "holder_state_missing_coverage"
)


def main() -> int:
    args = parse_args()
    diagnostics = build_negative_balance_diagnostics(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        max_launches=args.max_launches,
    )
    diagnostic_paths = write_negative_balance_diagnostics(
        diagnostics,
        output_dir=args.negative_balance_report_dir,
    )
    rollout = build_holder_state_rollout(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        max_launches=args.max_launches,
    )
    paths = write_holder_state_rollout_outputs(
        rollout,
        dataset_dir=args.dataset_dir,
        report_dir=args.report_dir,
    )
    missing_coverage = build_missing_coverage_diagnostics(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        rollout=rollout,
        max_launches=args.max_launches,
    )
    missing_coverage_paths = write_missing_coverage_diagnostics(
        missing_coverage,
        output_dir=args.missing_coverage_report_dir,
    )
    print(f"readiness_classification={rollout['readiness_classification']}")
    print(f"launches_attempted={rollout['launches_attempted']}")
    print(f"snapshots_expected={rollout['snapshots_expected']}")
    print(f"snapshot_rows_written={rollout['snapshot_rows_written']}")
    print(f"snapshots_built={rollout['snapshots_built']}")
    print(f"snapshots_with_holder_values={rollout['snapshots_with_holder_values']}")
    print(f"valid_zero_holder_snapshots={rollout['valid_zero_holder_snapshots']}")
    print(f"insufficient_prior_state_snapshots={rollout['insufficient_prior_state_snapshots']}")
    print(f"missing_event_data_snapshots={rollout['missing_event_data_snapshots']}")
    print(f"holder_count_coverage_pct={rollout['holder_count_coverage_pct']:.2f}")
    print(f"top_holder_share_coverage_pct={rollout['top_holder_share_coverage_pct']:.2f}")
    print(f"top_10_holder_share_coverage_pct={rollout['top_10_holder_share_coverage_pct']:.2f}")
    print(f"creator_holder_share_coverage_pct={rollout['creator_holder_share_coverage_pct']:.2f}")
    print(f"suspicious_negative_balance_count={rollout['suspicious_negative_balance_count']}")
    print(f"original_negative_balance_count={diagnostics['total_negative_balance_events']}")
    print(f"unique_negative_balance_launches={diagnostics['unique_launches_affected']}")
    print(f"excluded_ambiguous_event_count={rollout['excluded_ambiguous_event_count']}")
    print(f"excluded_program_pool_account_event_count={rollout['excluded_program_pool_account_event_count']}")
    print(f"sell_without_prior_observed_balance_count={rollout['sell_without_prior_observed_balance_count']}")
    print(f"sell_without_prior_observed_balance_unique_launches={rollout['sell_without_prior_observed_balance_unique_launches']}")
    print(f"duplicate_event_skipped_count={rollout['duplicate_event_skipped_count']}")
    print(f"t001_v2_feasible={rollout['t001_v2_feasible']}")
    print(f"t002_v2_feasible={rollout['t002_v2_feasible']}")
    for key, path in diagnostic_paths.items():
        print(f"{key}={path}")
    for key, path in missing_coverage_paths.items():
        print(f"{key}={path}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict-cohort holder-state offline replay rollout.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--negative-balance-report-dir", default=DEFAULT_NEGATIVE_BALANCE_REPORT_DIR)
    parser.add_argument("--missing-coverage-report-dir", default=DEFAULT_MISSING_COVERAGE_REPORT_DIR)
    parser.add_argument("--max-launches", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
