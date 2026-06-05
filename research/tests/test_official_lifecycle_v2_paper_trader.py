from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_v2_paper_trader import (
    OfficialV2PaperTradeConfig,
    initialize_paper_trader,
    run_paper_trade_once,
)
from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleV2Config, initialize_official_lifecycle_namespace


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def test_v2_paper_trader_buys_5_percent_and_sells_on_e2_with_metadata_monitor(tmp_path: Path) -> None:
    lifecycle = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(lifecycle)
    config = OfficialV2PaperTradeConfig(data_root=tmp_path, starting_wallet_usd=300, position_fraction=0.05)

    _append(
        lifecycle.followup_paths_path,
        {"mint": "mint-a", "timestamp": 100.0, "fdv_proxy": 22_000, "crossed_20k": True},
    )
    _append(
        lifecycle.followup_paths_path,
        {"mint": "mint-a", "timestamp": 120.0, "fdv_proxy": 33_000, "crossed_20k": True},
    )
    _append(
        lifecycle.paper_shadow_labels_path,
        {
            "mint": "mint-a",
            "label_time": 100.0,
            "official_baseline_entry_eligible": True,
            "baseline_all_actionable_20k": True,
            "B4_pass": True,
        },
    )
    _append(
        lifecycle.metadata_snapshots_path,
        {
            "mint": "mint-a",
            "observed_at": 99.0,
            "lifecycle_point": "birth",
            "token_name": "Token A",
            "token_symbol": "TA",
            "image_uri": "https://example.com/a.png",
        },
    )

    initialize_paper_trader(config, reset=True)
    first = run_paper_trade_once(config)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))

    assert first["buys_created"] == 1
    assert state["cash_usd"] == 285
    assert state["open_positions"]["mint-a"]["buy_marketcap"] == 22_000
    assert state["open_positions"]["mint-a"]["allocation_usd"] == 15
    assert state["open_positions"]["mint-a"]["token_name"] == "Token A"
    monitor_html = config.monitor_html_path.read_text(encoding="utf-8")
    monitor_json = json.loads(config.monitor_json_path.read_text(encoding="utf-8"))
    assert "Token A" in monitor_html
    assert 'content="10"' in monitor_html
    assert "copyCA('mint-a')" in monitor_html
    assert "Current Market Caps" in monitor_html
    assert monitor_json["open_positions"][0]["current_marketcap"] == 33_000

    _append(
        lifecycle.paper_shadow_exit_labels_path,
        {
            "mint": "mint-a",
            "timestamp": 140.0,
            "current_fdv": 44_000,
            "hypothetical_exit_condition_met": True,
            "hypothetical_exit_reason": "E2_milestone_trailing_drawdown_no_reclaim_label",
        },
    )
    second = run_paper_trade_once(config)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    ledger = [json.loads(line) for line in config.ledger_path.read_text(encoding="utf-8").splitlines()]

    assert second["sells_created"] == 1
    assert state["cash_usd"] == 315
    assert state["open_positions"] == {}
    assert ledger[0]["side"] == "paper_buy"
    assert ledger[0]["buy_reason"] == "MTP_V2_BASELINE_ACTIONABLE_20K_ENTRY"
    assert ledger[1]["side"] == "paper_sell"
    assert ledger[1]["sell_marketcap"] == 44_000
    assert ledger[1]["paper_profit_loss_usd"] == 15
    assert ledger[1]["sell_reason"] == "E2_milestone_trailing_drawdown_no_reclaim_label"


def test_v2_paper_trader_is_idempotent(tmp_path: Path) -> None:
    lifecycle = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(lifecycle)
    config = OfficialV2PaperTradeConfig(data_root=tmp_path)
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 100.0, "fdv_proxy": 20_000, "crossed_20k": True})
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 110.0, "fdv_proxy": 21_000, "crossed_20k": True})
    _append(
        lifecycle.paper_shadow_labels_path,
        {"mint": "mint-a", "label_time": 100.0, "official_baseline_entry_eligible": True, "baseline_all_actionable_20k": True},
    )

    initialize_paper_trader(config, reset=True)
    run_paper_trade_once(config)
    run_paper_trade_once(config)

    ledger = [json.loads(line) for line in config.ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(ledger) == 1


def test_v2_paper_trader_rejects_single_row_fdv_spike(tmp_path: Path) -> None:
    lifecycle = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(lifecycle)
    config = OfficialV2PaperTradeConfig(data_root=tmp_path)
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 90.0, "fdv_proxy": 3_200, "crossed_20k": False})
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 100.0, "fdv_proxy": 36_000, "crossed_20k": True})
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 103.0, "fdv_proxy": 3_100, "crossed_20k": False})
    _append(
        lifecycle.paper_shadow_labels_path,
        {"mint": "mint-a", "label_time": 100.0, "official_baseline_entry_eligible": True, "baseline_all_actionable_20k": True},
    )

    initialize_paper_trader(config, reset=True)
    result = run_paper_trade_once(config)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    ledger = [json.loads(line) for line in config.ledger_path.read_text(encoding="utf-8").splitlines()]

    assert result["buys_created"] == 0
    assert state["wallet_usd"] == 300
    assert state["open_positions"] == {}
    assert state["rejected_entry_mints"] == ["mint-a"]
    assert ledger[0]["side"] == "paper_rejected_entry"
    assert ledger[0]["rejection_reason"] == "single_row_fdv_spike_not_confirmed"


def test_v2_paper_trader_voids_existing_single_row_fdv_spike_trade(tmp_path: Path) -> None:
    lifecycle = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(lifecycle)
    config = OfficialV2PaperTradeConfig(data_root=tmp_path)
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 90.0, "fdv_proxy": 3_200, "crossed_20k": False})
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 100.0, "fdv_proxy": 36_000, "crossed_20k": True})
    _append(lifecycle.followup_paths_path, {"mint": "mint-a", "timestamp": 103.0, "fdv_proxy": 3_100, "crossed_20k": False})
    initialize_paper_trader(config, reset=True)
    config.ledger_path.write_text(
        "\n".join(
            [
                json.dumps({"mint": "mint-a", "timestamp": 100.0, "opened_at": 100.0, "side": "paper_buy", "allocation_usd": 15, "buy_marketcap": 36_000, "paper_profit_loss_usd": 0.0}),
                json.dumps({"mint": "mint-a", "timestamp": 120.0, "opened_at": 100.0, "side": "paper_sell", "allocation_usd": 15, "buy_marketcap": 36_000, "sell_marketcap": 3_100, "paper_profit_loss_usd": -13.708333}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config.state_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "mode": "paper_only_sidecar",
                "starting_wallet_usd": 300,
                "wallet_usd": 286.291667,
                "cash_usd": 286.291667,
                "position_fraction": 0.05,
                "open_positions": {},
                "closed_mints": ["mint-a"],
            }
        ),
        encoding="utf-8",
    )

    result = run_paper_trade_once(config)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    ledger = [json.loads(line) for line in config.ledger_path.read_text(encoding="utf-8").splitlines()]

    assert result["voids_created"] == 1
    assert state["wallet_usd"] == 300
    assert state["cash_usd"] == 300
    assert state["voided_mints"] == ["mint-a"]
    assert ledger[-1]["side"] == "paper_void"
    assert ledger[-1]["void_reason"] == "single_row_fdv_spike_not_confirmed"


def test_v2_paper_trader_contains_no_live_execution_logic() -> None:
    text = Path("research/mtp_research/validation/official_lifecycle_v2_paper_trader.py").read_text(encoding="utf-8").lower()
    forbidden = ["sendtransaction", "private_key", "secretkey", "jupiter", "swaptransaction"]
    assert not any(term in text for term in forbidden)
