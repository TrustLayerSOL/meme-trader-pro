import json
import sys
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import (
    apply_paper_decision,
    build_paper_bankroll_state,
    initialize_forward_paper_shadow,
    paper_bankroll_status,
    process_lifecycle_path_for_paper_rules,
)
from research.mtp_research.validation.official_lifecycle_watch import (
    OfficialLifecycleConfig,
    OfficialLifecycleStateMachine,
    initialize_official_lifecycle_namespace,
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


def test_initialize_paper_simulation_preserves_existing_bankroll_state(tmp_path: Path) -> None:
    initial = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    state_path = Path(initial["bankroll_state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
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
    state_path.write_text(json.dumps(bought), encoding="utf-8")

    preserved = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )

    preserved_state = json.loads(Path(preserved["bankroll_state_path"]).read_text(encoding="utf-8"))
    assert preserved_state["cash_bankroll_usd"] == 90
    assert "mint-a" in preserved_state["open_positions"]


def test_lifecycle_paper_rule_processor_is_noop_without_enabled_state(tmp_path: Path) -> None:
    result = process_lifecycle_path_for_paper_rules(
        tmp_path / "missing",
        {
            "mint": "mint-a",
            "timestamp": 1,
            "fdv_proxy": 22_000,
            "crossed_20k": True,
        },
        {"first_followup_before_20k": True},
    )

    assert result["enabled"] is False
    assert result["decisions_written"] == 0


def test_lifecycle_paper_rule_processor_records_entry_and_maturity_exit(tmp_path: Path) -> None:
    initialized = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    observation_root = Path(initialized["bankroll_state_path"]).parent

    entry = process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 1,
            "fdv_proxy": 22_000,
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "state": "trigger_qualified_active_watch",
        },
        {"first_followup_before_20k": True, "fdv_path_before_20k": True},
    )
    exit_result = process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 2,
            "fdv_proxy": 1_100_000,
            "crossed_1m": True,
            "state": "matured_reached_1m",
        },
        {"first_followup_before_20k": True, "fdv_path_before_20k": True},
    )

    ledger_rows = _read_jsonl(Path(initialized["bankroll_ledger_path"]))
    final_state = json.loads(Path(initialized["bankroll_state_path"]).read_text(encoding="utf-8"))
    assert entry["decisions_written"] == 1
    assert exit_result["decisions_written"] == 1
    assert [row["side"] for row in ledger_rows] == ["paper_buy", "paper_sell"]
    assert ledger_rows[0]["rule_id"] == "PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY"
    assert ledger_rows[1]["rule_id"] == "PBCL_EXIT_MAX_AGE_OR_INACTIVE"
    assert final_state["total_bankroll_usd"] > 100
    assert final_state["next_max_position_usd"] == round(final_state["total_bankroll_usd"] * 0.10, 6)
    assert final_state["rule_performance"]["PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY"]["realized_pnl_usd"] > 0


def test_lifecycle_paper_rule_processor_skips_far_above_trigger_chase(tmp_path: Path) -> None:
    initialized = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    observation_root = Path(initialized["bankroll_state_path"]).parent

    result = process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 1,
            "fdv_proxy": 69_954_418_736,
            "crossed_20k": True,
            "crossed_50k": True,
            "crossed_100k": True,
            "crossed_500k": True,
            "crossed_1m": True,
            "state": "matured_reached_1m",
        },
        {"first_followup_before_20k": True},
    )

    assert result["decisions_written"] == 0
    assert _read_jsonl(Path(initialized["bankroll_ledger_path"])) == []


def test_lifecycle_paper_rule_processor_does_not_exit_before_entry_timestamp(tmp_path: Path) -> None:
    initialized = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    observation_root = Path(initialized["bankroll_state_path"]).parent
    process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 100,
            "fdv_proxy": 22_000,
            "crossed_20k": True,
            "state": "trigger_qualified_active_watch",
        },
        {"first_followup_before_20k": True},
    )
    result = process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 90,
            "fdv_proxy": 1_100,
            "state": "matured_terminal_collapse",
            "drawdown_pct": 95,
        },
        {"first_followup_before_20k": True},
    )

    ledger_rows = _read_jsonl(Path(initialized["bankroll_ledger_path"]))
    assert result["decisions_written"] == 0
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["side"] == "paper_buy"


def test_paper_bankroll_status_reports_rule_performance(tmp_path: Path) -> None:
    initialized = initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    observation_root = Path(initialized["bankroll_state_path"]).parent
    process_lifecycle_path_for_paper_rules(
        observation_root,
        {
            "mint": "mint-a",
            "timestamp": 1,
            "fdv_proxy": 22_000,
            "crossed_20k": True,
            "state": "trigger_qualified_active_watch",
        },
        {"first_followup_before_20k": True},
    )

    status = paper_bankroll_status(data_root=tmp_path)

    assert status["enabled"] is True
    assert status["ledger_rows"] == 1
    assert status["open_position_count"] == 1
    assert status["current_bankroll_usd"] == 100
    assert status["next_max_position_usd"] == 10
    assert status["rule_performance"]["PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY"]["buys"] == 1


def test_official_lifecycle_path_hook_updates_paper_ledger_when_enabled(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    machine = OfficialLifecycleStateMachine(config)
    machine.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "first_followup_before_20k": True,
            "fdv_path_before_20k": True,
        }
    )

    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 103,
            "fdv_proxy": 22_000,
            "event_count": 1,
            "buy_count": 1,
            "sell_count": 0,
            "active_wallet_count": 1,
            "source_provenance": "mock_observed_path",
        }
    )

    ledger_path = config.observation_root / "paper_bankroll_ledger.jsonl"
    ledger_rows = _read_jsonl(ledger_path)
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["side"] == "paper_buy"
    assert ledger_rows[0]["allocation_usd"] == 10


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


def test_forward_paper_shadow_cli_prints_paper_status(tmp_path: Path, monkeypatch, capsys) -> None:
    initialize_forward_paper_shadow(
        data_root=tmp_path,
        execute=True,
        enable_paper_simulation=True,
        starting_bankroll_usd=100,
        max_position_fraction=0.10,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_paper_shadow",
            "--data-root",
            str(tmp_path),
            "--paper-status",
        ],
    )

    assert paper_shadow_main() == 0

    output = capsys.readouterr().out
    assert "Forward Paper Bankroll Status" in output
    assert "current_bankroll_usd=100" in output
    assert "ledger_rows=0" in output


def test_paper_bankroll_module_does_not_add_live_runtime_logic() -> None:
    text = Path("research/mtp_research/validation/forward_paper_shadow.py").read_text(encoding="utf-8").lower()
    forbidden = ["place_order", "submit_order", "send_transaction", "secret_key", "auto_buy", "auto_sell", "grid_search"]
    for pattern in forbidden:
        assert pattern not in text


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
