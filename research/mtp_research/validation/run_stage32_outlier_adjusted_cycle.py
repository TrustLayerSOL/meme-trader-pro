"""Offline Stage 32 outlier-adjusted diagnostic cycle."""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

from research.mtp_research.validation.run_outlier_adjusted_rule_report import main as adjusted_main
from research.mtp_research.validation.run_outlier_price_path_review import main as price_path_main
from research.mtp_research.validation.run_rule_robust_return_report import main as robust_main


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    real_arg = ["--real-only"] if args.real_only else []

    print("stage32_outlier_price_path_review=starting")
    with _argv([
        "run_outlier_price_path_review",
        "--dataset-path",
        args.dataset_path,
        "--events-path",
        args.events_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        price_path_main()

    print("stage32_rule_robust_return_report=starting")
    with _argv([
        "run_rule_robust_return_report",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        robust_main()

    print("stage32_outlier_adjusted_rule_report=starting")
    with _argv([
        "run_outlier_adjusted_rule_report",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        adjusted_main()

    final_recommendation = "separate outlier metrics before bounded evidence expansion"
    print(f"final_recommendation={final_recommendation}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 32 offline outlier-adjusted cycle.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
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
