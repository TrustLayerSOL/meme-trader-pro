import json
from pathlib import Path

from research.mtp_research.validation.run_early_ownership_concentration_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_json_markdown_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates = _write_jsonl(
        tmp_path / "launches.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "launch_regime": "mon_tue_wed_0600_1200_pt",
                "metadata_json": {"creator_deployer": "creator-a"},
            }
        ],
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "token_mint": "mint-a",
                "actor": "buyer-a",
                "block_time": 1010,
                "base_qty": 5,
                "venue": "pumpfun_buy",
            }
        ],
    )
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "token_mint": "mint-a",
                "launch_id": "launch-a",
                "launch_age_seconds": 30,
                "valuation_proxy_usd": 1000,
                "valuation_proxy_available": True,
            }
        ],
    )
    outcomes = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "token_mint": "mint-a",
                "launch_id": "launch-a",
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
                "proxy_threshold_outcomes_usable": True,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "thesis_status.md"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_early_ownership_concentration_thesis",
            "--candidates-path",
            str(candidates),
            "--events-path",
            str(events),
            "--snapshots-path",
            str(snapshots),
            "--outcomes-path",
            str(outcomes),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "thesis_id=T001" in output
    assert "json_summary_path=" in output
    assert (output_dir / "T001_early_ownership_concentration_summary.json").exists()
    assert (output_dir / "T001_early_ownership_concentration_summary.md").exists()
    assert status_path.exists()
    assert "No trading rules were generated." in status_path.read_text(encoding="utf-8")
