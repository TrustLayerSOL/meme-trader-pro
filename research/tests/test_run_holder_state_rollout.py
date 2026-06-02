import json
from pathlib import Path

from research.mtp_research.validation.run_holder_state_rollout import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_rollout_cli_writes_expected_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [{
            "launch_id": "launch-a",
            "token_mint": "mint-a",
            "launch_ts": 1000,
            "launch_time_utc": "2026-01-01T00:00:00+00:00",
            "launch_weekday": "Thursday",
            "launch_hour_local": 0,
            "launch_minute_local": 0,
            "launch_day_of_week": 3,
            "launch_is_weekend": False,
            "launch_regime": "strict",
            "source": "test",
            "pool_address": "pool-a",
            "venue": "pumpfun",
            "metadata_json": {"creator_deployer": "wallet-a"},
        }],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [{
            "event_id": "event-a",
            "signature": "sig-a",
            "slot": 1,
            "block_time": 1010,
            "event_type": "possible_buy",
            "token_mint": "mint-a",
            "venue": "pumpfun",
            "actor": "wallet-a",
            "side": "buy",
            "base_qty": 10,
            "source": "test",
            "metadata_json": {},
        }],
    )
    dataset_dir = tmp_path / "dataset"
    report_dir = tmp_path / "reports"
    negative_balance_report_dir = tmp_path / "negative_balance_reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_holder_state_rollout",
            "--candidates-path",
            str(candidates_path),
            "--events-path",
            str(events_path),
            "--dataset-dir",
            str(dataset_dir),
            "--report-dir",
            str(report_dir),
            "--negative-balance-report-dir",
            str(negative_balance_report_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "readiness_classification=holder_state_ready_for_T001_T002_v2" in output
    assert "snapshots_expected=5" in output
    assert "snapshots_built=5" in output
    assert (dataset_dir / "strict_cohort_holder_state_snapshots.jsonl").exists()
    assert (dataset_dir / "strict_cohort_holder_state_snapshots.parquet").exists()
    assert (report_dir / "holder_state_strict_cohort_audit.json").exists()
    assert (report_dir / "holder_state_strict_cohort_audit.md").exists()
    assert (negative_balance_report_dir / "negative_balance_diagnostics.json").exists()
    assert (negative_balance_report_dir / "negative_balance_diagnostics.md").exists()
