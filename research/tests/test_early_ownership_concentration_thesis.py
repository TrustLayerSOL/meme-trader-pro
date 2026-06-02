import json
from pathlib import Path

from research.mtp_research.validation.early_ownership_concentration_thesis import (
    DEFAULT_REQUIRED_FEATURES,
    build_t001_early_ownership_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int = 1000, creator: str = "creator-1") -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "launch_regime": "mon_tue_wed_0600_1200_pt",
        "metadata_json": {"creator_deployer": creator},
    }


def _event(
    mint: str,
    actor: str,
    block_time: int,
    qty: float,
    venue: str = "pumpfun_buy",
) -> dict:
    return {
        "token_mint": mint,
        "actor": actor,
        "block_time": block_time,
        "base_qty": qty,
        "venue": venue,
        "signature": f"sig-{mint}-{actor}-{block_time}",
    }


def _snapshot(mint: str, age: int, value: float) -> dict:
    return {
        "token_mint": mint,
        "launch_id": f"launch-{mint}",
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
    }


def _outcome(mint: str) -> dict:
    return {
        "token_mint": mint,
        "launch_id": f"launch-{mint}",
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "proxy_threshold_outcomes_usable": True,
    }


def _holder_state(mint: str, age: int, top_share: float, creator_share: float) -> dict:
    return {
        "mint": mint,
        "launch_id": f"launch-{mint}",
        "snapshot_age_seconds": age,
        "holder_count": 3,
        "top_holder_share": top_share,
        "top_10_holder_share": 1.0,
        "creator_holder_share": creator_share,
        "holder_snapshot_confidence": "medium",
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
    }


def test_builds_ownership_features_without_future_leakage(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            _event("mint-a", "buyer-1", 1010, 90),
            _event("mint-a", "buyer-2", 1020, 10),
            _event("mint-a", "future-whale", 2000, 10000),
        ],
    )
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [_snapshot("mint-a", 30, 1000), _snapshot("mint-a", 120, 2000)],
    )
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")])

    report = build_t001_early_ownership_report(
        candidates_path=candidates_path,
        events_path=events_path,
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
        bucket_count=5,
        observation_window_seconds=120,
    )

    row = report["launch_rows"][0]
    assert row["features"]["first_10_buyer_share"] == 0.9
    assert row["features"]["first_20_buyer_share"] == 0.9
    assert row["outcomes"]["fdv_proxy_runup_120m"] == 1.0
    assert row["metadata_json"]["max_feature_event_block_time"] == 1020
    assert "future-whale" not in row["metadata_json"]["feature_actor_sample"]


def test_missing_holder_and_label_features_remain_audited_missing(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "buyer-1", 1010, 1)])
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", [_snapshot("mint-a", 30, 1000)])
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")])

    report = build_t001_early_ownership_report(
        candidates_path=candidates_path,
        events_path=events_path,
        snapshots_path=snapshots_path,
        outcomes_path=outcomes_path,
    )

    for feature in ("insider_share", "bundler_share", "top_holder_share"):
        assert feature in DEFAULT_REQUIRED_FEATURES
        assert report["missing_value_audit"][feature]["missing_count"] == 1
    assert "missing_holder_state_features" in report["warning_flags"]


def test_holder_state_v2_supplies_top_holder_and_creator_share_without_future_leakage(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")])
    events_path = _write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "buyer-1", 1010, 1)])
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", [_snapshot("mint-a", 30, 1000), _snapshot("mint-a", 120, 1500)])
    holder_state_path = _write_jsonl(
        tmp_path / "holder_state.jsonl",
        [
            _holder_state("mint-a", 30, 0.7, 0.2),
            _holder_state("mint-a", 7200, 0.99, 0.8),
        ],
    )
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")])

    report = build_t001_early_ownership_report(
        candidates_path=candidates_path,
        events_path=events_path,
        snapshots_path=snapshots_path,
        holder_state_snapshots_path=holder_state_path,
        outcomes_path=outcomes_path,
    )
    row = report["launch_rows"][0]

    assert row["features"]["top_holder_share"] == 0.7
    assert row["features"]["creator_share"] == 0.2
    assert row["metadata_json"]["holder_state_snapshot_age_seconds"] == 30
    assert report["missing_value_audit"]["top_holder_share"]["available_count"] == 1
    assert "missing_holder_state_features" not in report["warning_flags"]
    assert "holder_state_observed_delta_replay_not_full_chain_state" in report["methodology_flags"]


def test_quantile_report_is_deterministic_and_uses_allowed_classification(tmp_path: Path) -> None:
    launches = [_candidate(f"mint-{i}", launch_ts=1000 + i) for i in range(10)]
    events = []
    snapshots = []
    outcomes = []
    for i in range(10):
        mint = f"mint-{i}"
        events.append(_event(mint, f"buyer-{i}", 1001 + i, i + 1))
        events.append(_event(mint, f"other-{i}", 1002 + i, 10 - i))
        snapshots.append(_snapshot(mint, 30, 1000))
        snapshots.append(_snapshot(mint, 120, 1000 + (i * 100)))
        outcomes.append(_outcome(mint))
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", launches),
        "events_path": _write_jsonl(tmp_path / "events.jsonl", events),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t001_early_ownership_report(**paths, bucket_count=5)
    second = build_t001_early_ownership_report(**paths, bucket_count=5)

    assert first["feature_reports"]["first_10_buyer_share"] == second["feature_reports"]["first_10_buyer_share"]
    assert len(first["feature_reports"]["first_10_buyer_share"]["bucket_tables"]) == 5
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_threshold_optimization" in first["methodology_flags"]
    assert "no_future_leakage" in first["methodology_flags"]
