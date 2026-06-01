"""CLI for native SOL proxy diagnostic quality gating."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.native_sol_proxy_quality import NativeSolProxyQualityAnalyzer
from research.mtp_research.validation.native_sol_proxy_quality_models import NativeSolProxyQualityConfig
from research.mtp_research.validation.native_sol_proxy_quality_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry()
        rows = [row for row in rows if row.token_mint in real_mints]
    events = NormalizedEventStore(args.events_path).load_all()
    config = NativeSolProxyQualityConfig(
        max_abs_forward_return=args.max_abs_forward_return,
        max_abs_runup=args.max_abs_runup,
        max_price_jump_ratio=args.max_price_jump_ratio,
        min_proxy_price_points_in_horizon=args.min_proxy_price_points_in_horizon,
        max_gap_between_proxy_points_sec=args.max_gap_between_proxy_points_sec,
        require_non_proxy_anchor=args.require_non_proxy_anchor,
    )
    passed_rows, _decisions, report = NativeSolProxyQualityAnalyzer().filter_rows(
        rows,
        events,
        config,
        dataset_path=args.dataset_path,
    )
    if not args.dry_run:
        ResearchDatasetStore(args.output_dataset_path).replace_all(passed_rows)
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"row_count={report.row_count}")
    print(f"native_proxy_backed_count={report.native_proxy_backed_count}")
    print(f"native_proxy_passed_count={report.native_proxy_passed_count}")
    print(f"native_proxy_failed_count={report.native_proxy_failed_count}")
    print(f"pass_rate={report.pass_rate}")
    print(f"failure_reason_counts={report.failure_reason_counts}")
    print(f"output_dataset_path={args.output_dataset_path}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build native-SOL-proxy-quality-gated diagnostic dataset.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--output-dataset-path", default="data/backtests/diagnostics/research_dataset_native_sol_proxy_gated.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--max-abs-forward-return", type=float, default=2.0)
    parser.add_argument("--max-abs-runup", type=float, default=5.0)
    parser.add_argument("--max-price-jump-ratio", type=float, default=25.0)
    parser.add_argument("--min-proxy-price-points-in-horizon", type=int, default=2)
    parser.add_argument("--max-gap-between-proxy-points-sec", type=int, default=300)
    parser.add_argument("--require-non-proxy-anchor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
