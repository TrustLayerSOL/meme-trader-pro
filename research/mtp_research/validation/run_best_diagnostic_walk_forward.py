"""Run walk-forward with the best evidence-bearing diagnostic fold config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
)
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.fold_sufficiency_analyzer import (
    FoldSufficiencyAnalyzer,
    _total_valid_rule_folds,
)
from research.mtp_research.validation.fold_sufficiency_models import FOLD_SUFFICIENCY_WARNING
from research.mtp_research.validation.fold_sufficiency_report import (
    write_report_json as write_sufficiency_json,
    write_report_markdown as write_sufficiency_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_models import WalkForwardConfig
from research.mtp_research.validation.walk_forward_report import (
    write_result_json,
    write_result_markdown,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore
from research.mtp_research.validation.walk_forward_validator import WalkForwardValidator


def main() -> int:
    args = parse_args()
    result = run_best_diagnostic_walk_forward(args)
    print(f"row_count={result['row_count']}")
    print(f"token_count={result['token_count']}")
    print(f"best_config_name={result['best_config_name']}")
    print(f"recommended_next_action={result['recommended_next_action']}")
    print(f"walk_forward_ran={result['walk_forward_ran']}")
    if result["walk_forward_ran"]:
        validation = result["validation_result"]
        print(f"valid_fold_counts={result['valid_fold_counts']}")
        print(f"walk_forward_store_path={result['store_path']}")
        print(f"walk_forward_markdown_path={result['walk_forward_markdown_path']}")
        print(f"walk_forward_json_path={result['walk_forward_json_path']}")
    print(f"fold_sufficiency_markdown_path={result['sufficiency_markdown_path']}")
    print(f"fold_sufficiency_json_path={result['sufficiency_json_path']}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run best diagnostic walk-forward if evidence-bearing.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--store-path", default="data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--max-walk-forward-folds", type=int, default=2000)
    return parser.parse_args()


def run_best_diagnostic_walk_forward(args: argparse.Namespace) -> dict:
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]

    rules = default_rule_library()
    analyzer = FoldSufficiencyAnalyzer()
    report = analyzer.analyze(
        rows,
        rules,
        dataset_path=args.dataset_path,
        min_label_quality=args.min_label_quality,
        require_forward_return=True,
    )
    output_dir = Path(args.output_dir)
    sufficiency_markdown_path = write_sufficiency_markdown(report, output_dir / f"{report.report_id}.md")
    sufficiency_json_path = write_sufficiency_json(report, output_dir / f"{report.report_id}.json")

    best = next((item for item in report.config_results if item.config_name == report.best_config_name), None)
    if best is None or _total_valid_rule_folds(best) == 0:
        return {
            "row_count": report.row_count,
            "token_count": report.token_count,
            "best_config_name": report.best_config_name,
            "recommended_next_action": report.recommended_next_action,
            "walk_forward_ran": False,
            "sufficiency_markdown_path": sufficiency_markdown_path,
            "sufficiency_json_path": sufficiency_json_path,
        }

    walk_config = WalkForwardConfig(
        config_id=f"best_diagnostic__{best.config_name}",
        train_window_seconds=best.train_window_seconds,
        test_window_seconds=best.test_window_seconds,
        step_seconds=best.step_seconds,
        gap_seconds=best.gap_seconds,
        min_train_rows=best.min_train_rows,
        min_test_rows=best.min_test_rows,
        min_label_quality=args.min_label_quality,
        max_folds=args.max_walk_forward_folds,
        metadata_json={
            "diagnostic_only": True,
            "fold_sufficiency_report_id": report.report_id,
            "max_walk_forward_folds": args.max_walk_forward_folds,
        },
    )
    rule_config = RuleBacktestConfig(
        config_id=f"{walk_config.config_id}__rule_backtest",
        min_label_quality=args.min_label_quality,
        min_rows=best.min_test_rows,
        cost_assumptions=CostAssumptions(),
        metadata_json={"diagnostic_only": True},
    )
    validation = WalkForwardValidator(walk_config, rule_config).validate(
        rows,
        rules,
        dataset_path=args.dataset_path,
    )
    validation.warning_flags = sorted(set(validation.warning_flags + [FOLD_SUFFICIENCY_WARNING]))
    store = WalkForwardValidationStore(args.store_path)
    store.upsert(validation)
    markdown_path = write_result_markdown(validation, output_dir / f"{validation.validation_id}.md")
    json_path = write_result_json(validation, output_dir / f"{validation.validation_id}.json")
    _mark_diagnostic(markdown_path)
    _mark_diagnostic(json_path)
    return {
        "row_count": report.row_count,
        "token_count": report.token_count,
        "best_config_name": report.best_config_name,
        "recommended_next_action": report.recommended_next_action,
        "walk_forward_ran": True,
        "validation_result": validation,
        "valid_fold_counts": {
            summary.rule_id: summary.valid_test_fold_count
            for summary in validation.rule_summaries
        },
        "store_path": store.path,
        "walk_forward_markdown_path": markdown_path,
        "walk_forward_json_path": json_path,
        "sufficiency_markdown_path": sufficiency_markdown_path,
        "sufficiency_json_path": sufficiency_json_path,
    }


def _mark_diagnostic(path: Path) -> None:
    if path.suffix == ".md":
        text = path.read_text(encoding="utf-8")
        if FOLD_SUFFICIENCY_WARNING not in text[:500]:
            path.write_text(f"> Warning: {FOLD_SUFFICIENCY_WARNING}\n\n{text}", encoding="utf-8")
    elif path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload["diagnostic_warning"] = FOLD_SUFFICIENCY_WARNING
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
