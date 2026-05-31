"""Smoke runner for exploratory baseline edge reports."""

from __future__ import annotations

from pathlib import Path

from research.mtp_research.validation.baseline_edge_analyzer import BaselineEdgeAnalyzer
from research.mtp_research.validation.baseline_report_writer import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    store = ResearchDatasetStore()
    rows = store.load_all()
    analyzer = BaselineEdgeAnalyzer(
        min_bucket_size=5,
        bucket_count=5,
        min_label_quality="sparse",
        require_forward_return=True,
    )
    report = analyzer.analyze(rows)
    report.dataset_path = str(store.path)

    output_dir = Path("data/backtests/reports")
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
