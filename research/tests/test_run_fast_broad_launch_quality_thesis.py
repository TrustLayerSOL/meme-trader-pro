import json
from pathlib import Path

from research.mtp_research.validation.run_fast_broad_launch_quality_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t009_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 60,
                "launch_ts": 1000,
                "snapshot_ts": 1060,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1000,
                "buy_count": 3,
                "sell_count": 1,
                "tx_count": 4,
                "active_wallets": 3,
                "unique_actors": 3,
                "liquidity_proxy": 2.0,
                "metadata_json": {"event_count": 4},
            }
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "runups": {"max_runup_120m": 0.2},
                "drawdowns": {"max_drawdown_120m": -0.1},
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T009_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fast_broad_launch_quality_thesis",
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

    assert "thesis_id=T009" in output
    assert "launch_count=1" in output
    assert (output_dir / "T009_fast_broad_launch_quality_summary.json").exists()
    assert (output_dir / "T009_fast_broad_launch_quality_summary.md").exists()
    status_text = status_path.read_text(encoding="utf-8")
    assert "FAST + BROAD EARLY LAUNCH QUALITY" in status_text
    assert "No thesis promotion was made." in status_text
    assert "No trading rules were generated." in status_text
