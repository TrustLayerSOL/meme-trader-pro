"""Offline Stage 31 outlier price-path and robust-return review cycle."""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

from research.mtp_research.validation.run_outlier_price_path_review import main as price_path_main
from research.mtp_research.validation.run_price_outlier_audit import main as price_outlier_main
from research.mtp_research.validation.run_rule_robust_return_report import main as robust_return_main
from research.mtp_research.validation.run_selected_row_audit import main as selected_row_main


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    real_arg = ["--real-only"] if args.real_only else []

    print("stage31_outlier_price_path_review=starting")
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

    print("stage31_rule_robust_return_report=starting")
    with _argv([
        "run_rule_robust_return_report",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        robust_return_main()

    print("stage31_selected_row_audit=starting")
    with _argv([
        "run_selected_row_audit",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        selected_row_main()

    print("stage31_price_outlier_audit=starting")
    with _argv([
        "run_price_outlier_audit",
        "--dataset-path",
        args.dataset_path,
        "--output-dir",
        str(output_dir),
        *real_arg,
    ]):
        price_outlier_main()

    final_recommendation = "separate outlier metrics before bounded evidence expansion"
    print(f"final_recommendation={final_recommendation}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 31 offline outlier review cycle.")
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
