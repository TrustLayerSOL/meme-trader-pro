"""CLI for Stage 31 outlier price-path review."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.outlier_price_path_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.outlier_price_path_reviewer import OutlierPricePathReviewer
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


DEFAULT_RULE_IDS = ["buy_imbalance_basic", "unique_actor_flow_basic"]


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    events = NormalizedEventStore(args.events_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
        events = [event for event in events if event.token_mint in real_mints]
    rule_ids = args.rule_id or DEFAULT_RULE_IDS
    report = OutlierPricePathReviewer().build_report(
        rows,
        events,
        default_rule_library(),
        rule_ids,
        dataset_path=args.dataset_path,
        events_path=args.events_path,
        return_threshold=args.return_threshold,
        limit_per_rule=args.limit_per_rule,
        pre_window_seconds=args.pre_window_seconds,
        post_window_seconds=args.post_window_seconds,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"reviewed_count={report.reviewed_count}")
    print(f"classification_counts={report.classification_counts}")
    print(f"token_counts={report.token_counts}")
    print(f"recommended_next_action={report.recommended_next_action}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review outlier row price paths.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--rule-id", action="append")
    parser.add_argument("--return-threshold", type=float, default=1.0)
    parser.add_argument("--limit-per-rule", type=int, default=25)
    parser.add_argument("--pre-window-seconds", type=int, default=300)
    parser.add_argument("--post-window-seconds", type=int)
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
