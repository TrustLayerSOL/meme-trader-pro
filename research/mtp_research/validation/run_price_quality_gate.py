"""CLI for building a diagnostic price-quality-gated dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.price_quality_gate import PriceQualityGate
from research.mtp_research.validation.price_quality_models import PriceQualityConfig
from research.mtp_research.validation.price_quality_report import (
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

    config = PriceQualityConfig(
        max_entry_staleness_sec=args.max_entry_staleness_sec,
        min_future_price_points=args.min_future_price_points,
        allow_nearest_fallback=args.allow_nearest_fallback,
        allow_no_future_liquidity=args.allow_no_future_liquidity,
        allow_rug_like_drop=not args.disallow_rug_like_drop,
        min_label_quality=args.min_label_quality,
        max_forward_return_abs=args.max_forward_return_abs,
        max_runup_abs=args.max_runup_abs,
    )
    passed_rows, _decisions, report = PriceQualityGate().filter_rows(
        rows,
        config,
        dataset_path=args.dataset_path,
    )
    if not args.dry_run:
        ResearchDatasetStore(args.output_dataset_path).replace_all(passed_rows)

    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"input_row_count={report.input_row_count}")
    print(f"passed_row_count={report.passed_row_count}")
    print(f"failed_row_count={report.failed_row_count}")
    print(f"pass_rate={report.pass_rate}")
    print(f"token_count_passed={report.token_count_passed}")
    print(f"failure_reason_counts={report.failure_reason_counts}")
    print(f"output_dataset_path={args.output_dataset_path}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build price-quality-gated diagnostic dataset.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dataset-path", default="data/backtests/diagnostics/research_dataset_price_quality_gated.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--max-entry-staleness-sec", type=int, default=120)
    parser.add_argument("--min-future-price-points", type=int, default=3)
    parser.add_argument("--allow-nearest-fallback", action="store_true")
    parser.add_argument("--allow-no-future-liquidity", action="store_true")
    parser.add_argument("--disallow-rug-like-drop", action="store_true")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--max-forward-return-abs", type=float)
    parser.add_argument("--max-runup-abs", type=float)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
