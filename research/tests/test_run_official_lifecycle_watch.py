import sys
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleConfig, initialize_official_lifecycle_namespace
from research.mtp_research.validation.run_forward_efficient_mover_observer import main


def test_cli_status_supports_official_lifecycle_sample(tmp_path: Path, monkeypatch, capsys) -> None:
    initialize_official_lifecycle_namespace(OfficialLifecycleConfig(data_root=tmp_path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "status",
            "--sample",
            "official_lifecycle_watch_v1",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Official Lifecycle Watch v1 Status" in output
    assert "Births observed:" in output
    assert "Official crossed-20k target progress:" in output
    assert "Quality status:" in output


def test_cli_observe_lifecycle_mock_smoke_initializes_official_sample(tmp_path: Path, monkeypatch, capsys) -> None:
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
            "mock",
            "--data-root",
            str(tmp_path),
            "--target-births",
            "3",
            "--target-crossed-20k",
            "300",
            "--max-runtime-minutes",
            "30",
            "--max-helius-credits",
            "50000",
            "--execute",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Official Lifecycle Watch v1 Smoke" in output
    assert "execute=True" in output
    assert "smoke_births_observed=3" in output
    assert "under_5s_followup_count=3" in output
    assert "readiness_classification=official_lifecycle_watch_ready_for_100_birth_smoke" in output
    assert (tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "lifecycle_state.json").exists()
