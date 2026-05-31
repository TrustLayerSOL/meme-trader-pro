import pytest

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
    RuleCondition,
    RuleDefinition,
)
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(
    row_id: str = "row-1",
    *,
    snapshot_ts: int = 100,
    token_mint: str = "mint-1",
    window_name: str = "1m",
    horizon_name: str = "5m",
    label_quality: str = "sparse",
    entry_price: float | None = 1.0,
    end_price: float | None = 1.2,
    forward_return: float | None = 0.2,
    buy_sell_imbalance: float | None = 0.6,
    unique_actor_count: int = 4,
    confidence_weighted_net_flow: float = 1.0,
    possible_buy_count: int = 2,
    possible_sell_count: int = 1,
    quote_volume: float = 2.0,
    rug_like_drop: bool | None = False,
    no_future_liquidity: bool = False,
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
        end_price=end_price,
        forward_return=forward_return,
        max_runup=0.25,
        max_drawdown=-0.10,
        buy_sell_imbalance=buy_sell_imbalance,
        unique_actor_count=unique_actor_count,
        confidence_weighted_net_flow=confidence_weighted_net_flow,
        possible_buy_count=possible_buy_count,
        possible_sell_count=possible_sell_count,
        quote_volume=quote_volume,
        rug_like_drop=rug_like_drop,
        no_future_liquidity=no_future_liquidity,
        label_quality=label_quality,
    )


def test_evaluate_numeric_and_equality_operators() -> None:
    backtester = RuleBacktester()
    row = _row()
    assert backtester.evaluate_condition(row, RuleCondition("possible_buy_count", "gt", 1))
    assert backtester.evaluate_condition(row, RuleCondition("possible_buy_count", "gte", 2))
    assert backtester.evaluate_condition(row, RuleCondition("possible_sell_count", "lt", 2))
    assert backtester.evaluate_condition(row, RuleCondition("possible_sell_count", "lte", 1))
    assert backtester.evaluate_condition(row, RuleCondition("window_name", "eq", "1m"))
    assert backtester.evaluate_condition(row, RuleCondition("window_name", "neq", "5m"))


def test_evaluate_in_and_not_in_operators() -> None:
    backtester = RuleBacktester()
    row = _row()
    assert backtester.evaluate_condition(row, RuleCondition("horizon_name", "in", ["1m", "5m"]))
    assert backtester.evaluate_condition(row, RuleCondition("horizon_name", "not_in", ["15m"]))


def test_evaluate_boolean_and_not_none_operators() -> None:
    backtester = RuleBacktester()
    row = _row(rug_like_drop=True)
    assert backtester.evaluate_condition(row, RuleCondition("rug_like_drop", "is_true"))
    assert backtester.evaluate_condition(_row(rug_like_drop=False), RuleCondition("rug_like_drop", "is_false"))
    assert backtester.evaluate_condition(row, RuleCondition("entry_price", "is_not_none"))


def test_missing_fields_fail_safely_for_comparisons() -> None:
    backtester = RuleBacktester()
    row = _row()
    assert not backtester.evaluate_condition(row, RuleCondition("missing_field", "gt", 1))
    assert not backtester.evaluate_condition(row, RuleCondition("missing_field", "eq", 1))
    assert not backtester.evaluate_condition(row, RuleCondition("missing_field", "is_not_none"))


def test_row_passes_rule_with_multiple_conditions() -> None:
    rule = RuleDefinition(
        rule_id="test",
        name="test",
        conditions=[
            RuleCondition("buy_sell_imbalance", "gte", 0.5),
            RuleCondition("possible_buy_count", "gte", 2),
        ],
    )
    assert RuleBacktester().row_passes_rule(_row(), rule)
    assert not RuleBacktester().row_passes_rule(_row(possible_buy_count=1), rule)


def test_prefilter_filters_by_config_fields_and_requirements() -> None:
    rows = [
        _row("row-1"),
        _row("row-2", horizon_name="15m"),
        _row("row-3", window_name="5m"),
        _row("row-4", label_quality="no_price"),
        _row("row-5", entry_price=None),
        _row("row-6", forward_return=None),
    ]
    config = RuleBacktestConfig(
        config_id="cfg",
        horizon_name="5m",
        window_name="1m",
        min_label_quality="sparse",
        require_entry_price=True,
        require_forward_return=True,
    )
    filtered = RuleBacktester().prefilter_rows(rows, config)
    assert [row.row_id for row in filtered] == ["row-1"]


def test_selected_trade_from_row_subtracts_cost_drag() -> None:
    config = RuleBacktestConfig(
        config_id="cfg",
        cost_assumptions=CostAssumptions(
            entry_fee_bps=100,
            exit_fee_bps=100,
            slippage_bps=100,
        ),
    )
    trade = RuleBacktester().selected_trade_from_row(_row(forward_return=0.20), config)
    assert trade.gross_forward_return == 0.20
    assert trade.net_forward_return == pytest.approx(0.17)


def test_summarize_trades_calculates_core_metrics() -> None:
    config = RuleBacktestConfig(config_id="cfg", cost_assumptions=CostAssumptions(0, 0, 0, 0, 0))
    backtester = RuleBacktester(config=config)
    trades = [
        backtester.selected_trade_from_row(_row("row-1", snapshot_ts=1, forward_return=0.10), config),
        backtester.selected_trade_from_row(_row("row-2", snapshot_ts=2, forward_return=-0.05, rug_like_drop=True), config),
        backtester.selected_trade_from_row(_row("row-3", snapshot_ts=3, forward_return=0.20, no_future_liquidity=True), config),
    ]
    summary = backtester.summarize_trades(trades)
    assert summary.avg_gross_return == pytest.approx((0.10 - 0.05 + 0.20) / 3)
    assert summary.median_gross_return == 0.10
    assert summary.avg_net_return == pytest.approx((0.10 - 0.05 + 0.20) / 3)
    assert summary.median_net_return == 0.10
    assert summary.win_rate == 2 / 3
    assert summary.profit_factor == pytest.approx(0.30 / 0.05)
    assert summary.cumulative_net_return == pytest.approx((1.1 * 0.95 * 1.2) - 1)
    assert summary.max_equity_drawdown == pytest.approx((1.1 - 1.045) / 1.1)
    assert summary.rug_like_drop_rate == 1 / 3
    assert summary.no_future_liquidity_rate == 1 / 3


def test_run_backtest_adds_required_warnings_and_small_sample() -> None:
    rule = RuleDefinition("flow", "Flow", conditions=[RuleCondition("possible_buy_count", "gte", 1)])
    result = RuleBacktester(RuleBacktestConfig(config_id="cfg", min_rows=5)).run_backtest([_row()], rule)
    assert result.summary.selected_count == 1
    assert "exploratory_backtest_not_live_signal" in result.warning_flags
    assert "no_walk_forward_validation_yet" in result.warning_flags
    assert "heuristic_trade_labels_v0" in result.warning_flags
    assert "small_sample" in result.warning_flags
    assert result.metadata_json["cost_model_v0_simple_bps"] is True


def test_run_backtest_adds_no_selected_rows_warning() -> None:
    rule = RuleDefinition("flow", "Flow", conditions=[RuleCondition("possible_buy_count", "gte", 99)])
    result = RuleBacktester(RuleBacktestConfig(config_id="cfg", min_rows=1)).run_backtest([_row()], rule)
    assert result.summary.selected_count == 0
    assert "no_selected_rows" in result.warning_flags
