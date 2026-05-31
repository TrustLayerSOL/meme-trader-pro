"""CLI for Stage 33 evidence expansion decisions."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.evidence_expansion_decision import (
    EvidenceExpansionDecisionAnalyzer,
    latest_report,
    load_json_report,
)
from research.mtp_research.validation.evidence_expansion_decision_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.diagnostic_dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    output_dir = Path(args.output_dir)
    report_dirs = [output_dir, "data/backtests/reports"]
    robust_path = _path_arg(args.robust_rule_report_json) or latest_report(report_dirs, ["rule_robust_return_*.json"])
    outlier_path = _path_arg(args.outlier_price_path_json) or latest_report(report_dirs, ["outlier_price_path_*.json"])
    selected_path = _path_arg(args.selected_row_audit_json) or latest_report(report_dirs, ["selected_row_audit_*.json"])
    fold_path = _path_arg(args.fold_sufficiency_json) or latest_report(report_dirs, ["fold_sufficiency_*.json"])
    wf_path = _path_arg(args.diagnostic_walk_forward_review_json) or latest_report(report_dirs, ["diagnostic_walk_forward_review_*.json"])
    price_path = _path_arg(args.price_coverage_json) or latest_report(report_dirs, ["price_coverage_*.json"])
    sufficiency_path = _path_arg(args.dataset_sufficiency_json) or latest_report(report_dirs, ["dataset_sufficiency_*.json"])
    analyzer = EvidenceExpansionDecisionAnalyzer()
    report = analyzer.build_report(
        rows,
        diagnostic_dataset_path=args.diagnostic_dataset_path,
        raw_row_count=_line_count("data/raw/helius_transactions.jsonl"),
        robust_rule_report_data=load_json_report(robust_path),
        outlier_price_path_data=load_json_report(outlier_path),
        selected_row_audit_data=load_json_report(selected_path),
        fold_sufficiency_data=load_json_report(fold_path),
        diagnostic_walk_forward_review_data=load_json_report(wf_path),
        price_coverage_data=load_json_report(price_path),
        dataset_sufficiency_data=load_json_report(sufficiency_path),
    )
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")
    classifications = {signal.rule_id: signal.signal_classification for signal in report.rule_signals}
    need_types = [need.need_type for need in report.expansion_needs]
    command = report.bounded_plan.recommended_command if report.bounded_plan else None

    print(f"real_token_count={report.real_token_count}")
    print(f"time_span_seconds={report.time_span_seconds}")
    print(f"price_coverage_rate={report.price_coverage_rate}")
    print(f"rule_signal_classifications={classifications}")
    print(f"expansion_needs={need_types}")
    print(f"recommended_next_action={report.recommended_next_action}")
    print(f"recommended_command={command}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build evidence expansion decision report.")
    parser.add_argument("--diagnostic-dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--robust-rule-report-json")
    parser.add_argument("--outlier-price-path-json")
    parser.add_argument("--selected-row-audit-json")
    parser.add_argument("--fold-sufficiency-json")
    parser.add_argument("--diagnostic-walk-forward-review-json")
    parser.add_argument("--price-coverage-json")
    parser.add_argument("--dataset-sufficiency-json")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    return parser.parse_args()


def _path_arg(value: str | None) -> Path | None:
    return Path(value) if value else None


def _line_count(path: str) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


if __name__ == "__main__":
    raise SystemExit(main())
