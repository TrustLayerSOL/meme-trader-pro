import json
from pathlib import Path

from research.mtp_research.validation.run_historical_date_expansion import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_historical_date_expansion_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    snapshots = [
        {
            "launch_id": "launch-a",
            "token_mint": "mint-a",
            "launch_ts": 1_700_000_000,
            "snapshot_ts": 1_700_000_060,
            "launch_age_seconds": 60,
            "valuation_proxy_available": True,
            "valuation_proxy_usd": 20_000,
            "buy_count": 3,
            "sell_count": 1,
            "active_wallets": 2,
            "tx_count": 4,
            "metadata_json": {"event_count": 4},
        }
    ]
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", snapshots)
    report_dir = tmp_path / "reports"
    output_root = tmp_path / "expanded"
    status_path = tmp_path / "STATUS.md"
    plan_path = tmp_path / "PLAN.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_historical_date_expansion",
            "--snapshots-path",
            str(snapshots_path),
            "--report-dir",
            str(report_dir),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
            "--plan-path",
            str(plan_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "readiness_classification=historical_expansion_requires_external_acquisition" in output
    assert (report_dir / "historical_coverage_audit.json").exists()
    assert (report_dir / "historical_date_expansion_summary.json").exists()
    assert (report_dir / "historical_expansion_plan.json").exists()
    assert (output_root / "expanded_trigger_labels.jsonl").exists()
    assert status_path.exists()
    assert plan_path.exists()
