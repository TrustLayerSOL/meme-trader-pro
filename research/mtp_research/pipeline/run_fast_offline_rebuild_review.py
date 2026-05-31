"""Fast observable offline rebuild and review orchestration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from research.mtp_research.pipeline.offline_rebuild_profile import (
    OfflineRebuildProfile,
    OfflineRebuildStepProfile,
    utc_now_iso,
)
from research.mtp_research.pipeline.offline_rebuild_profile_report import (
    write_profile_json,
    write_profile_markdown,
)


PATHS = {
    "raw": Path("data/raw/helius_transactions.jsonl"),
    "events": Path("data/normalized/events.jsonl"),
    "features": Path("data/features/feature_snapshots.jsonl"),
    "clean_outcomes": Path("data/backtests/outcome_labels.jsonl"),
    "clean_dataset": Path("data/backtests/research_dataset.jsonl"),
    "diagnostic_outcomes": Path("data/backtests/diagnostics/outcome_labels_nearest300.jsonl"),
    "diagnostic_dataset": Path("data/backtests/diagnostics/research_dataset_nearest300.jsonl"),
}


def main() -> int:
    args = parse_args()
    profile = OfflineRebuildProfile.create(
        {
            "real_only": args.real_only,
            "min_liquidity_usd": args.min_liquidity_usd,
            "max_snapshots": args.max_snapshots,
            "snapshot_selection_strategy": args.snapshot_selection_strategy,
            "max_snapshots_per_token": args.max_snapshots_per_token,
            "min_time_gap_seconds": args.min_time_gap_seconds,
            "nearest_entry_max_staleness_sec": args.nearest_entry_max_staleness_sec,
        }
    )
    markdown_path = None
    json_path = None
    try:
        print_counts("before_counts")
        for step_name, command, input_key, output_key, skipped in build_steps(args):
            run_profiled_step(
                profile=profile,
                step_name=step_name,
                command=command,
                input_count=count_rows(PATHS[input_key]) if input_key else 0,
                output_path=PATHS[output_key] if output_key else None,
                skipped=skipped,
            )
        print_counts("after_counts")
        print_artifact_span_guidance()
    except KeyboardInterrupt:
        profile.warning_flags.append("interrupted")
        print("interrupted=True", flush=True)
        print_counts("partial_counts")
    finally:
        profile.finish()
        if not args.skip_reports:
            markdown_path = write_profile_markdown(profile)
            json_path = write_profile_json(profile)
            print(f"profile_markdown_path={markdown_path}", flush=True)
            print(f"profile_json_path={json_path}", flush=True)

    print("step_timings=" + str({step.step_name: step.elapsed_seconds for step in profile.steps}), flush=True)
    print("network_calls=0", flush=True)
    return 0 if "interrupted" not in profile.warning_flags else 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fast offline rebuild and review.")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    parser.add_argument("--max-snapshots", type=int, default=1000)
    parser.add_argument("--snapshot-selection-strategy", default="head")
    parser.add_argument("--max-snapshots-per-token", type=int)
    parser.add_argument("--min-time-gap-seconds", type=int)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--nearest-entry-max-staleness-sec", type=int, default=300)
    parser.add_argument("--skip-clean-outcomes", action="store_true")
    parser.add_argument("--skip-diagnostic-outcomes", action="store_true")
    parser.add_argument("--skip-clean-dataset", action="store_true")
    parser.add_argument("--skip-diagnostic-dataset", action="store_true")
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--stop-after-snapshots", type=int)
    parser.add_argument("--timing", action="store_true")
    return parser.parse_args()


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str], str | None, str | None, bool]]:
    python = sys.executable
    real_args = ["--real-only", "--min-liquidity-usd", str(args.min_liquidity_usd)] if args.real_only else []
    stop_args = (
        ["--stop-after-snapshots", str(args.stop_after_snapshots)]
        if args.stop_after_snapshots is not None
        else []
    )
    timing_args = ["--timing"] if args.timing else []
    selection_args = ["--snapshot-selection-strategy", args.snapshot_selection_strategy]
    if args.max_snapshots_per_token is not None:
        selection_args.extend(["--max-snapshots-per-token", str(args.max_snapshots_per_token)])
    if args.min_time_gap_seconds is not None:
        selection_args.extend(["--min-time-gap-seconds", str(args.min_time_gap_seconds)])
    return [
        (
            "clean_outcomes",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_build_outcome_labels",
                "--max-snapshots",
                str(args.max_snapshots),
                *selection_args,
                "--progress-every",
                str(args.progress_every),
                "--overwrite",
                *real_args,
                *stop_args,
                *timing_args,
            ],
            "features",
            "clean_outcomes",
            args.skip_clean_outcomes,
        ),
        (
            "diagnostic_outcomes",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_build_outcome_labels",
                "--allow-nearest-entry-fallback",
                "--nearest-entry-max-staleness-sec",
                str(args.nearest_entry_max_staleness_sec),
                "--max-snapshots",
                str(args.max_snapshots),
                *selection_args,
                "--outcomes-path",
                str(PATHS["diagnostic_outcomes"]),
                "--progress-every",
                str(args.progress_every),
                "--overwrite",
                *real_args,
                *stop_args,
                *timing_args,
            ],
            "features",
            "diagnostic_outcomes",
            args.skip_diagnostic_outcomes,
        ),
        (
            "clean_dataset",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_build_research_dataset",
                "--min-label-quality",
                "sparse",
                "--require-forward-return",
                "--progress-every",
                str(args.progress_every),
                "--overwrite",
                *real_args,
                *timing_args,
            ],
            "clean_outcomes",
            "clean_dataset",
            args.skip_clean_dataset,
        ),
        (
            "diagnostic_dataset",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_build_research_dataset",
                "--outcomes-path",
                str(PATHS["diagnostic_outcomes"]),
                "--dataset-path",
                str(PATHS["diagnostic_dataset"]),
                "--min-label-quality",
                "sparse",
                "--require-forward-return",
                "--progress-every",
                str(args.progress_every),
                "--overwrite",
                *real_args,
                *timing_args,
            ],
            "diagnostic_outcomes",
            "diagnostic_dataset",
            args.skip_diagnostic_dataset,
        ),
        (
            "price_coverage_report",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_price_coverage_report",
                "--output-dir",
                "data/backtests/diagnostics/reports",
                *real_args,
            ],
            "clean_outcomes",
            None,
            args.skip_reports,
        ),
        (
            "dataset_sufficiency_report",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_dataset_sufficiency_report",
                "--output-dir",
                "data/backtests/diagnostics/reports",
                *real_args,
            ],
            "clean_dataset",
            None,
            args.skip_reports,
        ),
        (
            "fold_sufficiency_report",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_fold_sufficiency_report",
                *real_args,
            ],
            "diagnostic_dataset",
            None,
            args.skip_reports,
        ),
    ]


def run_profiled_step(
    profile: OfflineRebuildProfile,
    step_name: str,
    command: list[str],
    input_count: int,
    output_path: Path | None,
    skipped: bool,
) -> None:
    step = OfflineRebuildStepProfile(
        step_name=step_name,
        started_at=utc_now_iso(),
        input_count=input_count,
        output_count=count_rows(output_path) if output_path else 0,
        skipped=skipped,
        metadata_json={"command": command},
    )
    profile.steps.append(step)
    if skipped:
        step.finish(output_count=step.output_count, warning_flags=["skipped_by_flag"])
        print(f"step_skipped={step_name}", flush=True)
        return

    print(f"step_start={step_name}", flush=True)
    run_command_step(command)
    step.finish(output_count=count_rows(output_path) if output_path else 0)
    print(f"step_done={step_name} elapsed_seconds={step.elapsed_seconds}", flush=True)


def run_command_step(command: list[str]) -> None:
    subprocess.run(command, check=True)


def print_counts(prefix: str) -> None:
    for name, path in PATHS.items():
        print(f"{prefix}.{name}={count_rows(path)}", flush=True)


def count_rows(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def print_artifact_span_guidance() -> None:
    raw_span = artifact_span(PATHS["raw"], "block_time")
    diagnostic_span = artifact_span(PATHS["diagnostic_dataset"], "snapshot_ts")
    if (
        raw_span is not None
        and diagnostic_span is not None
        and raw_span > 0
        and diagnostic_span < raw_span * 0.5
    ):
        print("artifact_span_warning=diagnostic_dataset_span_much_smaller_than_raw", flush=True)
        print(
            "recommended_full_span_command="
            "./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review "
            "--real-only --snapshot-selection-strategy per_token_even "
            "--max-snapshots-per-token 1000 --min-time-gap-seconds 60 --timing",
            flush=True,
        )


def artifact_span(path: Path, time_field: str) -> int | None:
    if not path.exists():
        return None
    times: list[int] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            value = json.loads(text).get(time_field)
            if value is not None:
                times.append(int(value))
    if not times:
        return None
    return max(times) - min(times)


if __name__ == "__main__":
    raise SystemExit(main())
