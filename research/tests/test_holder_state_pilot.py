import json
from pathlib import Path

from research.mtp_research.validation.holder_state_pilot import (
    HOLDER_SNAPSHOT_AGES,
    build_holder_state_pilot_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int = 1000) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "launch_time_utc": "2026-01-01T00:00:00+00:00",
        "launch_weekday": "Thursday",
        "launch_hour_local": 0,
        "launch_minute_local": 0,
        "launch_day_of_week": 3,
        "launch_is_weekend": False,
        "launch_regime": "test",
        "source": "test",
        "pool_address": f"pool-{mint}",
        "venue": "pumpfun",
        "metadata_json": {},
    }


def _event(mint: str, actor: str, block_time: int, side: str, qty: float) -> dict:
    return {
        "event_id": f"{mint}-{actor}-{block_time}-{side}",
        "signature": f"sig-{mint}-{actor}-{block_time}-{side}",
        "slot": block_time,
        "block_time": block_time,
        "event_type": "possible_buy" if side in {"buy", "accumulate"} else "possible_sell",
        "token_mint": mint,
        "venue": "pumpfun",
        "actor": actor,
        "side": side,
        "base_qty": qty,
        "quote_qty": 1,
        "price_quote": 1,
        "source": "test",
        "metadata_json": {"confidence": 0.7},
    }


def test_holder_state_pilot_replays_event_deltas_deterministically(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            _event("mint-a", "wallet-a", 1010, "accumulate", 60),
            _event("mint-a", "wallet-b", 1020, "buy", 40),
            _event("mint-a", "wallet-a", 1170, "sell", 10),
            _event("mint-a", "wallet-c", 1600, "buy", 25),
        ],
    )

    report = build_holder_state_pilot_report(
        candidates_path=candidates_path,
        events_path=events_path,
        launch_limit=1,
    )
    first = report["holder_snapshots"][0]
    three_minute = next(row for row in report["holder_snapshots"] if row["launch_age_seconds"] == 180)

    assert len(report["holder_snapshots"]) == len(HOLDER_SNAPSHOT_AGES)
    assert first["holder_count"] == 2
    assert first["top_holder_share"] == 0.6
    assert first["top_10_holder_share"] == 1.0
    assert first["holder_distribution_source"] == "offline_normalized_event_delta_replay_v0"
    assert three_minute["holder_count"] == 2
    assert three_minute["top_holder_share"] == 50 / 90
    assert three_minute["holder_retention_proxy"] == 1.0
    assert report["api_calls_used"] == 0
    assert report["feasibility_result"] == "feasible_offline"


def test_holder_state_pilot_caps_launches_and_snapshot_attempts(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(f"mint-{idx}") for idx in range(60)])
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [_event(f"mint-{idx}", "wallet-a", 1010, "buy", 1) for idx in range(60)],
    )

    report = build_holder_state_pilot_report(
        candidates_path=candidates_path,
        events_path=events_path,
        launch_limit=500,
    )

    assert report["launches_attempted"] == 50
    assert report["snapshots_attempted"] == 250
    assert report["hard_limits"]["max_launches"] == 50
    assert report["hard_limits"]["max_holder_snapshots"] == 250


def test_holder_state_pilot_marks_missing_without_fabricating_state(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [])

    report = build_holder_state_pilot_report(
        candidates_path=candidates_path,
        events_path=events_path,
        launch_limit=1,
    )

    assert report["snapshots_built"] == 0
    assert report["missing_snapshots"] == 5
    assert report["holder_count_coverage_pct"] == 0
    assert report["holder_snapshots"][0]["holder_count"] is None
    assert report["holder_snapshots"][0]["holder_snapshot_missing_reason"] == "no_observed_holder_balances_at_snapshot"
    assert report["feasibility_result"] == "blocked"
    assert report["api_requirements"]["estimated_historical_holder_snapshots_for_1500_launches"] == 7500
