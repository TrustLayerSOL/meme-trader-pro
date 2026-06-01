import json
import subprocess
from pathlib import Path

from research.mtp_research.launch_regime.lifecycle_quality_audit import run_launch_lifecycle_quality_audit


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def test_lifecycle_quality_audit_counts_coverage_and_warnings(tmp_path: Path) -> None:
    launches_path = _write_jsonl(
        tmp_path / "launches.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "launch_time_utc": "1970-01-01T00:16:40+00:00",
                "launch_weekday": "Monday",
                "launch_hour_local": 6,
                "launch_minute_local": 0,
                "launch_day_of_week": 0,
                "launch_is_weekend": False,
                "launch_regime": "mon_tue_wed_0600_1200_pt",
                "source": "pumpfun_gtfa_census",
                "pool_address": "curve-a",
                "venue": "pumpfun",
                "launch_timestamp_source": "verified_pair_creation",
                "launch_timestamp_confidence": 90,
                "launch_timestamp_verified": True,
                "metadata_json": {},
            }
        ],
    )
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {"token_mint": "mint-a", "launch_age_seconds": 30, "metadata_json": {"event_count": 1, "priced_event_count": 1}},
            {"token_mint": "mint-a", "launch_age_seconds": 7200, "metadata_json": {"event_count": 1, "priced_event_count": 1}},
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "token_mint": "mint-a",
                "survived_120m": False,
                "no_future_liquidity": False,
                "metadata_json": {"priced_event_count": 2, "market_cap_available": False},
            }
        ],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {"token_mint": "mint-a", "block_time": 1030, "venue": "unknown_token_swap_candidate", "metadata_json": {}},
            {"token_mint": "mint-a", "block_time": 8200, "venue": "unknown_token_swap_candidate", "metadata_json": {}},
        ],
    )

    report = run_launch_lifecycle_quality_audit(
        launches_path=launches_path,
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        events_path=events_path,
        output_dir=tmp_path / "reports",
    )

    assert report["launch_count"] == 1
    assert report["snapshot_count"] == 2
    assert report["outcome_count"] == 1
    assert report["event_count"] == 2
    assert report["event_venue_counts"] == {"unknown_token_swap_candidate": 2}
    assert report["unique_event_mints"] == 1
    assert report["priced_snapshot_count"] == 2
    assert report["market_cap_unknown_outcome_count"] == 1
    assert report["event_max_age_bucket_counts"]["gte_120m"] == 1
    assert "unknown_event_venue_dominant" in report["warning_flags"]
    assert "market_cap_unavailable_for_threshold_outcomes" in report["warning_flags"]
    assert (tmp_path / "reports" / "launch_lifecycle_quality_audit.json").exists()
    assert (tmp_path / "reports" / "launch_lifecycle_quality_audit.md").exists()


def test_lifecycle_quality_audit_cli_runs(tmp_path: Path) -> None:
    launches_path = _write_jsonl(
        tmp_path / "launches.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_ts": 1000,
                "launch_time_utc": "1970-01-01T00:16:40+00:00",
                "launch_weekday": "Monday",
                "launch_hour_local": 6,
                "launch_minute_local": 0,
                "launch_day_of_week": 0,
                "launch_is_weekend": False,
                "launch_regime": "mon_tue_wed_0600_1200_pt",
                "source": "pumpfun_gtfa_census",
                "venue": "pumpfun",
                "metadata_json": {},
            }
        ],
    )
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", [])
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [])

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_launch_lifecycle_quality_audit",
            "--launches-path",
            str(launches_path),
            "--snapshots-path",
            str(snapshots_path),
            "--outcomes-path",
            str(outcomes_path),
            "--events-path",
            str(events_path),
            "--output-dir",
            str(tmp_path / "reports"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "launch_count=1" in result.stdout
    assert "network_calls=0" in result.stdout
