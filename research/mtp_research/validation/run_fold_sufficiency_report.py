"""CLI for walk-forward fold sufficiency diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.fold_sufficiency_analyzer import (
    FoldSufficiencyAnalyzer,
    _total_test_selected_count,
    _total_valid_rule_folds,
)
from research.mtp_research.validation.fold_sufficiency_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    report, markdown_path, json_path = build_and_write_report(args)
    print(f"row_count={report.row_count}")
    print(f"token_count={report.token_count}")
    print(f"time_span_seconds={report.time_span_seconds}")
    print(f"best_config_name={report.best_config_name}")
    print(f"recommended_next_action={report.recommended_next_action}")
    for result in report.config_results:
        print(
            "config_summary"
            f"[{result.config_name}]="
            f"folds:{result.fold_count},"
            f"valid_folds:{result.valid_fold_count},"
            f"valid_rule_folds:{_total_valid_rule_folds(result)},"
            f"test_selected:{_total_test_selected_count(result)},"
            f"warnings:{result.warning_flags}"
        )
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fold sufficiency diagnostic report.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--horizon-name")
    parser.add_argument("--window-name")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--allow-missing-forward-return", action="store_true")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--config-name", action="append")
    return parser.parse_args()


def build_and_write_report(args: argparse.Namespace):
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]

    analyzer = FoldSufficiencyAnalyzer()
    configs = analyzer.default_config_candidates()
    if args.config_name:
        wanted = set(args.config_name)
        configs = [config for config in configs if config.name in wanted]
        missing = wanted - {config.name for config in configs}
        if missing:
            raise SystemExit(f"Unknown config-name values: {sorted(missing)}")

    report = analyzer.analyze(
        rows,
        default_rule_library(),
        configs=configs,
        dataset_path=args.dataset_path,
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        require_forward_return=not args.allow_missing_forward_return,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")
    return report, markdown_path, json_path


if __name__ == "__main__":
    raise SystemExit(main())
