"""CLI for local price-quality failure analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.price_quality_failure_analysis import (
    PriceQualityFailureAnalyzer,
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.price_quality_gate import PriceQualityGate
from research.mtp_research.validation.price_quality_models import PriceQualityConfig
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    config = PriceQualityConfig(
        max_entry_staleness_sec=args.max_entry_staleness_sec,
        min_future_price_points=args.min_future_price_points,
        allow_nearest_fallback=args.allow_nearest_fallback,
    )
    _passed, decisions, gate_report = PriceQualityGate().filter_rows(
        rows,
        config,
        dataset_path=args.dataset_path,
    )
    report = PriceQualityFailureAnalyzer().build_report(rows, decisions, gate_report, top_n=args.top_n)
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"input_row_count={report.input_row_count}")
    print(f"failed_row_count={report.failed_row_count}")
    print(f"passed_row_count={report.passed_row_count}")
    print(f"failed_token_count={report.failed_token_count}")
    print(f"failure_reason_counts={report.failure_reason_counts}")
    print(f"recommended_next_action={report.recommended_next_action}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze strict price-quality gate failures by token.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--max-entry-staleness-sec", type=int, default=120)
    parser.add_argument("--min-future-price-points", type=int, default=3)
    parser.add_argument("--allow-nearest-fallback", action="store_true")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
