import copy

import pytest

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
    RuleCondition,
    RuleDefinition,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import (
    FoldRuleResult,
    WalkForwardConfig,
    WalkForwardFold,
)
from research.mtp_research.validation.walk_forward_validator import WalkForwardValidator


def _row(
    row_id: str,
    snapshot_ts: int,
    forward_return: float | None = 0.1,
    *,
    token_mint: str = "mint-1",
    window_name: str = "1m",
    horizon_name: str = "5m",
    label_quality: str = "sparse",
    entry_price: float | None = 1.0,
    possible_buy_count: int = 1,
    confidence_weighted_net_flow: float = 1.0,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=snapshot_ts,
        window_name=window_name,
        window_seconds=60,
        horizon_name=horizon_name,
        horizon_seconds=300,
        entry_price=entry_price,
        forward_return=forward_return,
        max_runup=0.2,
        max_drawdown=-0.1,
        possible_buy_count=possible_buy_count,
        confidence_weighted_net_flow=confidence_weighted_net_flow,
        label_quality=label_quality,
    )


def _config() -> WalkForwardConfig:
    return WalkForwardConfig(
        config_id="wf-cfg",
        train_window_seconds=10,
        test_window_seconds=5,
        step_seconds=5,
        min_train_rows=3,
        min_test_rows=2,
        horizon_name="5m",
        window_name="1m",
    )


def _rule() -> RuleDefinition:
    return RuleDefinition(
        rule_id="positive_flow_basic",
        name="Positive Flow Basic",
        conditions=[
            RuleCondition("confidence_weighted_net_flow", "gt", 0),
            RuleCondition("possible_buy_count", "gte", 1),
        ],
    )


def test_prefilter_filters_by_horizon_window_quality_and_requirements() -> None:
    rows = [
        _row("row-1", 1),
        _row("row-2", 2, horizon_name="15m"),
        _row("row-3", 3, window_name="5m"),
        _row("row-4", 4, label_quality="no_price"),
        _row("row-5", 5, entry_price=None),
        _row("row-6", 6, forward_return=None),
    ]
    assert [row.row_id for row in WalkForwardValidator(_config()).prefilter_rows(rows)] == ["row-1"]


def test_validate_rule_on_fold_runs_train_and_test_backtests() -> None:
    fold = WalkForwardFold("fold-1", 0, 0, 9, 10, 14)
    validator = WalkForwardValidator(_config(), RuleBacktestConfig("rule-cfg", cost_assumptions=CostAssumptions(0, 0, 0, 0, 0)))
    result = validator.validate_rule_on_fold(_rule(), [_row("row-1", 1), _row("row-2", 2)], [_row("row-3", 11)], fold)
    assert result.train_result_id
    assert result.test_result_id
    assert result.train_selected_count == 2
    assert result.test_selected_count == 1
    assert result.test_avg_net_return == 0.1


def test_validate_rule_on_fold_warnings() -> None:
    fold = WalkForwardFold("fold-1", 0, 0, 9, 10, 14)
    validator = WalkForwardValidator(_config())
    result = validator.validate_rule_on_fold(
        _rule(),
        [_row("row-1", 1, forward_return=0.2)],
        [_row("row-2", 11, forward_return=-0.1, possible_buy_count=0)],
        fold,
    )
    assert "small_train_fold" in result.warning_flags
    assert "small_test_fold" in result.warning_flags
    assert "no_test_trades" in result.warning_flags
    assert "train_only_pattern" in result.warning_flags


def test_summarize_rule_results_calculates_consistency_metrics() -> None:
    validator = WalkForwardValidator(_config())
    fold_results = [
        FoldRuleResult("fold-1", 0, "rule", "Rule", test_selected_count=2, test_avg_net_return=0.1, test_win_rate=1.0, test_cumulative_net_return=0.2),
        FoldRuleResult("fold-2", 1, "rule", "Rule", test_selected_count=2, test_avg_net_return=-0.05, test_win_rate=0.0, test_cumulative_net_return=-0.1),
        FoldRuleResult("fold-3", 2, "rule", "Rule", test_selected_count=0, test_avg_net_return=None),
    ]
    summary = validator.summarize_rule_results(RuleDefinition("rule", "Rule"), fold_results)
    assert summary.valid_test_fold_count == 2
    assert summary.positive_test_fold_rate == 0.5
    assert summary.avg_test_net_return == pytest.approx(0.025)
    assert summary.median_test_net_return == pytest.approx(0.025)
    assert summary.total_test_selected_count == 4
    assert summary.consistency_score == pytest.approx(0.0125)


def test_summarize_rule_results_adds_no_valid_warning() -> None:
    summary = WalkForwardValidator(_config()).summarize_rule_results(
        RuleDefinition("rule", "Rule"),
        [FoldRuleResult("fold-1", 0, "rule", "Rule", test_selected_count=0)],
    )
    assert "no_valid_test_folds" in summary.warning_flags
    assert "small_total_test_sample" in summary.warning_flags


def test_validate_returns_result_warnings_and_does_not_mutate_rules_or_optimize() -> None:
    rows = [_row(f"row-{ts}", ts, forward_return=0.1 if ts < 15 else -0.1) for ts in range(0, 26)]
    rule = _rule()
    original = copy.deepcopy(rule.to_dict())
    result = WalkForwardValidator(_config()).validate(rows, [rule], dataset_path="dataset.jsonl")
    assert result.fold_count > 0
    assert result.rules_tested == 1
    assert "exploratory_walk_forward_not_live_signal" in result.warning_flags
    assert "no_live_trading_enabled" in result.warning_flags
    assert "heuristic_trade_labels_v0" in result.warning_flags
    assert "cost_model_v0_simple_bps" in result.warning_flags
    assert rule.to_dict() == original
    assert result.metadata_json["rules_not_optimized"] is True
