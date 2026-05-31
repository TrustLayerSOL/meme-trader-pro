"""CLI for Stage 30 selected-row diagnostic audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.selected_row_audit_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.selected_row_auditor import SelectedRowAuditor


DEFAULT_RULE_IDS = ["buy_imbalance_basic", "unique_actor_flow_basic"]


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    rule_ids = args.rule_id or DEFAULT_RULE_IDS
    report = SelectedRowAuditor().audit_rules(
        rows,
        default_rule_library(),
        rule_ids,
        stale_entry_threshold_sec=args.stale_entry_threshold_sec,
        outlier_return_threshold=args.outlier_return_threshold,
        top_outlier_n=args.limit,
        dataset_path=args.dataset_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    for audit in report.rule_audits:
        print(f"{audit.rule_id}.selected_count={audit.selected_count}")
        print(f"{audit.rule_id}.win_rate={audit.win_rate}")
        print(f"{audit.rule_id}.median_forward_return={audit.median_forward_return}")
        print(f"{audit.rule_id}.outlier_return_share={audit.outlier_return_share}")
        print(f"{audit.rule_id}.fallback_entry_rate={audit.fallback_entry_rate}")
        print(f"{audit.rule_id}.stale_entry_rate={audit.stale_entry_rate}")
        print(f"{audit.rule_id}.token_concentration={audit.token_concentration}")
        print(f"{audit.rule_id}.warning_flags={audit.warning_flags}")
    print(f"recommended_next_action={report.recommended_next_action}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit selected rows for diagnostic rules.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--rule-id", action="append")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--stale-entry-threshold-sec", type=int, default=300)
    parser.add_argument("--outlier-return-threshold", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
