"""CLI for writing exploratory baseline edge reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.baseline_edge_analyzer import BaselineEdgeAnalyzer
from research.mtp_research.validation.baseline_report_writer import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Build baseline edge report v0.")
    parser.add_argument("--dataset-path")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    parser.add_argument("--token-mint")
    parser.add_argument("--window-name")
    parser.add_argument("--horizon-name")
    parser.add_argument("--feature", action="append")
    parser.add_argument("--bucket-count", type=int, default=5)
    parser.add_argument("--min-bucket-size", type=int, default=10)
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--allow-missing-forward-return", action="store_true")
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args()

    rows = ResearchDatasetStore(path=args.dataset_path).load_all() if args.dataset_path else ResearchDatasetStore().load_all()
    analyzer = BaselineEdgeAnalyzer(
        min_bucket_size=args.min_bucket_size,
        bucket_count=args.bucket_count,
        min_label_quality=args.min_label_quality,
        require_forward_return=not args.allow_missing_forward_return,
    )
    rows_for_analysis = analyzer.filter_dataset_rows(
        rows,
        token_mints=[args.token_mint] if args.token_mint else None,
        window_names=[args.window_name] if args.window_name else None,
        horizon_names=[args.horizon_name] if args.horizon_name else None,
        min_label_quality=args.min_label_quality,
        require_forward_return=not args.allow_missing_forward_return,
    )
    if args.max_rows is not None:
        rows_for_analysis = rows_for_analysis[: args.max_rows]

    report = analyzer.analyze(
        rows_for_analysis,
        feature_names=args.feature,
    )
    report.dataset_path = str(args.dataset_path or ResearchDatasetStore().path)
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"rows_loaded={len(rows)}")
    print(f"rows_analyzed={report.filtered_row_count}")
    print(f"features_analyzed={len(report.feature_reports)}")
    print(f"output_markdown_path={markdown_path}")
    print(f"output_json_path={json_path}")
    print(f"warning_flags={report.warning_flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
