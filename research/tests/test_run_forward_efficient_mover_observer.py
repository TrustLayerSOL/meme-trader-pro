from pathlib import Path

from research.mtp_research.validation.run_forward_efficient_mover_observer import main


def test_cli_dry_run_prints_status_and_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "dry-run",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Forward Efficient Mover Observer Dry Run" in output
    assert "readiness_classification=forward_observer_ready_for_dry_run" in output
    assert str(tmp_path) in output


def test_cli_status_reads_existing_files(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "data" / "forward_observation" / "efficient_movers"
    root.mkdir(parents=True)
    (root / "candidates.jsonl").write_text('{"observation_id":"obs-a","mint":"mint-a","status":"completed","trigger_level":"20k"}\n', encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "status",
            "--data-root",
            str(tmp_path),
            "--target-candidates",
            "3",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Forward Efficient Mover Observation Status" in output
    assert "Total candidates observed: 1 / 3 target" in output
    assert "Remaining until target: 2" in output


def test_cli_observe_mock_source_writes_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_forward_efficient_mover_observer",
            "--mode",
            "observe",
            "--source",
            "mock",
            "--data-root",
            str(tmp_path),
            "--target-candidates",
            "1",
            "--max-observe-iterations",
            "1",
            "--mock-candidate-json",
            '{"mint":"mint-a","fdv_proxy":25000,"event_count":4,"buy_count":3,"sell_count":1,"active_wallets":2}',
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Forward Efficient Mover Observation Loop" in output
    assert "total_candidates=1" in output
    assert (tmp_path / "data" / "forward_observation" / "efficient_movers" / "candidates.jsonl").exists()
