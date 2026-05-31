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
