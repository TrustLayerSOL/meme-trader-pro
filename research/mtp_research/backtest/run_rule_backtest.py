"""CLI for deterministic rule-based backtests."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
)
from research.mtp_research.backtest.rule_backtest_report import (
    write_multi_result_markdown,
    write_result_json,
    write_result_markdown,
)
from research.mtp_research.backtest.rule_backtest_store import RuleBacktestStore
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rule-based backtest v0.")
    parser.add_argument("--dataset-path")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    parser.add_argument("--store-path", default="data/backtests/rule_backtest_results.jsonl")
    parser.add_argument("--rule-id")
    parser.add_argument("--all-default-rules", action="store_true")
    parser.add_argument("--horizon-name")
    parser.add_argument("--window-name")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--min-rows", type=int, default=10)
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

    rules = _select_rules(args.rule_id, args.all_default_rules)
    config = RuleBacktestConfig(
        config_id=_config_id(args),
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        min_rows=args.min_rows,
        cost_assumptions=CostAssumptions(
            entry_fee_bps=args.entry_fee_bps,
            exit_fee_bps=args.exit_fee_bps,
            slippage_bps=args.slippage_bps,
            priority_fee_bps=args.priority_fee_bps,
            failure_penalty_bps=args.failure_penalty_bps,
        ),
    )
    backtester = RuleBacktester(config=config)
    results = [backtester.run_backtest(rows, rule, config=config) for rule in rules]

    store = RuleBacktestStore(path=args.store_path)
    store.upsert_many(results)
    output_dir = Path(args.output_dir)
    multi_report_path = write_multi_result_markdown(
        results,
        output_dir / f"rule_backtest_comparison_{config.config_id}.md",
    )
    output_paths = [multi_report_path]
    for result in results:
        output_paths.append(write_result_json(result, output_dir / f"{result.result_id}.json"))
        output_paths.append(write_result_markdown(result, output_dir / f"{result.result_id}.md"))

    print(f"rows_loaded={len(rows)}")
    print(f"rules_run={len(results)}")
    print(f"result_store_path={store.path}")
    print(f"multi_report_path={multi_report_path}")
    print("report_output_paths=" + ",".join(str(path) for path in output_paths))
    for result in results:
        print(f"warning_flags[{result.rule.rule_id}]={result.warning_flags}")
    return 0


def _select_rules(rule_id: str | None, all_default_rules: bool) -> list:
    rules = default_rule_library()
    if all_default_rules or not rule_id:
        return rules
    selected = [rule for rule in rules if rule.rule_id == rule_id]
    if not selected:
        raise SystemExit(f"Unknown rule_id: {rule_id}")
    return selected


def _config_id(args: argparse.Namespace) -> str:
    parts = [
        "rule_backtest_v0",
        f"window_{args.window_name or 'any'}",
        f"horizon_{args.horizon_name or 'any'}",
        f"quality_{args.min_label_quality}",
        f"cost_{int(args.entry_fee_bps)}_{int(args.exit_fee_bps)}_{int(args.slippage_bps)}_{int(args.priority_fee_bps)}_{int(args.failure_penalty_bps)}",
    ]
    return "__".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
