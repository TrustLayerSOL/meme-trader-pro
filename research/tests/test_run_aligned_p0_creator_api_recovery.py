import json
from pathlib import Path

from research.mtp_research.validation.run_aligned_p0_creator_api_recovery import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def test_cli_runs_dry_run_without_execute(tmp_path: Path, capsys) -> None:
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [{"launch_id": "launch-a", "mint": "mint-a", "creator": "", "launch_ts": 1000}],
    )

    rc = main(
        [
            "--structural-features-path",
            str(structural),
            "--output-root",
            str(tmp_path / "lake"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
            "--max-mints",
            "1",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=aligned_p0_creator_api_recovery_v0" in out
    assert "executed=False" in out
    assert "selected_unknown_mints=1" in out
    assert "network_calls_made=0" in out
