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
    assert "Frozen buy rule: BROAD_10K_WATCH_20K_BUY" in status.stdout
    assert "Frozen exit rule: EXIT_NO_RECLAIM" in status.stdout
    assert "Live trading enabled: false" in status.stdout
    assert "Paper trading enabled: true" in status.stdout
    assert "Confirmed 10k watches:" in status.stdout
    assert "Confirmed 20k entry candidates:" in status.stdout
    assert "Metadata hot path blocked: true" in status.stdout
    assert "No real trade flag: true" in status.stdout
