"""Offline post-backfill rebuild and diagnostic review helper."""

from __future__ import annotations

import argparse
import subprocess
import sys

from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.fold_sufficiency_analyzer import FoldSufficiencyAnalyzer
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_fold_sufficiency_report import parse_args as parse_fold_args
from research.mtp_research.validation.run_fold_sufficiency_report import build_and_write_report


def main() -> int:
    args = parse_args()
    commands = build_commands(args)
    outputs = []
    for command in commands:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        outputs.append(completed.stdout)

    raw_rows = len(RawTransactionStore().load_all())
    diagnostic_rows = ResearchDatasetStore("data/backtests/diagnostics/research_dataset_nearest300.jsonl").load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry()
        diagnostic_rows = [row for row in diagnostic_rows if row.token_mint in real_mints]

    fold_args = parse_fold_args_from_values(args.real_only)
    fold_report, fold_markdown, fold_json = build_and_write_report(fold_args)

    print(f"raw_rows={raw_rows}")
    print(f"diagnostic_rows={len(diagnostic_rows)}")
    print(f"time_span_seconds={fold_report.time_span_seconds}")
    print(f"best_fold_config={fold_report.best_config_name}")
    print(f"recommended_next_action={fold_report.recommended_next_action}")
    print(f"fold_sufficiency_markdown_path={fold_markdown}")
    print(f"fold_sufficiency_json_path={fold_json}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline post-backfill rebuild and review.")
    parser.add_argument("--max-snapshots", type=int, default=1000)
    parser.add_argument("--diagnostic-entry-max-staleness-sec", type=int, default=120)
    parser.add_argument("--nearest-entry-max-staleness-sec", type=int, default=300)
    parser.add_argument("--real-only", action="store_true")
    return parser.parse_args()


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    python = sys.executable
    return [
        [
            python,
            "-m",
            "research.mtp_research.pipeline.run_full_research_cycle",
            "--skip-backfill",
            "--max-snapshots",
            str(args.max_snapshots),
        ],
        [
            python,
            "-m",
            "research.mtp_research.validation.run_build_outcome_labels",
            "--allow-nearest-entry-fallback",
            "--entry-max-staleness-sec",
            str(args.diagnostic_entry_max_staleness_sec),
            "--nearest-entry-max-staleness-sec",
            str(args.nearest_entry_max_staleness_sec),
            "--max-snapshots",
            str(args.max_snapshots),
            "--outcomes-path",
            "data/backtests/diagnostics/outcome_labels_nearest300.jsonl",
        ],
        [
            python,
            "-m",
            "research.mtp_research.validation.run_build_research_dataset",
            "--outcomes-path",
            "data/backtests/diagnostics/outcome_labels_nearest300.jsonl",
            "--dataset-path",
            "data/backtests/diagnostics/research_dataset_nearest300.jsonl",
            "--min-label-quality",
            "sparse",
            "--require-forward-return",
        ],
        [
            python,
            "-m",
            "research.mtp_research.validation.run_price_coverage_report",
            *(["--real-only"] if args.real_only else []),
        ],
        [
            python,
            "-m",
            "research.mtp_research.validation.run_dataset_sufficiency_report",
            *(["--real-only"] if args.real_only else []),
        ],
        [
            python,
            "-m",
            "research.mtp_research.validation.run_diagnostic_validation_review",
        ],
    ]


def parse_fold_args_from_values(real_only: bool) -> argparse.Namespace:
    original = sys.argv
    try:
        sys.argv = ["run_fold_sufficiency_report"] + (["--real-only"] if real_only else [])
        return parse_fold_args()
    finally:
        sys.argv = original


if __name__ == "__main__":
    raise SystemExit(main())
