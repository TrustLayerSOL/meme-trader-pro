import json
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import (
    RuleBacktestConfig,
    RuleBacktestResult,
    RuleBacktestSummary,
    RuleCondition,
    RuleDefinition,
    SelectedTrade,
)
from research.mtp_research.backtest.rule_backtest_report import (
    format_number,
    format_percent,
    result_to_dict,
    write_multi_result_markdown,
    write_result_json,
    write_result_markdown,
)


def _result() -> RuleBacktestResult:
    return RuleBacktestResult(
        result_id="result-1",
        created_at="2026-05-30T00:00:00+00:00",
        rule=RuleDefinition(
            rule_id="rule-1",
            name="Rule 1",
            description="Exploratory only; not a live trading rule.",
            conditions=[RuleCondition("possible_buy_count", "gte", 1)],
        ),
        config=RuleBacktestConfig(config_id="cfg-1", horizon_name="5m", window_name="1m"),
        summary=RuleBacktestSummary(
            selected_count=1,
            token_count=1,
            rows_with_return=1,
            avg_net_return=0.1,
            median_net_return=0.1,
            win_rate=1.0,
            profit_factor=None,
            cumulative_net_return=0.1,
            max_equity_drawdown=0.0,
            rug_like_drop_rate=0.0,
        ),
        selected_trades=[
            SelectedTrade(
                row_id="row-1",
                token_mint="mint-1",
                snapshot_ts=100,
                window_name="1m",
                horizon_name="5m",
                entry_price=1.0,
                end_price=1.1,
                gross_forward_return=0.15,
                net_forward_return=0.1,
                max_runup=0.2,
                max_drawdown=-0.05,
                rug_like_drop=False,
                no_future_liquidity=False,
                label_quality="sparse",
            )
        ],
        warning_flags=["exploratory_backtest_not_live_signal"],
    )


def test_result_to_dict_serializes_nested_payload() -> None:
    payload = result_to_dict(_result())
    assert payload["result_id"] == "result-1"
    assert payload["rule"]["conditions"][0]["field_name"] == "possible_buy_count"


def test_write_result_json_writes_valid_json(tmp_path: Path) -> None:
    output_path = write_result_json(_result(), tmp_path / "result.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["result_id"] == "result-1"


def test_write_result_markdown_writes_readable_markdown_with_warnings(tmp_path: Path) -> None:
    output_path = write_result_markdown(_result(), tmp_path / "result.md")
    text = output_path.read_text(encoding="utf-8")
    assert "# Rule Backtest: Rule 1" in text
    assert "## Cost Assumptions" in text
    assert "`exploratory_backtest_not_live_signal`" in text
    assert "| Token | Snapshot TS |" in text


def test_write_multi_result_markdown_writes_comparison_table(tmp_path: Path) -> None:
    output_path = write_multi_result_markdown([_result()], tmp_path / "comparison.md")
    text = output_path.read_text(encoding="utf-8")
    assert "# Rule Backtest Comparison" in text
    assert "| Rule | Selected | Tokens |" in text
    assert "exploratory_backtest_not_live_signal" in text


def test_format_helpers_handle_none_safely() -> None:
    assert format_percent(None) == "n/a"
    assert format_number(None) == "n/a"
    assert format_percent(0.25) == "25.00%"
    assert format_number(1.23456) == "1.2346"
