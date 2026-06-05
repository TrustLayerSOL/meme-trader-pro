from __future__ import annotations

import sys
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_watch import (
    OfficialLifecycleConfig,
    OfficialLifecycleV2Config,
    initialize_official_lifecycle_namespace,
)
from research.mtp_research.validation.run_forward_efficient_mover_observer import main


def test_cli_status_prints_no_laserstream_header(tmp_path: Path, monkeypatch, capsys) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    config.provisional_births_path.write_text(
        '{"signature":"sig-a","log_observed_at":100,"hydration_status":"pending_hydration"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "status",
            "--sample",
            "official_lifecycle_watch_v1",
            "--source",
            "helius-pumpfun-no-laserstream",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "## No-LaserStream Official Lifecycle Watch v1" in output
    assert "Provisional birth logs: 1" in output


def test_cli_status_prints_v2_paper_shadow_labels_for_no_laserstream(tmp_path: Path, monkeypatch, capsys) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    config.provisional_births_path.write_text(
        '{"signature":"sig-a","log_observed_at":100,"hydration_status":"pending_hydration"}\n',
        encoding="utf-8",
    )
    config.paper_shadow_labels_path.write_text(
        (
            '{"mint":"mint-a","official_baseline_entry_eligible":true,'
            '"B3_pass":true,"B4_pass":false,"E2_tracking_started":true,'
            '"no_real_trade":true,"no_paper_trade_enabled":true}\n'
        ),
        encoding="utf-8",
    )
    config.paper_shadow_exit_labels_path.write_text(
        (
            '{"mint":"mint-a","E2_state":"hypothetical_exit_condition_met",'
            '"hypothetical_exit_condition_met":true,'
            '"no_real_trade":true,"no_enabled_paper_trade":true}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "status",
            "--sample",
            "official_lifecycle_watch_v2",
            "--source",
            "helius-pumpfun-no-laserstream",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "## No-LaserStream Official Lifecycle Watch v2" in output
    assert "## Paper/Shadow Labels" in output
    assert "B3 pass: 1" in output
    assert "E2 unique mints with hypothetical exit: 1" in output
    assert "E2 total exit-event rows: 1" in output


def test_cli_observe_lifecycle_no_laserstream_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "observe-lifecycle",
            "--sample",
            "official_lifecycle_watch_v1",
            "--source",
            "helius-pumpfun-no-laserstream",
            "--target-births",
            "50",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "## Official Lifecycle Watch v1 Smoke" in output
    assert "execute=False" in output
    assert "readiness_classification=no_laserstream_collector_ready_for_100_birth_run" in output
    assert (
        tmp_path
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "official_lifecycle_watch_v1"
        / "no_laserstream_bottleneck_audit.json"
    ).exists()
