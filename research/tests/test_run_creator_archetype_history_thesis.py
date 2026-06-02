import json
from pathlib import Path

from research.mtp_research.validation.run_creator_archetype_history_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t003_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "launches.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "block_time": 1000,
                "metadata_json": {"creator_deployer": "creator-a"},
            }
        ],
    )
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 30,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1000,
            },
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 7200,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1200,
            },
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T003_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_creator_archetype_history_thesis",
            "--candidates-path",
            str(candidates_path),
            "--snapshots-path",
            str(snapshots_path),
            "--outcomes-path",
            str(outcomes_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "thesis_id=T003" in output
    assert "creator_count=1" in output
    assert (output_dir / "T003_creator_archetype_history_summary.json").exists()
    assert (output_dir / "T003_creator_archetype_history_summary.md").exists()
    status_text = status_path.read_text(encoding="utf-8")
    assert "Creator Archetype History" in status_text
    assert "No trading rules were generated." in status_text
    assert "Leakage Controls" in status_text
