"""Deterministic rule-based backtester over local research dataset rows."""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
    RuleBacktestResult,
    RuleBacktestSummary,
    RuleCondition,
    RuleDefinition,
    SelectedTrade,
    make_backtest_result_id,
    utc_now_iso,
)
from research.mtp_research.validation.research_dataset_builder import _quality_rank
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


_MISSING = object()


class RuleBacktester:
    """Evaluate auditable feature rules against local ResearchDatasetRow objects."""

    def __init__(self, config: RuleBacktestConfig | None = None):
        self.config = config or RuleBacktestConfig(config_id="default_rule_backtest_v0")

    def evaluate_condition(self, row: ResearchDatasetRow, condition: RuleCondition) -> bool:
        value = getattr(row, condition.field_name, _MISSING)
        operator = condition.operator

        if operator == "neq":
            return value is _MISSING or value != condition.value
        if operator == "not_in":
            if value is _MISSING:
                return True
            try:
                return value not in condition.value
            except TypeError:
                return False
        if operator == "is_not_none":
            return value is not _MISSING and value is not None
        if value is _MISSING:
            return False
        if operator == "is_true":
            return value is True
        if operator == "is_false":
            return value is False
        if operator == "eq":
            return value == condition.value
        if operator == "in":
            try:
                return value in condition.value
            except TypeError:
                return False
        if operator in {"gt", "gte", "lt", "lte"}:
            return _compare_numeric(value, condition.value, operator)
        return False

    def row_passes_rule(self, row: ResearchDatasetRow, rule: RuleDefinition) -> bool:
        return all(self.evaluate_condition(row, condition) for condition in rule.conditions)

    def prefilter_rows(
        self,
        rows: list[ResearchDatasetRow],
        config: RuleBacktestConfig,
    ) -> list[ResearchDatasetRow]:
        output = []
        min_quality_rank = _quality_rank(config.min_label_quality)
        for row in rows:
            if config.horizon_name and row.horizon_name != config.horizon_name:
                continue
            if config.window_name and row.window_name != config.window_name:
                continue
            if _quality_rank(row.label_quality) < min_quality_rank:
                continue
            if config.require_entry_price and row.entry_price is None:
                continue
            if config.require_forward_return and row.forward_return is None:
                continue
            output.append(row)
        return output

    def selected_trade_from_row(
        self,
        row: ResearchDatasetRow,
        config: RuleBacktestConfig,
    ) -> SelectedTrade:
        cost_drag = config.cost_assumptions.total_cost_return_drag()
        net_forward_return = None
        if row.forward_return is not None:
            net_forward_return = row.forward_return - cost_drag
        return SelectedTrade(
            row_id=row.row_id,
            token_mint=row.token_mint,
            snapshot_ts=row.snapshot_ts,
            window_name=row.window_name,
            horizon_name=row.horizon_name,
            entry_price=row.entry_price,
            end_price=row.end_price,
            gross_forward_return=row.forward_return,
            net_forward_return=net_forward_return,
            max_runup=row.max_runup,
            max_drawdown=row.max_drawdown,
            rug_like_drop=row.rug_like_drop,
            no_future_liquidity=row.no_future_liquidity,
            label_quality=row.label_quality,
            metadata_json={
                "snapshot_id": row.snapshot_id,
                "outcome_id": row.outcome_id,
                "entry_price_source": row.entry_price_source,
                "cost_drag": cost_drag,
            },
        )

    def summarize_trades(self, trades: list[SelectedTrade]) -> RuleBacktestSummary:
        gross_returns = [
            trade.gross_forward_return
            for trade in trades
            if trade.gross_forward_return is not None
        ]
        net_returns = [
            trade.net_forward_return
            for trade in trades
            if trade.net_forward_return is not None
        ]
        runups = [trade.max_runup for trade in trades if trade.max_runup is not None]
        drawdowns = [trade.max_drawdown for trade in trades if trade.max_drawdown is not None]
        win_count = sum(1 for value in net_returns if value > 0)
        loss_count = sum(1 for value in net_returns if value <= 0)
        gross_profit = sum(value for value in net_returns if value > 0)
        gross_loss = abs(sum(value for value in net_returns if value < 0))
        equity_values = _compounded_equity_values(trades)
        cumulative_net_return = (equity_values[-1] - 1.0) if equity_values else None

        rug_count = sum(1 for trade in trades if trade.rug_like_drop is True)
        no_liquidity_count = sum(1 for trade in trades if trade.no_future_liquidity)
        selected_count = len(trades)
        rows_with_return = len(net_returns)
        return RuleBacktestSummary(
            selected_count=selected_count,
            token_count=len({trade.token_mint for trade in trades}),
            rows_with_return=rows_with_return,
            avg_gross_return=mean(gross_returns) if gross_returns else None,
            median_gross_return=median(gross_returns) if gross_returns else None,
            avg_net_return=mean(net_returns) if net_returns else None,
            median_net_return=median(net_returns) if net_returns else None,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=(win_count / rows_with_return) if rows_with_return else None,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
            cumulative_net_return=cumulative_net_return,
            max_equity_drawdown=_max_drawdown(equity_values),
            avg_max_runup=mean(runups) if runups else None,
            avg_max_drawdown=mean(drawdowns) if drawdowns else None,
            rug_like_drop_count=rug_count,
            rug_like_drop_rate=(rug_count / selected_count) if selected_count else None,
            no_future_liquidity_count=no_liquidity_count,
            no_future_liquidity_rate=(no_liquidity_count / selected_count) if selected_count else None,
        )

    def run_backtest(
        self,
        rows: list[ResearchDatasetRow],
        rule: RuleDefinition,
        config: RuleBacktestConfig | None = None,
    ) -> RuleBacktestResult:
        effective_config = config or self.config
        filtered_rows = self.prefilter_rows(rows, effective_config)
        selected_rows = [
            row for row in filtered_rows
            if self.row_passes_rule(row, rule)
        ]
        trades = [
            self.selected_trade_from_row(row, effective_config)
            for row in sorted(selected_rows, key=lambda item: (item.snapshot_ts, item.row_id))
        ]
        summary = self.summarize_trades(trades)
        warning_flags = [
            "exploratory_backtest_not_live_signal",
            "no_walk_forward_validation_yet",
            "heuristic_trade_labels_v0",
        ]
        if summary.selected_count < effective_config.min_rows:
            warning_flags.append("small_sample")
        if summary.selected_count == 0:
            warning_flags.append("no_selected_rows")
        return RuleBacktestResult(
            result_id=make_backtest_result_id(rule.rule_id, effective_config.config_id),
            created_at=utc_now_iso(),
            rule=rule,
            config=effective_config,
            summary=summary,
            selected_trades=trades,
            warning_flags=warning_flags,
            metadata_json={
                "backtester_version": "rule_backtester_v0",
                "cost_model_v0_simple_bps": True,
                "prefiltered_row_count": len(filtered_rows),
            },
        )


def _compare_numeric(left: Any, right: Any, operator: str) -> bool:
    if left is None or right is None:
        return False
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return False
    if operator == "gt":
        return left_value > right_value
    if operator == "gte":
        return left_value >= right_value
    if operator == "lt":
        return left_value < right_value
    if operator == "lte":
        return left_value <= right_value
    return False


def _compounded_equity_values(trades: list[SelectedTrade]) -> list[float]:
    equity = 1.0
    values = [equity]
    for trade in sorted(trades, key=lambda item: (item.snapshot_ts, item.row_id)):
        if trade.net_forward_return is None:
            continue
        equity *= 1 + trade.net_forward_return
        values.append(equity)
    return values if len(values) > 1 else []


def _max_drawdown(equity_values: list[float]) -> float | None:
    if not equity_values:
        return None
    peak = equity_values[0]
    max_drawdown = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    return max_drawdown
