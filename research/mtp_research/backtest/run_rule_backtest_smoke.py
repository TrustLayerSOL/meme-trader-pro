"""Convenience smoke runner for rule backtests."""

from __future__ import annotations

from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestConfig
from research.mtp_research.backtest.rule_backtest_report import write_multi_result_markdown
from research.mtp_research.backtest.rule_backtest_store import RuleBacktestStore
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    store = ResearchDatasetStore()
    rows = store.load_all()
    horizon_name = "5m" if any(row.horizon_name == "5m" for row in rows) else None
    config = RuleBacktestConfig(
        config_id=f"rule_backtest_smoke_v0__horizon_{horizon_name or 'any'}",
        horizon_name=horizon_name,
        min_label_quality="sparse",
        min_rows=5,
    )
    backtester = RuleBacktester(config=config)
    results = [
        backtester.run_backtest(rows, rule, config=config)
        for rule in default_rule_library()
    ]
    result_store = RuleBacktestStore()
    result_store.upsert_many(results)
    output_path = write_multi_result_markdown(
        results,
        Path("data/backtests/reports") / f"rule_backtest_smoke_{config.config_id}.md",
    )
    print(f"rows_loaded={len(rows)}")
    print(f"rules_run={len(results)}")
    print(f"horizon_name={horizon_name}")
    print(f"result_store_path={result_store.path}")
    print(f"multi_report_path={output_path}")
    for result in results:
        print(f"{result.rule.rule_id}: selected={result.summary.selected_count} warnings={result.warning_flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
