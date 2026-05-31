from pathlib import Path

from research.mtp_research.pipeline import run_fast_offline_rebuild_review as runner


def test_fast_offline_rebuild_skip_flags_and_mocked_steps(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/features").mkdir(parents=True)
    (tmp_path / "data/features/feature_snapshots.jsonl").write_text("{}\n", encoding="utf-8")
    calls = []

    def fake_run(command):
        calls.append(command)

    monkeypatch.setattr(runner, "run_command_step", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fast_offline_rebuild_review",
            "--skip-clean-outcomes",
            "--skip-reports",
            "--max-snapshots",
            "10",
        ],
    )

    assert runner.main() == 0

    output = capsys.readouterr().out
    assert "step_skipped=clean_outcomes" in output
    assert "profile_markdown_path=" not in output
    assert calls
    assert not any("run_price_coverage_report" in part for call in calls for part in call)


def test_fast_offline_rebuild_keyboard_interrupt_reports_partial(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt(_command):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "run_command_step", interrupt)
    monkeypatch.setattr("sys.argv", ["run_fast_offline_rebuild_review", "--skip-reports"])

    assert runner.main() == 130

    output = capsys.readouterr().out
    assert "interrupted=True" in output
    assert "partial_counts.raw=0" in output


def test_fast_offline_rebuild_passes_snapshot_selection_args(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/features").mkdir(parents=True)
    (tmp_path / "data/features/feature_snapshots.jsonl").write_text("{}\n", encoding="utf-8")
    calls = []

    def fake_run(command):
        calls.append(command)

    monkeypatch.setattr(runner, "run_command_step", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fast_offline_rebuild_review",
            "--skip-reports",
            "--snapshot-selection-strategy",
            "per_token_even",
            "--max-snapshots-per-token",
            "1000",
            "--min-time-gap-seconds",
            "60",
        ],
    )

    assert runner.main() == 0

    outcome_calls = [
        call for call in calls if "research.mtp_research.validation.run_build_outcome_labels" in call
    ]
    assert len(outcome_calls) == 2
    for call in outcome_calls:
        assert "--snapshot-selection-strategy" in call
        assert "per_token_even" in call
        assert "--max-snapshots-per-token" in call
        assert "1000" in call
        assert "--min-time-gap-seconds" in call
        assert "60" in call

    output = capsys.readouterr().out
    assert "network_calls=0" in output


def test_fast_offline_rebuild_passes_wider_diagnostic_entry_staleness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/features").mkdir(parents=True)
    (tmp_path / "data/features/feature_snapshots.jsonl").write_text("{}\n", encoding="utf-8")
    calls = []

    def fake_run(command):
        calls.append(command)

    monkeypatch.setattr(runner, "run_command_step", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fast_offline_rebuild_review",
            "--skip-reports",
            "--diagnostic-entry-max-staleness-sec",
            "120",
        ],
    )

    assert runner.main() == 0

    diagnostic_calls = [
        call
        for call in calls
        if "research.mtp_research.validation.run_build_outcome_labels" in call
        and "--allow-nearest-entry-fallback" in call
    ]
    assert len(diagnostic_calls) == 1
    diagnostic_call = diagnostic_calls[0]
    assert "--entry-max-staleness-sec" in diagnostic_call
    assert diagnostic_call[diagnostic_call.index("--entry-max-staleness-sec") + 1] == "120"
