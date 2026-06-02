import json
from pathlib import Path

from research.mtp_research.validation.run_holder_state_pilot import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_holder_state_pilot_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "launch_time_utc": "2026-01-01T00:00:00+00:00",
                "launch_weekday": "Thursday",
                "launch_hour_local": 0,
                "launch_minute_local": 0,
                "launch_day_of_week": 3,
                "launch_is_weekend": False,
                "launch_regime": "test",
                "source": "test",
                "pool_address": "pool-a",
                "venue": "pumpfun",
                "metadata_json": {"creator_deployer": "wallet-a"},
            }
        ],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
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
            }
        ],
    )
    output_dir = tmp_path / "holder_state_pilot"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_holder_state_pilot",
            "--candidates-path",
            str(candidates_path),
            "--events-path",
            str(events_path),
            "--output-dir",
            str(output_dir),
            "--launch-limit",
            "1",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "feasibility_result=feasible_offline" in output
    assert "api_calls_used=0" in output
    assert "helius_credits_used=0" in output
    assert "creator_holder_share_coverage_pct=100.00" in output
    assert (output_dir / "holder_state_feasibility_audit.md").exists()
    assert (output_dir / "holder_state_pilot_quality_report.json").exists()
    assert (output_dir / "holder_state_pilot_quality_report.md").exists()
    assert (output_dir / "holder_state_rollout_recommendation.md").exists()
    assert (output_dir / "holder_state_pilot_summary.json").exists()
    assert (output_dir / "holder_state_pilot_summary.md").exists()
    assert (output_dir / "holder_state_snapshots.jsonl").exists()
