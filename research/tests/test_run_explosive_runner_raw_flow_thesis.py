import json
from pathlib import Path

from research.mtp_research.validation.run_explosive_runner_raw_flow_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_t011_cli_writes_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1_000,
                "snapshot_ts": 1_060,
                "launch_age_seconds": 60,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 20_000,
                "buy_count": 5,
                "sell_count": 1,
                "active_wallets": 4,
                "unique_actors": 4,
                "tx_count": 6,
                "metadata_json": {"event_count": 6},
            },
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1_000,
                "snapshot_ts": 1_120,
                "launch_age_seconds": 120,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 100_000,
                "buy_count": 8,
                "sell_count": 1,
                "active_wallets": 6,
                "unique_actors": 6,
                "tx_count": 9,
                "metadata_json": {"event_count": 9},
            },
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T011_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_explosive_runner_raw_flow_thesis",
            "--snapshots-path",
            str(snapshots_path),
            "--holder-state-snapshots-path",
            "",
            "--entity-proxy-path",
            "",
            "--migration-labels-path",
            "",
            "--funding-link-path",
            "",
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "thesis_id=T011" in output
    assert "trigger_20k_count=1" in output
    assert (output_dir / "T011_explosive_runner_raw_flow_summary.json").exists()
    assert (output_dir / "T011_explosive_runner_raw_flow_summary.md").exists()
    assert (output_dir / "milestone_tier_feature_table.csv").exists()
    assert (output_dir / "trigger_20k_feature_rows.csv").exists()
    assert "No trading rules were generated." in status_path.read_text(encoding="utf-8")
