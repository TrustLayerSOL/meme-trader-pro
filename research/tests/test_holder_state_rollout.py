import json
from pathlib import Path

from research.mtp_research.validation.holder_state_rollout import (
    build_holder_state_rollout,
    write_holder_state_rollout_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int = 1000, creator: str = "creator-a") -> dict:
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
        "launch_regime": "strict",
        "source": "test",
        "pool_address": f"pool-{mint}",
        "venue": "pumpfun",
        "metadata_json": {"creator_deployer": creator},
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
        "source": "test",
        "metadata_json": {},
    }


def test_rollout_builds_five_snapshots_per_launch_with_required_schema(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a", creator="wallet-a")])
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            _event("mint-a", "wallet-a", 1010, "buy", 60),
            _event("mint-a", "wallet-b", 1020, "buy", 40),
            _event("mint-a", "wallet-a", 1200, "sell", 10),
        ],
    )

    rollout = build_holder_state_rollout(candidates_path=candidates_path, events_path=events_path)
    first = rollout["holder_snapshots"][0]

    assert rollout["launches_attempted"] == 1
    assert rollout["snapshots_expected"] == 5
    assert rollout["snapshots_built"] == 5
    assert first["mint"] == "mint-a"
    assert first["snapshot_label"] == "30s"
    assert first["snapshot_age_seconds"] == 30
    assert first["holder_count"] == 2
    assert first["top_holder_share"] == 0.6
    assert first["top_10_holder_share"] == 1.0
    assert first["creator_holder_share"] == 0.6
    assert first["observed_holder_balance_sum"] == 100
    assert first["is_observed_delta_replay"] is True
    assert first["is_confirmed_full_chain_snapshot"] is False
    assert rollout["readiness_classification"] == "holder_state_ready_for_T001_T002_v2"


def test_rollout_handles_negative_balance_without_silent_imputation(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "wallet-a", 1010, "sell", 10)])

    rollout = build_holder_state_rollout(candidates_path=candidates_path, events_path=events_path)

    assert rollout["snapshots_built"] == 0
    assert rollout["suspicious_negative_balance_count"] == 1
    assert rollout["readiness_classification"] == "holder_state_blocked"
    assert rollout["holder_snapshots"][0]["holder_snapshot_missing_reason"] == "no_observed_holder_balances_at_snapshot"


def test_rollout_outputs_are_deterministic_and_writes_jsonl_and_parquet(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "creator-a", 1010, "buy", 10)])

    first = build_holder_state_rollout(candidates_path=candidates_path, events_path=events_path)
    second = build_holder_state_rollout(candidates_path=candidates_path, events_path=events_path)
    paths = write_holder_state_rollout_outputs(
        first,
        dataset_dir=tmp_path / "holder_state",
        report_dir=tmp_path / "reports",
    )

    assert first["holder_snapshots"] == second["holder_snapshots"]
    assert paths["jsonl_path"].exists()
    assert paths["parquet_path"].exists()
    assert paths["audit_json_path"].exists()
    assert paths["audit_markdown_path"].exists()
    assert "full-chain" in paths["audit_markdown_path"].read_text(encoding="utf-8")
