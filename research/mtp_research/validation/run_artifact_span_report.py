"""CLI for reporting whether derived artifacts cover raw evidence spans."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.artifact_span_report import compare_artifact_spans
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    raw_records = RawTransactionStore(args.raw_path).load_all()
    normalized_events = NormalizedEventStore(args.events_path).load_all()
    feature_snapshots = FeatureSnapshotStore(args.features_path).load_all()
    clean_outcome_labels = OutcomeLabelStore(args.clean_outcomes_path).load_all()
    clean_dataset_rows = ResearchDatasetStore(args.clean_dataset_path).load_all()
    diagnostic_outcome_labels = OutcomeLabelStore(args.diagnostic_outcomes_path).load_all()
    diagnostic_dataset_rows = ResearchDatasetStore(args.diagnostic_dataset_path).load_all()

    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        raw_records = _filter_by_token(raw_records, real_mints)
        normalized_events = _filter_by_token(normalized_events, real_mints)
        feature_snapshots = _filter_by_token(feature_snapshots, real_mints)
        clean_outcome_labels = _filter_by_token(clean_outcome_labels, real_mints)
        clean_dataset_rows = _filter_by_token(clean_dataset_rows, real_mints)
        diagnostic_outcome_labels = _filter_by_token(diagnostic_outcome_labels, real_mints)
        diagnostic_dataset_rows = _filter_by_token(diagnostic_dataset_rows, real_mints)

    report = compare_artifact_spans(
        raw_records=raw_records,
        normalized_events=normalized_events,
        feature_snapshots=feature_snapshots,
        clean_outcome_labels=clean_outcome_labels,
        clean_dataset_rows=clean_dataset_rows,
        diagnostic_outcome_labels=diagnostic_outcome_labels,
        diagnostic_dataset_rows=diagnostic_dataset_rows,
    )
    report["metadata"] = {
        "real_only": args.real_only,
        "min_liquidity_usd": args.min_liquidity_usd,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    markdown_path, json_path = write_reports(report, Path(args.output_dir))

    for section in (
        "raw",
        "normalized_events",
        "feature_snapshots",
        "clean_outcomes",
        "clean_dataset",
        "diagnostic_outcomes",
        "diagnostic_dataset",
    ):
        print_section(section, report[section])
    print(f"warning_flags={report['warning_flags']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report artifact time-span coverage.")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--raw-path", default="data/raw/helius_transactions.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--features-path", default="data/features/feature_snapshots.jsonl")
    parser.add_argument("--clean-outcomes-path", default="data/backtests/outcome_labels.jsonl")
    parser.add_argument("--clean-dataset-path", default="data/backtests/research_dataset.jsonl")
    parser.add_argument(
        "--diagnostic-outcomes-path",
        default="data/backtests/diagnostics/outcome_labels_nearest300.jsonl",
    )
    parser.add_argument(
        "--diagnostic-dataset-path",
        default="data/backtests/diagnostics/research_dataset_nearest300.jsonl",
    )
    return parser.parse_args()


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"artifact_span_report_{suffix}.json"
    markdown_path = output_dir / f"artifact_span_report_{suffix}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return markdown_path, json_path


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Artifact Span Report",
        "",
        "Offline-only report comparing raw evidence coverage to derived validation artifacts.",
        "",
        "| Artifact | Rows | Tokens | Time span seconds |",
        "| --- | ---: | ---: | ---: |",
    ]
    for section in (
        "raw",
        "normalized_events",
        "feature_snapshots",
        "clean_outcomes",
        "clean_dataset",
        "diagnostic_outcomes",
        "diagnostic_dataset",
    ):
        summary = report[section]
        lines.append(
            f"| {section} | {summary['row_count']} | {summary['token_count']} | "
            f"{summary['time_span_seconds']} |"
        )
    lines.extend(["", f"Warning flags: {report['warning_flags']}", ""])
    return "\n".join(lines)


def print_section(name: str, summary: dict[str, Any]) -> None:
    print(f"{name}.row_count={summary['row_count']}")
    print(f"{name}.token_count={summary['token_count']}")
    print(f"{name}.time_span_seconds={summary['time_span_seconds']}")


def _filter_by_token(rows: list[Any], token_mints: set[str]) -> list[Any]:
    return [row for row in rows if getattr(row, "token_mint", None) in token_mints]


if __name__ == "__main__":
    raise SystemExit(main())
