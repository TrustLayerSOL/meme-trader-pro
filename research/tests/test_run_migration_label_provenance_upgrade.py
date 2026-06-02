import json
from pathlib import Path

from research.mtp_research.validation.run_migration_label_provenance_upgrade import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_runs_offline_and_writes_reports(tmp_path: Path, capsys) -> None:
    candidates = [
        {
            "launch_id": "launch-1",
            "token_mint": "mint-1",
            "launch_ts": 1_700_000_001,
            "metadata_json": {"creator_deployer": "creator-a"},
        }
    ]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-a",
            "migration_time": "2026-05-25T13:37:31+00:00",
            "dex_pair_detected": True,
            "migration_source": "dexscreener_pair_created_at",
        }
    ]

    result = main(
        [
            "--candidates-path",
            str(_write_jsonl(tmp_path / "candidates.jsonl", candidates)),
            "--migration-labels-path",
            str(_write_jsonl(tmp_path / "labels.jsonl", labels)),
            "--output-dir",
            str(tmp_path / "reports"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
            "--max-targets",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "report_id=migration_label_provenance_upgrade" in output
    assert "network_calls_made=0" in output
    assert "selected_targets=1" in output
    assert (tmp_path / "reports" / "migration_label_provenance_upgrade_summary.json").exists()
    assert (tmp_path / "STATUS.md").exists()
