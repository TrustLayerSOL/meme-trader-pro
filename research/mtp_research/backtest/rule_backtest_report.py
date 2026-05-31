"""Report writers for rule-based backtest results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestResult


def result_to_dict(result: RuleBacktestResult) -> dict[str, Any]:
    return result.to_dict()


def write_result_json(result: RuleBacktestResult, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_dict(result), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_result_markdown(result: RuleBacktestResult, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result.summary
    cost = result.config.cost_assumptions
    lines = [
        f"# Rule Backtest: {result.rule.name}",
        "",
        f"- Created at: `{result.created_at}`",
        f"- Rule ID: `{result.rule.rule_id}`",
        f"- Result ID: `{result.result_id}`",
        f"- Description: {result.rule.description}",
        "",
        "## Conditions",
        "",
        *[
            f"- `{condition.field_name}` `{condition.operator}` `{condition.value}`"
            for condition in result.rule.conditions
        ],
        "",
        "## Config",
        "",
        f"- Config ID: `{result.config.config_id}`",
        f"- Window: `{result.config.window_name}`",
        f"- Horizon: `{result.config.horizon_name}`",
        f"- Minimum label quality: `{result.config.min_label_quality}`",
        f"- Require entry price: `{result.config.require_entry_price}`",
        f"- Require forward return: `{result.config.require_forward_return}`",
        f"- Minimum rows: `{result.config.min_rows}`",
        "",
        "## Cost Assumptions",
        "",
        f"- Entry fee bps: `{format_number(cost.entry_fee_bps)}`",
        f"- Exit fee bps: `{format_number(cost.exit_fee_bps)}`",
        f"- Slippage bps: `{format_number(cost.slippage_bps)}`",
        f"- Priority fee bps: `{format_number(cost.priority_fee_bps)}`",
        f"- Failure penalty bps: `{format_number(cost.failure_penalty_bps)}`",
        f"- Total cost bps: `{format_number(cost.total_cost_bps())}`",
        f"- Total return drag: `{format_percent(cost.total_cost_return_drag())}`",
        "",
        "## Warning Flags",
        "",
        *[f"- `{flag}`" for flag in result.warning_flags],
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Selected trades | {summary.selected_count} |",
        f"| Token count | {summary.token_count} |",
        f"| Rows with return | {summary.rows_with_return} |",
        f"| Avg gross return | {format_percent(summary.avg_gross_return)} |",
        f"| Median gross return | {format_percent(summary.median_gross_return)} |",
        f"| Avg net return | {format_percent(summary.avg_net_return)} |",
        f"| Median net return | {format_percent(summary.median_net_return)} |",
        f"| Win rate | {format_percent(summary.win_rate)} |",
        f"| Profit factor | {format_number(summary.profit_factor)} |",
        f"| Cumulative net return | {format_percent(summary.cumulative_net_return)} |",
        f"| Max equity drawdown | {format_percent(summary.max_equity_drawdown)} |",
        f"| Rug-like drop rate | {format_percent(summary.rug_like_drop_rate)} |",
        f"| No-future-liquidity rate | {format_percent(summary.no_future_liquidity_rate)} |",
        "",
        f"Selected trade count: `{len(result.selected_trades)}`",
        "",
        "## Selected Trades",
        "",
        "| Token | Snapshot TS | Window | Horizon | Gross Return | Net Return | Max Runup | Max Drawdown | Rug-like Drop | Label Quality |",
        "|---|---:|---|---|---:|---:|---:|---:|---|---|",
    ]
    for trade in sorted(result.selected_trades, key=lambda item: (item.snapshot_ts, item.row_id))[:20]:
        lines.append(
            f"| {trade.token_mint} | {trade.snapshot_ts} | {trade.window_name} | "
            f"{trade.horizon_name} | {format_percent(trade.gross_forward_return)} | "
            f"{format_percent(trade.net_forward_return)} | {format_percent(trade.max_runup)} | "
            f"{format_percent(trade.max_drawdown)} | {trade.rug_like_drop} | {trade.label_quality} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_multi_result_markdown(results: list[RuleBacktestResult], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Rule Backtest Comparison",
        "",
        "These results are exploratory and are not live trading signals.",
        "",
        "| Rule | Selected | Tokens | Avg Net | Median Net | Win Rate | Profit Factor | Cumulative Net | Max Drawdown | Rug Drop Rate | Warnings |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summarize_results_table(results):
        lines.append(
            f"| `{row['rule_id']}` {row['rule_name']} | {row['selected_count']} | "
            f"{row['token_count']} | {format_percent(row['avg_net_return'])} | "
            f"{format_percent(row['median_net_return'])} | {format_percent(row['win_rate'])} | "
            f"{format_number(row['profit_factor'])} | {format_percent(row['cumulative_net_return'])} | "
            f"{format_percent(row['max_equity_drawdown'])} | {format_percent(row['rug_like_drop_rate'])} | "
            f"{', '.join(row['warning_flags'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def summarize_results_table(results: list[RuleBacktestResult]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        summary = result.summary
        rows.append(
            {
                "rule_id": result.rule.rule_id,
                "rule_name": result.rule.name,
                "selected_count": summary.selected_count,
                "token_count": summary.token_count,
                "avg_net_return": summary.avg_net_return,
                "median_net_return": summary.median_net_return,
                "win_rate": summary.win_rate,
                "profit_factor": summary.profit_factor,
                "cumulative_net_return": summary.cumulative_net_return,
                "max_equity_drawdown": summary.max_equity_drawdown,
                "rug_like_drop_rate": summary.rug_like_drop_rate,
                "warning_flags": list(result.warning_flags),
            }
        )
    return rows


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"
