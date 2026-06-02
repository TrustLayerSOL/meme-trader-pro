import json
from pathlib import Path

from research.mtp_research.validation.fast_broad_launch_quality_thesis import (
    build_t009_fast_broad_launch_quality_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, value: float, active: int, buys: int, creator: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "launch_ts": 1000 + int(mint.split("-")[-1]),
        "snapshot_ts": 1000 + age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": 1,
        "tx_count": buys + 1,
        "active_wallets": active,
        "unique_actors": active,
        "liquidity_proxy": 2.0,
        "metadata_json": {"event_count": buys + 1, "creator_deployer": creator},
    }


def _outcome(mint: str, runup: float, drawdown: float = -0.1) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "runups": {"max_runup_120m": runup},
        "drawdowns": {"max_drawdown_120m": drawdown},
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "true_market_cap_available": False,
    }


def test_builds_predefined_fast_broad_interaction_groups(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    for index in range(12):
        mint = f"mint-{index}"
        creator = "creator-a" if index < 6 else f"creator-{index}"
        speed = 1000 + index * 100
        breadth = 1 + index
        snapshots.extend(
            [
                _snapshot(mint, 30, speed * 0.8, breadth, breadth, creator),
                _snapshot(mint, 60, speed, breadth, breadth, creator),
                _snapshot(mint, 7200, speed * (1 + index / 10), breadth, breadth, creator),
            ]
        )
        outcomes.append(_outcome(mint, runup=index / 10))
    report = build_t009_fast_broad_launch_quality_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    )

    assert report["thesis_id"] == "T009"
    assert report["dataset"]["launch_count"] == 12
    assert report["selected_features"]["speed_feature_used"] == "valuation_proxy_usd_1m"
    assert report["selected_features"]["breadth_feature_used"] == "active_wallets_60s"
    assert "fast_and_broad" in report["interaction_groups"]["counts"]
    assert "fast_and_narrow" in report["interaction_groups"]["counts"]
    assert report["interaction_groups"]["counts"]["fast_and_broad"] > 0
    assert report["interaction_groups"]["counts"]["slow_and_narrow"] > 0
    assert report["main_comparisons"]["fast_and_broad_vs_fast_and_narrow"]["left_group"] == "fast_and_broad"
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_future_leakage" in report["methodology_flags"]
    assert report["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }


def test_uses_holder_and_entity_overlays_without_requiring_all_collected_coverage(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    holder_rows = []
    entity_rows = []
    for index in range(6):
        mint = f"mint-{index}"
        snapshots.extend(
            [
                _snapshot(mint, 60, 1000 + index * 10, 3 + index, 2 + index, f"creator-{index}"),
                _snapshot(mint, 7200, 1100 + index * 10, 3 + index, 2 + index, f"creator-{index}"),
            ]
        )
        outcomes.append(_outcome(mint, runup=0.2))
        if index < 3:
            holder_rows.append(
                {
                    "launch_id": f"launch-{mint}",
                    "mint": mint,
                    "snapshot_age_seconds": 30,
                    "holder_count": 3 + index,
                    "top_holder_share": 0.1 + index / 10,
                    "top_10_holder_share": 0.2 + index / 10,
                    "creator_holder_share": 0.05 + index / 10,
                    "holder_snapshot_confidence": "medium",
                    "is_observed_delta_replay": True,
                    "is_confirmed_full_chain_snapshot": False,
                }
            )
            entity_rows.append(
                {
                    "launch_id": f"launch-{mint}",
                    "mint": mint,
                    "repeated_actor_overlap_proxy": index,
                    "repeated_buyer_overlap_proxy": index,
                    "synchronized_participation_proxy": index / 10,
                    "circularity_proxy": index,
                    "churn_proxy": index / 10,
                    "creator_linked_share_proxy": index / 10,
                    "proxy_confidence": "medium",
                }
            )

    report = build_t009_fast_broad_launch_quality_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", holder_rows),
        entity_proxy_path=_write_jsonl(tmp_path / "entity.jsonl", entity_rows),
    )

    assert report["field_coverage_audit"]["top_holder_share_60s_or_nearest"]["available_rows"] == 3
    assert report["field_coverage_audit"]["repeated_actor_overlap_proxy"]["available_rows"] == 3
    assert "holder_state_observed_delta_replay_not_full_chain_state" in report["warning_flags"]
    assert report["secondary_concentration_overlay"]["high_speed_concentration_groups"]


def test_falls_back_to_event_count_speed_when_first_minute_fdv_missing(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    for index in range(6):
        mint = f"mint-{index}"
        row = _snapshot(mint, 60, 0, 2 + index, 3 + index, f"creator-{index}")
        row["valuation_proxy_available"] = False
        row["valuation_proxy_usd"] = None
        snapshots.append(row)
        outcomes.append(_outcome(mint, runup=0.1))

    report = build_t009_fast_broad_launch_quality_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    )

    assert report["selected_features"]["speed_feature_used"] == "event_count_60s"
    assert "primary_speed_fdv_unavailable_used_event_count_fallback" in report["warning_flags"]
