import json
from pathlib import Path

from research.mtp_research.validation.structural_wallet_anatomy_report import (
    build_structural_wallet_anatomy_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, ts: int, age: int, value: float, creator: str, buys: int = 4, active: int = 4) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "mint": mint,
        "creator": creator,
        "launch_ts": ts,
        "snapshot_ts": ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": 1,
        "active_wallets": active,
        "unique_actors": active,
        "tx_count": buys + 1,
        "metadata_json": {"event_count": buys + 1},
    }


def test_structural_report_audits_field_availability_and_guardrails(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000, "creator-a"),
            _snapshot("mint-a", 1_700_000_000, 120, 600_000, "creator-a"),
            _snapshot("mint-b", 1_700_086_400, 60, 20_000, "creator-b"),
            _snapshot("mint-b", 1_700_086_400, 120, 40_000, "creator-b"),
        ],
    )
    holder = _write_jsonl(
        tmp_path / "holder.jsonl",
        [
            {
                "mint": "mint-a",
                "snapshot_age_seconds": 60,
                "holder_count": 10,
                "top_holder_share": 0.35,
                "top_10_holder_share": 0.72,
                "creator_holder_share": 0.08,
                "is_confirmed_full_chain_snapshot": False,
            }
        ],
    )
    entity = _write_jsonl(
        tmp_path / "entity.jsonl",
        [
            {
                "mint": "mint-a",
                "repeated_buyer_overlap_proxy": 0.4,
                "repeated_actor_overlap_proxy": 0.2,
                "synchronized_participation_proxy": 0.1,
                "circularity_proxy": 0.0,
                "churn_proxy": 0.3,
                "creator_linked_share_proxy": 0.12,
            }
        ],
    )

    report, paths = build_structural_wallet_anatomy_report(
        snapshot_paths=[snapshots],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STRUCTURAL_STATUS.md",
        holder_state_snapshots_path=holder,
        entity_proxy_path=entity,
        migration_labels_path=None,
        funding_link_path=None,
        event_paths=[],
    )

    assert report["report_id"] == "structural_wallet_anatomy_report_v0"
    assert report["coverage_report"]["total_launches"] == 2
    assert report["field_availability"]["launch_identity"]["creator"]["status"] == "available_now"
    assert report["field_availability"]["holder_state"]["top_holder_addresses"]["status"] == "unavailable"
    assert report["milestone_tier_summary"]["reached_500k_but_never_1m"]["launch_count"] == 1
    assert report["milestone_tier_summary"]["reached_20k_but_never_50k"]["launch_count"] == 1
    forbidden = " ".join(json.dumps(report).lower().split())
    assert "insider" not in forbidden
    assert "manipulator" not in forbidden
    assert "wash trader" not in forbidden
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_trading_logic" in report["methodology_flags"]
    assert paths["structural_feature_feasibility_path"].exists()
    assert paths["status_path"].exists()


def test_structural_report_separates_entry_exit_and_data_gaps(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000, "creator-a"),
            _snapshot("mint-a", 1_700_000_000, 180, 100_000, "creator-a"),
            _snapshot("mint-c", 1_700_172_800, 60, 12_000, "creator-c"),
        ],
    )

    report, paths = build_structural_wallet_anatomy_report(
        snapshot_paths=[snapshots],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STRUCTURAL_STATUS.md",
        holder_state_snapshots_path=None,
        entity_proxy_path=None,
        migration_labels_path=None,
        funding_link_path=None,
        event_paths=[],
    )

    entry_names = {row["feature_name"] for row in report["entry_exit_feature_separation"] if row["feature_side"] == "entry_side"}
    exit_names = {row["feature_name"] for row in report["entry_exit_feature_separation"] if row["feature_side"] == "exit_side"}
    gap_names = {row["missing_feature"] for row in report["data_gap_plan"]}

    assert "fdv_per_event_at_20k" in entry_names
    assert "top_holder_share_drop_after_20k" in exit_names
    assert "top_holder_addresses" in gap_names
    assert all("priority" in row and "source_needed" in row for row in report["data_gap_plan"])
    assert paths["entry_vs_exit_structural_features_path"].exists()
    assert paths["structural_data_gap_plan_path"].exists()


def test_structural_report_is_deterministic(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000, "creator-a"),
            _snapshot("mint-a", 1_700_000_000, 120, 1_200_000, "creator-a"),
            _snapshot("mint-b", 1_700_086_400, 60, 20_000, "creator-b"),
            _snapshot("mint-b", 1_700_086_400, 120, 30_000, "creator-b"),
        ],
    )

    first, _ = build_structural_wallet_anatomy_report(
        snapshot_paths=[snapshots],
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
        event_paths=[],
    )
    second, _ = build_structural_wallet_anatomy_report(
        snapshot_paths=[snapshots],
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
        event_paths=[],
    )

    assert first["milestone_tier_summary"] == second["milestone_tier_summary"]
    assert first["feature_family_feasibility"] == second["feature_family_feasibility"]
