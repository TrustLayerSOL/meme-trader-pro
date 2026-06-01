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
            {
                "token_mint": "mint-a",
                "launch_age_seconds": 30,
                "liquidity_proxy": 2.5,
                "true_market_cap_available": False,
                "fdv_available": False,
                "valuation_proxy_available": False,
                "bonding_curve_liquidity_proxy_available": True,
                "threshold_outcomes_usable": False,
                "price_sol_available": False,
                "price_usd_available": False,
                "supply_available": False,
                "sol_usd_available": False,
                "valuation_missing_reason": "missing_supply_and_price",
                "threshold_outcomes_missing_reason": "usd_valuation_unavailable",
                "metadata_json": {
                    "event_count": 1,
                    "priced_event_count": 1,
                    "liquidity_proxy_source": "bonding_curve_post_balance",
                },
            },
            {
                "token_mint": "mint-a",
                "launch_age_seconds": 7200,
                "liquidity_proxy": 2.8,
                "true_market_cap_available": False,
                "fdv_available": False,
                "valuation_proxy_available": False,
                "bonding_curve_liquidity_proxy_available": True,
                "threshold_outcomes_usable": False,
                "price_sol_available": False,
                "price_usd_available": False,
                "supply_available": False,
                "sol_usd_available": False,
                "valuation_missing_reason": "missing_supply_and_price",
                "threshold_outcomes_missing_reason": "usd_valuation_unavailable",
                "metadata_json": {
                    "event_count": 1,
                    "priced_event_count": 1,
                    "liquidity_proxy_source": "bonding_curve_post_balance",
                },
            },
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "token_mint": "mint-a",
                "survived_120m": False,
                "no_future_liquidity": False,
                "has_liquidity_proxy_at_120m": True,
                "true_market_cap_available": False,
                "fdv_available": False,
                "valuation_proxy_available": False,
                "bonding_curve_liquidity_proxy_available": True,
                "threshold_outcomes_usable": False,
                "price_sol_available": False,
                "price_usd_available": False,
                "supply_available": False,
                "sol_usd_available": False,
                "valuation_missing_reason": "missing_supply_and_price",
                "threshold_outcomes_missing_reason": "usd_valuation_unavailable",
                "metadata_json": {
                    "priced_event_count": 2,
                    "market_cap_available": False,
                    "liquidity_proxy_at_120m": 2.8,
                    "liquidity_proxy_source_120m": "bonding_curve_post_balance",
                },
            }
        ],
    )
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "token_mint": "mint-a",
                "block_time": 1030,
                "signature": "sig-a",
                "venue": "pumpfun_buy",
                "metadata_json": {"venue_matched_program_ids": ["pumpfun-program"]},
            },
            {
                "token_mint": "mint-a",
                "block_time": 8200,
                "signature": "sig-b",
                "venue": "unknown_token_swap_candidate",
                "metadata_json": {"venue_matched_program_ids": ["pumpfun-program"]},
            },
        ],
    )
    raw_path = _write_jsonl(
        tmp_path / "raw.jsonl",
        [
            {
                "signature": "sig-b",
                "raw_json": {
                    "transaction": {
                        "message": {
                            "instructions": [
                                {"programId": "pumpfun-program", "accounts": ["a", "b"], "data": "abcdef123456"}
                            ]
                        }
                    },
                    "meta": {"logMessages": ["Program log: Instruction: UnknownNewInstruction"]},
                },
            }
        ],
    )

    report = run_launch_lifecycle_quality_audit(
        launches_path=launches_path,
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        events_path=events_path,
        raw_path=raw_path,
        output_dir=tmp_path / "reports",
    )

    assert report["launch_count"] == 1
    assert report["snapshot_count"] == 2
    assert report["outcome_count"] == 1
    assert report["event_count"] == 2
    assert report["event_venue_counts"] == {"pumpfun_buy": 1, "unknown_token_swap_candidate": 1}
    assert report["event_classification_counts"] == {"pumpfun_buy": 1, "unknown_token_swap_candidate": 1}
    assert report["program_id_counts"] == {"pumpfun-program": 2}
    assert report["per_launch_event_classification_coverage"]["launches_with_known_classification"] == 1
    assert report["top_unknown_instruction_clusters"][0]["program_id"] == "pumpfun-program"
    assert report["unique_event_mints"] == 1
    assert report["priced_snapshot_count"] == 2
    assert report["liquidity_proxy_snapshot_count"] == 2
    assert report["liquidity_proxy_outcome_count"] == 1
    assert report["liquidity_proxy_source_counts"] == {"bonding_curve_post_balance": 3}
    assert report["true_market_cap_available_count"] == 0
    assert report["fdv_available_count"] == 0
    assert report["valuation_proxy_available_count"] == 0
    assert report["bonding_curve_liquidity_proxy_available_count"] == 3
    assert report["threshold_outcomes_usable_count"] == 0
    assert report["valuation_missing_reason_counts"] == {"missing_supply_and_price": 3}
    assert report["threshold_outcomes_missing_reason_counts"] == {"usd_valuation_unavailable": 3}
    assert report["sol_usd_available_count"] == 0
    assert report["supply_available_count"] == 0
    assert report["price_usd_available_count"] == 0
    assert report["market_cap_unknown_outcome_count"] == 1
    assert report["event_max_age_bucket_counts"]["gte_120m"] == 1
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


def test_lifecycle_quality_audit_skips_raw_context_when_no_unknown_events(tmp_path: Path) -> None:
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
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "token_mint": "mint-a",
                "signature": "sig-a",
                "venue": "pumpfun_swap",
                "metadata_json": {"venue_matched_program_ids": ["pumpfun-program"]},
            }
        ],
    )
    invalid_raw_path = tmp_path / "raw.jsonl"
    invalid_raw_path.write_text("{not-json}\n", encoding="utf-8")

    report = run_launch_lifecycle_quality_audit(
        launches_path=launches_path,
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        events_path=events_path,
        raw_path=invalid_raw_path,
        output_dir=tmp_path / "reports",
    )

    assert report["event_classification_counts"] == {"pumpfun_swap": 1}
    assert report["top_unknown_instruction_clusters"] == []
