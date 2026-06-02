import csv
import json
from pathlib import Path

from research.mtp_research.validation.p0_structural_proxy_audit import (
    build_p0_structural_proxy_audit,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _fixture_paths(tmp_path: Path) -> dict[str, Path]:
    launch_rows = [
        {"launch_id": "launch-a", "mint": "mint-a", "launch_ts": 1000, "milestone_tier": "reached_100k_but_never_200k"},
        {"launch_id": "launch-b", "mint": "mint-b", "launch_ts": 1100, "milestone_tier": "reached_500k_but_never_1m"},
        {"launch_id": "launch-c", "mint": "mint-c", "launch_ts": 1200, "milestone_tier": "reached_1m_plus"},
        {"launch_id": "launch-d", "mint": "mint-d", "launch_ts": 1300, "milestone_tier": "never_reached_20k"},
    ]
    universe = {
        "report_id": "fixture",
        "launch_feature_rows": launch_rows,
        "milestone_tier_summary": {
            "reached_100k_but_never_200k": {"launch_count": 1},
            "reached_500k_but_never_1m": {"launch_count": 1},
            "reached_1m_plus": {"launch_count": 1},
            "never_reached_20k": {"launch_count": 1},
        },
    }
    universe_path = tmp_path / "universe.json"
    universe_path.write_text(json.dumps(universe), encoding="utf-8")
    early = [
        {"current_launch_id": "launch-a", "current_mint": "mint-a", "wallet": "buyer-a1", "prior_transaction_count": 2, "history_missing_reason": None, "wallet_history_source_confidence": "medium"},
        {"current_launch_id": "launch-a", "current_mint": "mint-a", "wallet": "buyer-a2", "prior_transaction_count": 0, "history_missing_reason": "none", "wallet_history_source_confidence": "none"},
        {"current_launch_id": "launch-b", "current_mint": "mint-b", "wallet": "buyer-b1", "prior_transaction_count": 5, "history_missing_reason": None, "wallet_history_source_confidence": "medium"},
    ]
    top = [
        {"launch_id": "launch-a", "mint": "mint-a", "milestone": "100k", "top_holder_owner": "top-a", "top_holder_share_proxy": 0.42, "top_10_holder_share_proxy": 0.8, "holder_snapshot_confidence": "medium", "is_confirmed_full_chain_snapshot": False},
        {"launch_id": "launch-c", "mint": "mint-c", "milestone": "1m", "top_holder_owner": "top-c", "top_holder_share_proxy": 0.2, "top_10_holder_share_proxy": 0.6, "holder_snapshot_confidence": "medium", "is_confirmed_full_chain_snapshot": False},
    ]
    funder = [
        {"launch_id": "launch-a", "mint": "mint-a", "creator": "creator-a", "candidate_funder": "funder-a", "candidate_funder_confidence": "high", "shared_funding_proxy": True, "time_linked_funding_proxy": True, "launches_sharing_funder": 2, "creators_sharing_funder": 2, "common_funder_candidate_id": "funder-a", "creator_to_early_buyer_transfer_link_proxy": False, "creator_to_top_holder_transfer_link_proxy": False},
        {"launch_id": "launch-b", "mint": "mint-b", "creator": "creator-b", "candidate_funder": "funder-a", "candidate_funder_confidence": "high", "shared_funding_proxy": True, "time_linked_funding_proxy": True, "launches_sharing_funder": 2, "creators_sharing_funder": 2, "common_funder_candidate_id": "funder-a", "creator_to_early_buyer_transfer_link_proxy": False, "creator_to_top_holder_transfer_link_proxy": False},
    ]
    return {
        "universe_path": universe_path,
        "early_buyer_path": _write_jsonl(tmp_path / "early.jsonl", early),
        "top_holder_path": _write_jsonl(tmp_path / "top.jsonl", top),
        "creator_funder_path": _write_jsonl(tmp_path / "funder.jsonl", funder),
    }


def test_structural_proxy_audit_join_schema_and_outputs(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    report, outputs = build_p0_structural_proxy_audit(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "P0_STRUCTURAL_PROXY_AUDIT_STATUS.md",
        **paths,
    )

    preview = outputs["joined_preview_csv_path"]
    assert report["report_id"] == "p0_structural_proxy_audit_v0"
    assert report["readiness_classification"] == "p0_structural_layer_needs_scaleup"
    assert outputs["summary_json_path"].exists()
    assert outputs["summary_markdown_path"].exists()
    assert preview.exists()
    assert outputs["status_path"].exists()

    rows = list(csv.DictReader(preview.open(encoding="utf-8")))
    assert {"launch_id", "mint", "has_any_p0_structural_data", "has_all_three_p0_structural_layers"} <= set(rows[0])
    launch_a = next(row for row in rows if row["launch_id"] == "launch-a")
    assert launch_a["early_buyer_history_available"] == "True"
    assert launch_a["top_holder_replay_available"] == "True"
    assert launch_a["creator_funder_graph_available"] == "True"
    assert launch_a["full_chain_holder_snapshot_confirmed"] == "False"


def test_coverage_overlap_readiness_and_recommendation(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    report, outputs = build_p0_structural_proxy_audit(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
        **paths,
    )

    coverage = {row["milestone_tier"]: row for row in report["coverage_by_tier"]}
    overlap = report["overlap_audit"]
    readiness = report["structural_proxy_readiness"]

    assert coverage["reached_100k_but_never_200k"]["all_three_layers"] == 1
    assert overlap["launches_covered_by_all_three_pilots"] == 1
    assert overlap["runners_100k_plus_covered_by_all_three"] == 1
    assert overlap["runners_500k_plus_covered_by_all_three"] == 0
    assert overlap["runners_1m_plus_covered_by_all_three"] == 0
    assert overlap["failed_20k_triggers_covered_by_all_three"] == 0
    assert readiness["combined_p0_structural_proxy"]["classification"] == "pilot_only_needs_scale"
    assert report["scaleup_recommendation"]["selection"] == "D"
    assert outputs["coverage_by_tier_csv_path"].exists()
    assert outputs["overlap_csv_path"].exists()
    assert outputs["scaleup_recommendation_csv_path"].exists()


def test_structural_proxy_audit_guardrails_and_determinism(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    first, _ = build_p0_structural_proxy_audit(output_dir=tmp_path / "a", status_path=tmp_path / "A.md", **paths)
    second, _ = build_p0_structural_proxy_audit(output_dir=tmp_path / "b", status_path=tmp_path / "B.md", **paths)

    text = json.dumps(first).lower()
    assert "no_trading_logic" in first["methodology_flags"]
    assert "no_helius_calls" in first["methodology_flags"]
    assert "no_validation_run" in first["methodology_flags"]
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text
    assert first["joined_preview_rows"] == second["joined_preview_rows"]
    assert first["coverage_by_tier"] == second["coverage_by_tier"]
