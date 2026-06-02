import json
from pathlib import Path

from research.mtp_research.validation.run_repeated_buyer_runner_participation_report import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_repeated_buyer_report(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "creator": "creator-a",
                "launch_ts": 1_700_000_000,
                "snapshot_ts": 1_700_000_060,
                "launch_age_seconds": 60,
                "valuation_proxy_usd": 20_000,
                "buy_count": 4,
                "sell_count": 1,
                "active_wallets": 4,
                "tx_count": 5,
            }
        ],
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "token_mint": "mint-a",
                "actor": "wallet-a",
                "block_time": 1_700_000_030,
                "side": "accumulate",
                "event_type": "token_accumulation",
                "signature": "sig-a",
            }
        ],
    )
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_repeated_buyer_runner_participation_report",
            "--snapshot-path",
            str(snapshots),
            "--event-path",
            str(events),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(tmp_path / "REPEATED_BUYER_STATUS.md"),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=repeated_buyer_runner_participation_report_v0" in output
    assert "launches_analyzed=1" in output
    assert "readiness_classification=" in output
    assert (output_dir / "repeated_buyer_runner_participation_summary.json").exists()
    assert (output_dir / "repeated_buyer_tier_comparison.csv").exists()
