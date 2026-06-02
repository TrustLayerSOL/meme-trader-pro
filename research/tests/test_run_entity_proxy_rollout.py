import json
from pathlib import Path

from research.mtp_research.validation.run_entity_proxy_rollout import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_entity_proxy_rollout_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [{"launch_id": "launch-a", "token_mint": "mint-a", "launch_ts": 1, "metadata_json": {"creator_deployer": "creator-a"}}],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "event_id": "e1",
                "token_mint": "mint-a",
                "actor": "actor-a",
                "side": "accumulate",
                "signature": "sig-a",
                "block_time": 2,
                "slot": 2,
            }
        ],
    )
    holder_path = _write_jsonl(
        tmp_path / "holder.jsonl",
        [{"launch_id": "launch-a", "mint": "mint-a", "snapshot_age_seconds": 1800, "creator_holder_share": 0.0}],
    )
    dataset_dir = tmp_path / "dataset"
    report_dir = tmp_path / "reports"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_entity_proxy_rollout",
            "--candidates-path",
            str(candidates_path),
            "--events-path",
            str(events_path),
            "--holder-state-snapshots-path",
            str(holder_path),
            "--dataset-dir",
            str(dataset_dir),
            "--report-dir",
            str(report_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "readiness_classification=" in output
    assert "launches_processed=1" in output
    assert (dataset_dir / "entity_proxy_strict_cohort.jsonl").exists()
    assert (dataset_dir / "entity_proxy_strict_cohort.parquet").exists()
    assert (report_dir / "entity_proxy_strict_cohort_audit.json").exists()
    assert (report_dir / "entity_proxy_strict_cohort_audit.md").exists()
