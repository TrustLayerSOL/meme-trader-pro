import json
from pathlib import Path

from research.mtp_research.validation.run_explosive_runner_winner_anatomy_report import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, ts: int, age: int, value: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": ts,
        "snapshot_ts": ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": 3,
        "sell_count": 1,
        "active_wallets": 3,
        "unique_actors": 3,
        "tx_count": 4,
        "metadata_json": {"event_count": 4},
    }


def test_cli_writes_broad_winner_anatomy_report(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 30, 15_000),
            _snapshot("mint-a", 1_700_000_000, 60, 20_000),
            _snapshot("mint-a", 1_700_000_000, 120, 100_000),
            _snapshot("mint-b", 1_700_086_400, 30, 10_000),
            _snapshot("mint-b", 1_700_086_400, 60, 20_000),
            _snapshot("mint-b", 1_700_086_400, 120, 30_000),
        ],
    )
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_explosive_runner_winner_anatomy_report",
            "--snapshot-path",
            str(snapshots),
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
            str(tmp_path / "WINNER_STATUS.md"),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=explosive_runner_winner_anatomy_report_v0" in output
    assert "launches_analyzed=2" in output
    assert (output_dir / "explosive_runner_winner_anatomy_report_summary.json").exists()
    assert (output_dir / "milestone_tier_feature_comparison.csv").exists()
