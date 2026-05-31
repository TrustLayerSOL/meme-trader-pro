"""CLI for diagnostic sample adequacy reporting."""

from __future__ import annotations

import argparse

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.sample_adequacy import SampleAdequacyAnalyzer
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    results = WalkForwardValidationStore(args.walk_forward_store_path).load_all()
    analyzer = SampleAdequacyAnalyzer(
        min_real_token_count=args.min_real_token_count,
        min_time_span_seconds=args.min_time_span_seconds,
        min_valid_test_folds=args.min_valid_test_folds,
        min_total_test_selected_count=args.min_total_test_selected_count,
        min_independent_batches=args.min_independent_batches,
    )
    report = analyzer.build_report(rows, results)
    print(f"real_token_count={report.real_token_count}")
    print(f"time_span_seconds={report.time_span_seconds}")
    print(f"valid_test_fold_count={report.valid_test_fold_count}")
    print(f"total_test_selected_count={report.total_test_selected_count}")
    print(f"adequate_for_rejection={report.adequate_for_rejection}")
    print(f"adequate_for_promotion={report.adequate_for_promotion}")
    print(f"warning_flags={report.warning_flags}")
    print(f"recommended_data_expansion={report.recommended_data_expansion}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sample adequacy report.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--walk-forward-store-path", default="data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--min-real-token-count", type=int, default=10)
    parser.add_argument("--min-time-span-seconds", type=int, default=43_200)
    parser.add_argument("--min-valid-test-folds", type=int, default=10)
    parser.add_argument("--min-total-test-selected-count", type=int, default=100)
    parser.add_argument("--min-independent-batches", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
