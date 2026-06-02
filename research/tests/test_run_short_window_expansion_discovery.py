import json
from pathlib import Path

from research.mtp_research.validation.run_short_window_expansion_discovery import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_short_window_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "snapshot_ts": 1060,
                "launch_age_seconds": 60,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 20_000,
                "active_wallets": 2,
                "unique_actors": 2,
                "buy_count": 2,
                "sell_count": 1,
                "tx_count": 3,
                "metadata_json": {"event_count": 3},
            },
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "snapshot_ts": 1120,
                "launch_age_seconds": 120,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 50_000,
                "active_wallets": 3,
                "unique_actors": 3,
                "buy_count": 3,
                "sell_count": 1,
                "tx_count": 4,
                "metadata_json": {"event_count": 4},
            },
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_short_window_expansion_discovery",
            "--snapshots-path",
            str(snapshots_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "report_id=short_window_expansion_discovery_v0" in output
    assert "launches_analyzed=1" in output
    assert (output_dir / "short_window_expansion_labels.json").exists()
    assert (output_dir / "short_window_expansion_labels.parquet").exists()
    assert (output_dir / "short_window_expansion_discovery_summary.json").exists()
    assert (output_dir / "short_window_expansion_discovery_summary.md").exists()
    status = status_path.read_text(encoding="utf-8")
    assert "explosive expansion" in status
    assert "No trading rules were generated." in status
