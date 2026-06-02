import csv
from pathlib import Path

from research.mtp_research.validation.run_p0_top_holder_replay_pilot import main


def _write_targets(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["launch_id", "mint", "milestone", "milestone_time", "milestone_age_seconds"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "launch_id": "launch-a",
                "mint": "mint-a",
                "milestone": "20k",
                "milestone_time": 1_700_000_120,
                "milestone_age_seconds": 120,
            }
        )
    return path


def test_cli_dry_run_writes_report_with_explicit_paths(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--target-csv-path",
            str(_write_targets(tmp_path / "targets.csv")),
            "--raw-path",
            str(tmp_path / "raw.jsonl"),
            "--jsonl-path",
            str(tmp_path / "replay.jsonl"),
            "--parquet-path",
            str(tmp_path / "replay.parquet"),
            "--checkpoint-path",
            str(tmp_path / "checkpoint.json"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "report_id=p0_top_holder_replay_pilot_v0" in output
    assert "mode=dry_run" in output
    assert "network_calls_made=0" in output
    assert (tmp_path / "reports" / "top_holder_replay_pilot_summary.json").exists()
