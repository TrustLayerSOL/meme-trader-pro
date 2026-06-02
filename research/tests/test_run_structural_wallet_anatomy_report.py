import json
from pathlib import Path

from research.mtp_research.validation.run_structural_wallet_anatomy_report import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_structural_wallet_anatomy_report(tmp_path: Path, monkeypatch, capsys) -> None:
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
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_structural_wallet_anatomy_report",
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
            "--event-path",
            "",
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(tmp_path / "STRUCTURAL_STATUS.md"),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=structural_wallet_anatomy_report_v0" in output
    assert "launches_analyzed=1" in output
    assert "readiness_classification=" in output
    assert (output_dir / "structural_wallet_anatomy_summary.json").exists()
    assert (output_dir / "structural_feature_feasibility.csv").exists()
