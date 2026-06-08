from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_rule_runtime_cli_init_status_and_once(tmp_path: Path) -> None:
    init = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mtp_research.validation.run_rule_runtime_v1",
            "--mode",
            "init",
            "--data-root",
            str(tmp_path),
            "--reset",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "## Rule Runtime v1 Initialized" in init.stdout
    assert "Live trading enabled: false" in init.stdout
    assert "Paper trading enabled: true" in init.stdout

    event = {
        "mint": "mint-a",
        "timestamp": 100,
        "fdv_proxy": 10_500,
        "event_count": 5,
        "buy_count": 2,
        "active_wallet_count": 2,
    }
    once = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mtp_research.validation.run_rule_runtime_v1",
            "--mode",
            "once",
            "--data-root",
            str(tmp_path),
            "--event-json",
            json.dumps(event),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "processed_events=1" in once.stdout

    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mtp_research.validation.run_rule_runtime_v1",
            "--mode",
            "status",
            "--data-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "## Rule Runtime v1 Status" in status.stdout
    assert "Frozen buy rule: RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER" in status.stdout
    assert "Frozen exit rule: EXIT_V2_PROFIT_LOCK_WITH_RUNNER" in status.stdout
    assert "Live trading enabled: false" in status.stdout
    assert "Paper trading enabled: true" in status.stdout
    assert "Confirmed 10k watches:" in status.stdout
    assert "Confirmed 20k entry candidates:" in status.stdout
    assert "Runtime mode:" in status.stdout
    assert "Live bus events:" in status.stdout
    assert "File adapter events:" in status.stdout
    assert "Latency event_to_rule p50/p90/p99:" in status.stdout
    assert "Latency bus_to_runtime p50/p90/p99:" in status.stdout
    assert "Latency runtime_eval p50/p90/p99:" in status.stdout
    assert "## First FDV Queue" in status.stdout
    assert "Scheduler mode: priority_single_worker" in status.stdout
    assert "Metadata hot path blocked: true" in status.stdout
    assert "No real trade flag: true" in status.stdout


def test_rule_runtime_cli_smoke_live_bus_with_mock_events(tmp_path: Path) -> None:
    events = [
        {"event_id": "e1", "mint": "mint-a", "observed_at": 100, "fdv_proxy": 10_500, "event_count": 5, "buy_count": 2, "active_wallet_count": 2},
        {"event_id": "e2", "mint": "mint-a", "observed_at": 130, "fdv_proxy": 11_000, "event_count": 6, "buy_count": 3, "active_wallet_count": 3},
    ]
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mtp_research.validation.run_rule_runtime_v1",
            "--mode",
            "smoke-live-bus",
            "--data-root",
            str(tmp_path),
            "--mock-live-bus-events",
            str(event_path),
            "--reset",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "## Rule Runtime v1 Live Bus Smoke" in result.stdout
    assert "runtime_mode=live_bus" in result.stdout
    assert "events_processed=2" in result.stdout
    assert "confirmed_10k_watches=1" in result.stdout


def test_rule_runtime_cli_triage_smoke_with_mock_events(tmp_path: Path) -> None:
    events = [
        {"event_id": "e1", "mint": "near", "observed_at": 100, "fdv_proxy": 5_500, "event_count": 5, "buy_count": 2, "active_wallet_count": 2},
    ]
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.mtp_research.validation.run_rule_runtime_v1",
            "--mode",
            "triage-smoke",
            "--data-root",
            str(tmp_path),
            "--mock-live-bus-events",
            str(event_path),
            "--reset",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "## First FDV Queue Triage Smoke" in result.stdout
    assert "scheduler_mode=priority_single_worker" in result.stdout
    assert "parallel_workers_added=False" in result.stdout
    assert "events_processed=1" in result.stdout
