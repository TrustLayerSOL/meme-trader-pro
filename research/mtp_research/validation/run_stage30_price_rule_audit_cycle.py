"""Offline Stage 30 selected-row and price-outlier audit cycle."""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

from research.mtp_research.validation.run_dataset_sufficiency_report import main as dataset_sufficiency_main
from research.mtp_research.validation.run_price_outlier_audit import main as price_outlier_main
from research.mtp_research.validation.run_rule_failure_review import main as rule_failure_main
from research.mtp_research.validation.run_selected_row_audit import main as selected_row_main


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    common_selected_args = [
        "run_selected_row_audit",
        "--dataset-path",
        args.dataset_path,
        "--rule-id",
        "buy_imbalance_basic",
        "--rule-id",
        "unique_actor_flow_basic",
        "--output-dir",
        str(output_dir),
    ]
    common_outlier_args = [
        "run_price_outlier_audit",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
    ]
    if args.real_only:
        common_selected_args.append("--real-only")
        common_outlier_args.append("--real-only")

    print("stage30_selected_row_audit=starting")
    with _argv(common_selected_args):
        selected_row_main()
    print("stage30_price_outlier_audit=starting")
    with _argv(common_outlier_args):
        price_outlier_main()

    if not args.skip_dependent_reviews:
        print("stage30_rule_failure_review=starting")
        rule_args = [
            "run_rule_failure_review",
            "--dataset-path",
            args.dataset_path,
            "--output-dir",
            str(output_dir),
        ]
        if args.real_only:
            rule_args.append("--real-only")
        with _argv(rule_args):
            rule_failure_main()

        print("stage30_dataset_sufficiency=starting")
        sufficiency_args = [
            "run_dataset_sufficiency_report",
            "--dataset-path",
            args.dataset_path,
            "--output-dir",
            str(output_dir),
        ]
        if args.real_only:
            sufficiency_args.append("--real-only")
        with _argv(sufficiency_args):
            dataset_sufficiency_main()

    final_recommendation = "inspect outliers manually before conservative rule review"
    print(f"final_recommendation={final_recommendation}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 30 offline price/rule audit cycle.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--skip-dependent-reviews", action="store_true")
    return parser.parse_args()


@contextmanager
def _argv(argv: list[str]):
    previous = sys.argv
    sys.argv = argv
    try:
        yield
    finally:
        sys.argv = previous


if __name__ == "__main__":
    raise SystemExit(main())
