import json
import sys
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import (
    apply_paper_decision,
    build_paper_bankroll_state,
    initialize_forward_paper_shadow,
)
from research.mtp_research.validation.run_forward_paper_shadow import main as paper_shadow_main


def test_paper_bankroll_starts_at_100_and_sizes_next_buy_at_10_percent() -> None:
    state = build_paper_bankroll_state(starting_bankroll_usd=100, max_position_fraction=0.10)

    buy_result = apply_paper_decision(
        state,
        {
            "timestamp": 1,
            "mint": "mint-a",
            "rule_id": "BUY_RULE_A",
            "side": "paper_buy",
            "paper_price_usd": 2,
        },
    )

    assert buy_result["ledger_row"]["allocation_usd"] == 10
    assert buy_result["state"]["cash_bankroll_usd"] == 90
    assert buy_result["state"]["total_bankroll_usd"] == 100
    assert buy_result["state"]["next_max_position_usd"] == 10


def test_next_buy_uses_increased_bankroll_after_profitable_sell() -> None:
    state = build_paper_bankroll_state(starting_bankroll_usd=100, max_position_fraction=0.10)
    bought = apply_paper_decision(
        state,
        {
            "timestamp": 1,
            "mint": "mint-a",
            "rule_id": "BUY_RULE_A",
            "side": "paper_buy",
            "paper_price_usd": 2,
        },
    )["state"]

    sold = apply_paper_decision(
        bought,
        {
            "timestamp": 2,
            "mint": "mint-a",
            "rule_id": "SELL_RULE_A",
            "side": "paper_sell",
            "paper_price_usd": 4,
        },
    )

    assert sold["ledger_row"]["realized_pnl_usd"] == 10
    assert sold["state"]["total_bankroll_usd"] == 110
    assert sold["state"]["next_max_position_usd"] == 11
    assert sold["state"]["rule_performance"]["BUY_RULE_A"]["realized_pnl_usd"] == 10
    assert sold["state"]["rule_performance"]["SELL_RULE_A"]["sells"] == 1


def test_initialize_paper_simulation_requires_explicit_enable(tmp_path: Path) -> None:
    default_result = initialize_forward_paper_shadow(data_root=tmp_path, execute=True)
    enabled_result = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )

    assert default_result["enabled"] is False
    assert enabled_result["enabled"] is True
    assert enabled_result["readiness"] == "paper_bankroll_tracker_ready"
    state = json.loads(Path(enabled_result["bankroll_state_path"]).read_text(encoding="utf-8"))
    assert state["total_bankroll_usd"] == 100
    assert state["next_max_position_usd"] == 10
    assert state["no_live_trade_flag"] is True


def test_forward_paper_shadow_cli_enables_paper_bankroll_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_paper_shadow",
            "--data-root",
            str(tmp_path),
            "--execute",
            "--enable-paper-simulation",
            "--starting-bankroll-usd",
            "100",
            "--max-position-fraction",
            "0.10",
        ],
    )

    assert paper_shadow_main() == 0

    output = capsys.readouterr().out
    assert "enabled=True" in output
    assert "readiness=paper_bankroll_tracker_ready" in output
    assert "current_bankroll_usd=100" in output
    assert "next_max_position_usd=10" in output


def test_paper_bankroll_module_does_not_add_live_runtime_logic() -> None:
    text = Path("research/mtp_research/validation/forward_paper_shadow.py").read_text(encoding="utf-8").lower()
    forbidden = ["place_order", "submit_order", "send_transaction", "secret_key", "auto_buy", "auto_sell", "grid_search"]
    for pattern in forbidden:
        assert pattern not in text
