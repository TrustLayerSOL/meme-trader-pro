"""CLI for chronological walk-forward validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
)
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_models import (
    WalkForwardConfig,
    make_walk_forward_config_id,
)
from research.mtp_research.validation.walk_forward_report import (
    write_result_json,
    write_result_markdown,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore
from research.mtp_research.validation.walk_forward_validator import WalkForwardValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run walk-forward validation v0.")
    parser.add_argument("--dataset-path")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    parser.add_argument("--store-path", default="data/backtests/walk_forward_results.jsonl")
    parser.add_argument("--rule-id")
    parser.add_argument("--all-default-rules", action="store_true")
    parser.add_argument("--horizon-name")
    parser.add_argument("--window-name")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--train-window-seconds", type=int, default=86400)
    parser.add_argument("--test-window-seconds", type=int, default=21600)
    parser.add_argument("--step-seconds", type=int, default=21600)
    parser.add_argument("--gap-seconds", type=int, default=0)
    parser.add_argument("--min-train-rows", type=int, default=25)
    parser.add_argument("--min-test-rows", type=int, default=10)
    parser.add_argument("--entry-fee-bps", type=float, default=125.0)
    parser.add_argument("--exit-fee-bps", type=float, default=125.0)
    parser.add_argument("--slippage-bps", type=float, default=200.0)
    parser.add_argument("--priority-fee-bps", type=float, default=0.0)
    parser.add_argument("--failure-penalty-bps", type=float, default=0.0)
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args()

    dataset_store = ResearchDatasetStore(path=args.dataset_path) if args.dataset_path else ResearchDatasetStore()
    rows = dataset_store.load_all()
    if args.max_rows is not None:
        rows = rows[: args.max_rows]

    config_id = make_walk_forward_config_id(
        args.train_window_seconds,
        args.test_window_seconds,
        args.step_seconds,
        args.gap_seconds,
    )
    walk_config = WalkForwardConfig(
        config_id=config_id,
        train_window_seconds=args.train_window_seconds,
        test_window_seconds=args.test_window_seconds,
        step_seconds=args.step_seconds,
        gap_seconds=args.gap_seconds,
        min_train_rows=args.min_train_rows,
        min_test_rows=args.min_test_rows,
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
    )
    rule_config = RuleBacktestConfig(
        config_id=f"{config_id}__rule_backtest",
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        min_rows=args.min_test_rows,
        cost_assumptions=CostAssumptions(
            entry_fee_bps=args.entry_fee_bps,
            exit_fee_bps=args.exit_fee_bps,
            slippage_bps=args.slippage_bps,
            priority_fee_bps=args.priority_fee_bps,
            failure_penalty_bps=args.failure_penalty_bps,
        ),
    )
    rules = _select_rules(args.rule_id, args.all_default_rules)
    validator = WalkForwardValidator(walk_config, rule_backtest_config=rule_config)
    result = validator.validate(rows, rules, dataset_path=str(dataset_store.path))

    store = WalkForwardValidationStore(path=args.store_path)
    store.upsert(result)
    output_dir = Path(args.output_dir)
    markdown_path = write_result_markdown(result, output_dir / f"{result.validation_id}.md")
    json_path = write_result_json(result, output_dir / f"{result.validation_id}.json")

    print(f"rows_loaded={len(rows)}")
    print(f"rows_analyzed={result.filtered_row_count}")
    print(f"folds_generated={result.fold_count}")
    print(f"rules_tested={result.rules_tested}")
    print(f"output_markdown_path={markdown_path}")
    print(f"output_json_path={json_path}")
    print(f"store_path={store.path}")
    print(f"warning_flags={result.warning_flags}")
    return 0


def _select_rules(rule_id: str | None, all_default_rules: bool) -> list:
    rules = default_rule_library()
    if all_default_rules or not rule_id:
        return rules
    selected = [rule for rule in rules if rule.rule_id == rule_id]
    if not selected:
        raise SystemExit(f"Unknown rule_id: {rule_id}")
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
