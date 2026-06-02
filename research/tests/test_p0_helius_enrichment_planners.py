import csv
import json
from pathlib import Path

import pytest

from research.mtp_research.validation.p0_helius_enrichment_planners import (
    ExecuteRejectedError,
    build_p0_helius_enrichment_plans,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    launch_rows = [
        {
            "launch_id": "launch-a",
            "mint": "mint-a",
            "creator": "creator-a",
            "launch_ts": 1_700_000_000,
            "launch_date": "2023-11-14",
            "milestone_tier": "reached_1m_plus",
            "crossing_20k_age": 60,
            "crossing_50k_age": 90,
            "crossing_100k_age": 120,
            "crossing_500k_age": 180,
            "crossing_1m_age": 240,
        },
        {
            "launch_id": "launch-b",
            "mint": "mint-b",
            "creator": "creator-b",
            "launch_ts": 1_700_086_400,
            "launch_date": "2023-11-15",
            "milestone_tier": "reached_20k_but_never_50k",
            "crossing_20k_age": 70,
            "crossing_50k_age": None,
            "crossing_100k_age": None,
            "crossing_500k_age": None,
            "crossing_1m_age": None,
        },
        {
            "launch_id": "launch-c",
            "mint": "mint-c",
            "creator": "creator-a",
            "launch_ts": 1_700_172_800,
            "launch_date": "2023-11-16",
            "milestone_tier": "never_reached_20k",
            "crossing_20k_age": None,
            "crossing_50k_age": None,
            "crossing_100k_age": None,
            "crossing_500k_age": None,
            "crossing_1m_age": None,
        },
    ]
    events = [
        {"token_mint": "mint-a", "actor": "wallet-a", "block_time": 1_700_000_030, "side": "accumulate"},
        {"token_mint": "mint-a", "actor": "wallet-b", "block_time": 1_700_000_050, "side": "accumulate"},
        {"token_mint": "mint-b", "actor": "wallet-a", "block_time": 1_700_086_430, "side": "accumulate"},
    ]
    funding = [
        {
            "launch_id": "launch-a",
            "mint": "mint-a",
            "creator": "creator-a",
            "candidate_funding_wallet": "funder-a",
            "candidate_funding_signature": "sig-funding-a",
            "launches_sharing_funder": 2,
        }
    ]
    return {
        "master": _write_json(
            tmp_path / "master.json",
            {
                "helius_budget_plan": [
                    {"plan_id": "top_holder_milestone_snapshot_pilot", "estimated_credits": 20_000, "priority": "P0"},
                    {"plan_id": "early_buyer_wallet_history_pilot", "estimated_credits": 25_000, "priority": "P0"},
                    {"plan_id": "creator_funder_transfer_graph_pilot", "estimated_credits": 25_000, "priority": "P0"},
                ],
                "priority_rank": [{"priority": "P0", "data_family": "top_holder_structure"}],
            },
        ),
        "repeated": _write_json(tmp_path / "repeated.json", {"launch_feature_rows": launch_rows, "dataset": {"event_paths": []}}),
        "events": _write_jsonl(tmp_path / "events.jsonl", events),
        "funding": _write_jsonl(tmp_path / "funding.jsonl", funding),
    }


def test_dry_run_builds_all_planners_and_preview_tables(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, output_paths = build_p0_helius_enrichment_plans(
        master_plan_path=paths["master"],
        repeated_buyer_report_path=paths["repeated"],
        event_paths=[paths["events"]],
        funding_link_path=paths["funding"],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
        pilot="all",
        dry_run=True,
    )

    by_pilot = {row["pilot_id"]: row for row in report["pilot_plans"]}
    assert set(by_pilot) == {
        "top_holder_milestone_snapshot_pilot",
        "early_buyer_wallet_history_pilot",
        "creator_funder_transfer_graph_pilot",
    }
    assert by_pilot["top_holder_milestone_snapshot_pilot"]["readiness_classification"] == "planner_ready_for_review"
    assert by_pilot["early_buyer_wallet_history_pilot"]["target_counts"]["wallets_selected"] == 2
    assert by_pilot["creator_funder_transfer_graph_pilot"]["target_counts"]["candidate_funders_selected"] == 1
    assert report["overall_classification"] == "p0_helius_planners_ready_for_user_review"
    assert report["network_calls_made"] == 0
    assert output_paths["top_holder_targets_path"].exists()
    assert output_paths["budget_projection_path"].exists()


def test_execute_is_rejected_and_budget_caps_are_enforced(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    with pytest.raises(ExecuteRejectedError):
        build_p0_helius_enrichment_plans(
            master_plan_path=paths["master"],
            repeated_buyer_report_path=paths["repeated"],
            event_paths=[paths["events"]],
            funding_link_path=paths["funding"],
            output_dir=tmp_path / "reports",
            status_path=tmp_path / "STATUS.md",
            pilot="all",
            execute=True,
        )

    report, _ = build_p0_helius_enrichment_plans(
        master_plan_path=paths["master"],
        repeated_buyer_report_path=paths["repeated"],
        event_paths=[paths["events"]],
        funding_link_path=paths["funding"],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
        pilot="all",
        credit_cap_per_pilot=1,
        dry_run=True,
    )
    assert report["overall_classification"] == "p0_helius_planners_blocked"
    assert all(row["readiness_classification"] == "planner_blocked_budget" for row in report["pilot_plans"])


def test_target_selection_is_deterministic_and_uses_neutral_labels(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    first, _ = build_p0_helius_enrichment_plans(
        master_plan_path=paths["master"],
        repeated_buyer_report_path=paths["repeated"],
        event_paths=[paths["events"]],
        funding_link_path=paths["funding"],
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
        pilot="all",
        dry_run=True,
    )
    second, _ = build_p0_helius_enrichment_plans(
        master_plan_path=paths["master"],
        repeated_buyer_report_path=paths["repeated"],
        event_paths=[paths["events"]],
        funding_link_path=paths["funding"],
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
        pilot="all",
        dry_run=True,
    )

    assert first["pilot_plans"] == second["pilot_plans"]
    text = json.dumps(first).lower()
    assert "wallet_structure_proxy" in text
    assert "funder_link_proxy" in text
    assert "top_holder_behavior_proxy" in text
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text


def test_preview_csv_schema(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    _report, output_paths = build_p0_helius_enrichment_plans(
        master_plan_path=paths["master"],
        repeated_buyer_report_path=paths["repeated"],
        event_paths=[paths["events"]],
        funding_link_path=paths["funding"],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
        pilot="all",
        dry_run=True,
    )
    with output_paths["top_holder_targets_path"].open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert {"launch_id", "mint", "milestone", "milestone_time", "milestone_tier"} <= set(row)
    with output_paths["early_buyer_targets_path"].open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert {"wallet", "current_launch_id", "current_mint", "reason_selected"} <= set(row)
    with output_paths["creator_funder_targets_path"].open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert {"creator", "candidate_funder", "launch_id", "reason_selected"} <= set(row)
