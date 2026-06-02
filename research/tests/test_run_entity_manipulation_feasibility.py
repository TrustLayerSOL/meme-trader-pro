import json
from pathlib import Path

from research.mtp_research.validation.run_entity_manipulation_feasibility import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_entity_proxy_feasibility_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1_700_000_000,
                "metadata_json": {"creator_deployer": "creator-a", "creation_signature": "create-a"},
            }
        ],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "event_id": "e1",
                "token_mint": "mint-a",
                "actor": "actor-a",
                "side": "accumulate",
                "event_type": "token_accumulation",
                "venue": "pumpfun_buy",
                "signature": "sig-a",
                "block_time": 1_700_000_010,
                "slot": 1,
                "base_qty": 10,
                "quote_qty": 1,
                "metadata_json": {},
            }
        ],
    )
    holder_path = _write_jsonl(
        tmp_path / "holder.jsonl",
        [
            {
                "launch_id": "launch-a",
                "mint": "mint-a",
                "snapshot_age_seconds": 1800,
                "holder_count": 1,
                "creator_holder_share": 0.0,
                "top_holder_share": 1.0,
                "top_10_holder_share": 1.0,
            }
        ],
    )
    output_dir = tmp_path / "reports"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_entity_manipulation_feasibility",
            "--candidates-path",
            str(candidates_path),
            "--events-path",
            str(events_path),
            "--holder-state-snapshots-path",
            str(holder_path),
            "--output-dir",
            str(output_dir),
            "--max-launches",
            "100",
            "--max-events",
            "10000",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "readiness_classification=" in output
    assert "launches_attempted=1" in output
    assert (output_dir / "entity_manipulation_data_availability.md").exists()
    assert (output_dir / "entity_proxy_pilot.json").exists()
    assert (output_dir / "entity_proxy_pilot.md").exists()
