import json
from pathlib import Path

from research.mtp_research.validation.run_pre_launch_funding_collection import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_dry_run_writes_report_with_explicit_paths(tmp_path: Path, capsys) -> None:
    candidates = [
        {
            "launch_id": "launch-1",
            "token_mint": "mint-1",
            "launch_ts": 1000,
            "metadata_json": {"creator_deployer": "creator-a"},
        }
    ]

    result = main(
        [
            "--candidates-path",
            str(_write_jsonl(tmp_path / "candidates.jsonl", candidates)),
            "--max-creators",
            "1",
            "--raw-path",
            str(tmp_path / "raw.jsonl"),
            "--jsonl-path",
            str(tmp_path / "funding.jsonl"),
            "--parquet-path",
            str(tmp_path / "funding.parquet"),
            "--checkpoint-path",
            str(tmp_path / "checkpoint.json"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "report_id=funding_link_pilot_v0" in output
    assert "mode=dry_run" in output
    assert "requests_used=0" in output
    assert (tmp_path / "reports" / "funding_link_pilot_summary.json").exists()
