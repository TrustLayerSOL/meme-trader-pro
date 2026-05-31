"""CLI for outlier-adjusted diagnostic rule metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.outlier_adjusted_rule_metrics import (
    build_outlier_adjusted_report,
    find_latest_outlier_report,
    write_outlier_adjusted_json,
    write_outlier_adjusted_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    output_dir = Path(args.output_dir)
    outlier_report_path = Path(args.outlier_report_path) if args.outlier_report_path else find_latest_outlier_report(output_dir)
    report = build_outlier_adjusted_report(
        rows,
        default_rule_library(),
        args.rule_id or [rule.rule_id for rule in default_rule_library()],
        outlier_report_path=outlier_report_path,
        return_cap=args.return_cap,
        dataset_path=args.dataset_path,
    )
    markdown_path = write_outlier_adjusted_markdown(report, output_dir / f"{report['report_id']}.md")
    json_path = write_outlier_adjusted_json(report, output_dir / f"{report['report_id']}.json")
    for summary in report["rule_summaries"]:
        print(f"{summary['rule_id']}.selected_count={summary['selected_count']}")
        print(f"{summary['rule_id']}.excluded_outlier_count={summary['excluded_outlier_count']}")
        print(f"{summary['rule_id']}.raw_mean={summary['raw_metrics']['mean']}")
        print(f"{summary['rule_id']}.raw_median={summary['raw_metrics']['median']}")
        print(f"{summary['rule_id']}.capped_mean={summary['capped_metrics']['mean']}")
        print(f"{summary['rule_id']}.included_mean={summary['included_metrics']['mean']}")
        print(f"{summary['rule_id']}.warning_flags={summary['warning_flags']}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build outlier-adjusted rule metrics.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--outlier-report-path")
    parser.add_argument("--rule-id", action="append")
    parser.add_argument("--return-cap", type=float, default=1.0)
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
