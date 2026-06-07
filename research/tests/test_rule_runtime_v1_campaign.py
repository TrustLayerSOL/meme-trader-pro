from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.rule_runtime_v1 import RuleRuntimeConfig, initialize_rule_runtime
from research.mtp_research.validation.rule_runtime_v1_campaign import (
    build_scan_command,
    campaign_paths,
    campaign_status_payload,
    helius_credits_used,
    write_campaign_preflight,
    write_status_snapshot,
)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def test_campaign_preflight_writes_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path, starting_wallet_usd=300.0, position_fraction=0.15)
    paths = campaign_paths(tmp_path, "rule_runtime_v1_8hr_locked_rule_test")
    initialize_rule_runtime(config, reset=True)
    monkeypatch.setattr(
        "research.mtp_research.validation.rule_runtime_v1_campaign.resolve_helius_api_key",
        lambda *, load_project_dotenv=True: "key",
    )

    preflight = write_campaign_preflight(
        config,
        paths,
        capability_audit_fn=lambda _config: {
            "recommended_endpoint": {
                "name": "helius_beta",
                "transactionSubscribe_supported": True,
                "getAccountInfo_processed_supported": True,
            }
        },
    )

    assert isinstance(preflight["passed"], bool)
    assert preflight["checks"]["buy_sizing_set_to_15pct"] is True
    assert preflight["checks"]["paper_wallet_starts_at_300"] is True
    assert preflight["checks"]["transactionSubscribe_available"] is True
    assert paths.preflight_json_path.exists()
    assert "Campaign Preflight" in paths.preflight_md_path.read_text(encoding="utf-8")


def test_campaign_status_snapshot_reports_retry_credit_and_paper_metrics(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path, starting_wallet_usd=300.0, position_fraction=0.15)
    paths = campaign_paths(tmp_path, "rule_runtime_v1_8hr_locked_rule_test")
    initialize_rule_runtime(config, reset=True)
    _append_jsonl(
        config.pumpfun_create_stream_events_path,
        {"parser_status": "decoded", "mint": "mint-a"},
    )
    _append_jsonl(
        config.pumpfun_transaction_subscribe_raw_path,
        {"source": "transactionSubscribe"},
    )
    _append_jsonl(
        config.bonding_curve_account_probe_events_path,
        {
            "probe_status": "success",
            "probe_scheduled_during_stream": True,
            "probe_attempt_count": 2,
            "account_not_found_retry_count": 1,
            "account_not_found_recovered_by_retry": True,
            "observed_to_first_fdv_emitted_ms": 220.0,
            "getAccountInfo_latency_ms": 8.0,
        },
    )
    for index in range(7):
        _append_jsonl(
            config.bonding_curve_account_probe_events_path,
            {
                "mint": "mint-a",
                "probe_phase": "near_entry_live_watch",
                "probe_status": "success",
                "probe_attempt_count": 0,
                "helius_rpc_request_count": 0,
                "accountSubscribe_latency_ms": 4.0 + index,
            },
        )
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    state["cash_usd"] = 255.0
    state["scheduler_stats"]["near_entry_live_watch_futures"] = 2
    state["scheduler_stats"]["near_entry_live_watch_probe_rows"] = 7
    state["scheduler_stats"]["near_entry_live_watch_successes"] = 7
    state["open_positions"] = {
        "mint-a": {
            "mint": "mint-a",
            "allocation_usd": 45.0,
            "paper_buy_fdv": 20_000,
            "current_fdv": 24_000,
            "local_high_fdv": 24_000,
        }
    }
    config.runtime_state_path.write_text(json.dumps(state), encoding="utf-8")
    _append_jsonl(
        config.paper_trades_path,
        {"side": "paper_buy", "mint": "mint-a", "allocation_usd": 45.0, "paper_buy_fdv": 20_000},
    )

    snapshot = write_status_snapshot(
        config,
        paths,
        started_at=100.0,
        duration_seconds=28_800,
        process_pid=None,
        log_path=paths.log_path,
    )

    assert snapshot["helius_credits_used"] == 2
    assert snapshot["decoded_pumpfun_creates"] == 1
    assert snapshot["accountSubscribe_calls"] == 2
    assert snapshot["near_entry_live_watch_probe_rows"] == 7
    assert snapshot["near_entry_live_watch_successes"] == 7
    assert snapshot["account_not_found_recovered_by_retry"] == 1
    assert snapshot["paper_trading"]["current_paper_wallet_value"] == 309.0
    assert snapshot["paper_trading"]["current_15pct_buy_size"] == 46.35
    snapshot_json = list(paths.status_snapshots_root.glob("status_*.json"))
    snapshot_md = list(paths.status_snapshots_root.glob("status_*.md"))
    assert snapshot_json
    assert snapshot_md
    snapshot_text = snapshot_md[0].read_text(encoding="utf-8")
    assert "Helius credits used/cap" in snapshot_text
    assert "accountSubscribe calls/live-watch rows/successes" in snapshot_text


def test_campaign_status_counts_midrun_account_subscribe_rows_without_final_future_count(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    paths = campaign_paths(tmp_path, "rule_runtime_v1_8hr_locked_rule_test")
    initialize_rule_runtime(config, reset=True)
    for index in range(3):
        _append_jsonl(
            config.bonding_curve_account_probe_events_path,
            {
                "mint": "live-watch-mint",
                "probe_phase": "near_entry_live_watch",
                "probe_status": "success",
                "probe_attempt_count": 0,
                "helius_rpc_request_count": 0,
                "accountSubscribe_latency_ms": 5.0 + index,
            },
        )

    snapshot = campaign_status_payload(
        config,
        paths,
        started_at=100.0,
        duration_seconds=28_800,
        process_pid=None,
        log_path=paths.log_path,
    )

    assert snapshot["near_entry_live_watch_futures"] == 0
    assert snapshot["near_entry_live_watch_probe_rows"] == 3
    assert snapshot["accountSubscribe_calls"] == 1


def test_build_scan_command_uses_caffeinate_and_locked_paper_sizing(tmp_path: Path) -> None:
    paths = campaign_paths(tmp_path, "rule_runtime_v1_8hr_locked_rule_test")

    command = build_scan_command(repo_root=tmp_path, data_root=tmp_path, paths=paths)

    assert command[:2] == ["caffeinate", "-i"]
    assert "--mode" in command
    assert "transaction-subscribe-smoke" in command
    assert command[command.index("--position-fraction") + 1] == "0.15"
    assert command[command.index("--starting-wallet-usd") + 1] == "300.0"
    assert command[command.index("--max-helius-credits") + 1] == "500000"


def test_helius_credits_used_counts_probe_attempts(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    _append_jsonl(config.bonding_curve_account_probe_events_path, {"probe_attempt_count": 1})
    _append_jsonl(config.bonding_curve_account_probe_events_path, {"probe_attempt_count": 3})

    assert helius_credits_used(config) == 4
