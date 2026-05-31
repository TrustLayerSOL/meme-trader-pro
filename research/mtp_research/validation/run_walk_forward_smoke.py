"""Convenience smoke runner for walk-forward validation."""

from __future__ import annotations

from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestConfig
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_models import (
    WalkForwardConfig,
    make_walk_forward_config_id,
)
from research.mtp_research.validation.walk_forward_report import write_result_markdown
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore
from research.mtp_research.validation.walk_forward_validator import WalkForwardValidator


def main() -> int:
    store = ResearchDatasetStore()
    rows = store.load_all()
    config_id = make_walk_forward_config_id(86400, 21600, 21600, 0)
    config = WalkForwardConfig(
        config_id=config_id,
        train_window_seconds=86400,
        test_window_seconds=21600,
        step_seconds=21600,
        min_train_rows=10,
        min_test_rows=5,
        min_label_quality="sparse",
    )
    rule_config = RuleBacktestConfig(config_id=f"{config_id}__smoke_rule_backtest", min_rows=5)
    result = WalkForwardValidator(config, rule_backtest_config=rule_config).validate(
        rows,
        default_rule_library(),
        dataset_path=str(store.path),
    )
    result_store = WalkForwardValidationStore()
    result_store.upsert(result)
    report_path = write_result_markdown(
        result,
        Path("data/backtests/reports") / f"{result.validation_id}.md",
    )
    print(f"rows_loaded={len(rows)}")
    print(f"rows_analyzed={result.filtered_row_count}")
    print(f"folds_generated={result.fold_count}")
    print(f"rules_tested={result.rules_tested}")
    print(f"report_path={report_path}")
    print(f"store_path={result_store.path}")
    print(f"warning_flags={result.warning_flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
