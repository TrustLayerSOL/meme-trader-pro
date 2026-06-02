import json
from pathlib import Path

from research.mtp_research.validation.explosive_runner_raw_flow_thesis import (
    build_t011_explosive_runner_raw_flow_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, value: float, buys: int, sells: int, active: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1_000,
        "snapshot_ts": 1_000 + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": sells,
        "active_wallets": active,
        "unique_actors": active,
        "tx_count": buys + sells,
        "metadata_json": {"event_count": buys + sells},
    }


def _holder(mint: str, age: int, holders: int, top: float = 0.4) -> dict:
    return {
        "mint": mint,
        "token_mint": mint,
        "snapshot_age_seconds": age,
        "holder_count": holders,
        "top_holder_share": top,
        "top_10_holder_share": min(1.0, top + 0.3),
        "creator_holder_share": 0.1,
        "holder_snapshot_source": "observed_delta_replay",
    }


def test_t011_uses_first_20k_crossing_and_no_future_features(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("winner", 30, 10_000, buys=2, sells=1, active=2),
        _snapshot("winner", 60, 20_000, buys=4, sells=1, active=4),
        _snapshot("winner", 120, 100_000, buys=99, sells=1, active=99),
        _snapshot("stall", 30, 10_000, buys=3, sells=1, active=3),
        _snapshot("stall", 60, 20_000, buys=5, sells=2, active=4),
        _snapshot("stall", 120, 30_000, buys=7, sells=4, active=5),
    ]
    report = build_t011_explosive_runner_raw_flow_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    rows = {row["token_mint"]: row for row in report["trigger_rows"]}

    assert report["trigger_summary"]["trigger_20k_count"] == 2
    assert rows["winner"]["trigger_age_seconds"] == 60
    assert rows["winner"]["features"]["buy_count_at_20k"] == 4
    assert rows["winner"]["features"]["active_wallets_at_20k"] == 4
    assert rows["winner"]["features"]["fdv_per_event_at_20k"] == 4_000
    assert rows["winner"]["features"]["fdv_per_buy_at_20k"] == 5_000
    assert rows["winner"]["features"]["event_count_growth_before_20k"] == 2
    assert rows["winner"]["outcomes"]["crossed_100k_after_20k"] is True
    assert rows["stall"]["outcomes"]["reached_20k_but_never_50k"] is True
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_t011_merges_holder_entity_and_funding_overlays(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 12_000, buys=2, sells=1, active=2),
        _snapshot("mint-a", 60, 20_000, buys=5, sells=1, active=4),
        _snapshot("mint-a", 120, 500_000, buys=6, sells=1, active=5),
    ]
    holders = [_holder("mint-a", 60, holders=40, top=0.25)]
    entity = [
        {
            "token_mint": "mint-a",
            "repeated_actor_overlap_proxy": 0.2,
            "repeated_buyer_overlap_proxy": 0.1,
            "synchronized_participation_proxy": 0.3,
            "circularity_proxy": 0.0,
            "churn_proxy": 0.4,
        }
    ]
    funding = [
        {
            "token_mint": "mint-a",
            "candidate_funding_wallet": "funder-a",
            "launches_sharing_funder": 2,
        }
    ]
    report = build_t011_explosive_runner_raw_flow_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holders.jsonl", holders),
        entity_proxy_path=_write_jsonl(tmp_path / "entity.jsonl", entity),
        funding_link_path=_write_jsonl(tmp_path / "funding.jsonl", funding),
    )
    features = report["trigger_rows"][0]["features"]

    assert features["holder_count_at_20k"] == 40
    assert features["top_holder_share_at_20k"] == 0.25
    assert features["repeated_actor_overlap_proxy"] == 0.2
    assert features["funding_source_available"] is True
    assert features["repeated_funder_flag"] is True
    assert report["feature_coverage_audit"]["holder_count_at_20k"]["source_type"] == "observed_delta_replay"


def test_t011_classification_is_data_limited_for_tiny_samples(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 60, 20_000, buys=3, sells=1, active=3),
        _snapshot("mint-a", 120, 40_000, buys=4, sells=2, active=4),
    ]
    report = build_t011_explosive_runner_raw_flow_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )

    assert report["final_classification"] == "data_limited"
    assert report["robustness_checks"]["chronological_halves"]["available"] is False
    assert "no_trading_rules" in report["methodology_flags"]
