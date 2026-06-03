import csv
import json
from pathlib import Path

from research.mtp_research.validation.combined_p0_fingerprint_selection_design import (
    build_combined_p0_fingerprint_selection_design,
    classify_feature_direction,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _structural_row(launch_id: str, tier: str, *, balanced: bool = True, leftover: bool = False) -> dict:
    return {
        "launch_id": launch_id,
        "mint": f"mint-{launch_id}",
        "creator": f"creator-{launch_id}",
        "milestone_tier": tier,
        "is_balanced_sample": balanced,
        "is_leftover_sample": leftover,
        "fdv_per_event_at_20k": 10.0 if tier == "reached_1m_plus" else 2.0,
        "fdv_per_buy_at_20k": 8.0 if tier == "reached_1m_plus" else 1.5,
        "fdv_per_active_wallet_at_20k": 6.0 if tier == "reached_1m_plus" else 2.0,
        "active_wallets_at_20k": 3.0,
        "event_count_at_20k": 2.0,
        "buy_count_at_20k": 2.0,
        "sell_count_at_20k": 1.0,
        "buy_sell_ratio_at_20k": 2.0,
        "repeated_buyer_quality_proxy": 0.9 if tier == "reached_1m_plus" else 0.4,
        "early_buyer_with_prior_runner_count": 3.0 if tier == "reached_1m_plus" else 1.0,
        "early_buyer_prior_failure_count": 0.0 if tier == "reached_1m_plus" else 2.0,
        "top_holder_share_proxy": 0.95 if tier == "reached_1m_plus" else 0.7,
        "top_10_holder_share_proxy": 1.0,
        "launches_sharing_funder": 0.0 if tier == "reached_1m_plus" else 3.0,
        "creators_sharing_funder": 0.0 if tier == "reached_1m_plus" else 2.0,
        "shared_funding_proxy": False if tier == "reached_1m_plus" else True,
        "time_linked_funding_proxy": False if tier == "reached_1m_plus" else True,
        "has_all_three_p0_layers": True,
    }


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    summary = _write_json(
        tmp_path / "summary.json",
        {
            "report_id": "combined_aligned_p0_fingerprint_report_v0",
            "readiness_classification": "combined_p0_fingerprint_ready_for_formal_thesis_selection",
            "coverage_audit": {
                "total_unique_launches": 4,
                "all_three_p0_launches": 4,
                "balanced_sample_rows": 3,
                "leftover_sample_rows": 1,
            },
            "milestone_tier_counts": {"reached_20k_but_never_50k": 2, "reached_1m_plus": 2},
        },
    )
    tier = _write_csv(
        tmp_path / "tier.csv",
        [
            {
                "evidence_subset": subset,
                "feature": feature,
                "milestone_tier": tier_name,
                "sample_count": 2,
                "median": median,
                "coverage_pct": 100,
            }
            for subset in ("balanced_sample", "leftover_sample", "combined_sample")
            for feature, high, low in (
                ("fdv_per_event_at_20k", 10, 2),
                ("repeated_buyer_quality_proxy", 0.9, 0.4),
                ("launches_sharing_funder", 0, 3),
                ("active_wallets_at_20k", 3, 3),
            )
            for tier_name, median in (
                ("reached_1m_plus", high),
                ("reached_20k_but_never_50k", low),
            )
        ],
    )
    entry_exit = _write_csv(
        tmp_path / "entry_exit.csv",
        [
            {"feature_name": "fdv_per_event_at_20k", "feature_side": "entry_side", "available_now": True},
            {"feature_name": "repeated_buyer_quality_proxy", "feature_side": "entry_side", "available_now": True},
        ],
    )
    candidate = _write_csv(
        tmp_path / "candidate.csv",
        [{"name": "concept only", "sample_support": 0, "visible_features": "fdv_per_event_at_20k"}],
    )
    dataset = _write_jsonl(
        tmp_path / "combined.jsonl",
        [
            _structural_row("a", "reached_1m_plus", balanced=True),
            _structural_row("b", "reached_1m_plus", balanced=False, leftover=True),
            _structural_row("c", "reached_20k_but_never_50k", balanced=True),
            _structural_row("d", "reached_20k_but_never_50k", balanced=True),
        ],
    )
    return {
        "summary_path": summary,
        "tier_feature_comparison_path": tier,
        "entry_vs_exit_features_path": entry_exit,
        "candidate_fingerprints_path": candidate,
        "combined_dataset_path": dataset,
    }


def test_classifies_feature_directions() -> None:
    assert classify_feature_direction(10, 2) == "higher_in_higher_tiers"
    assert classify_feature_direction(2, 10) == "lower_in_higher_tiers"
    assert classify_feature_direction(3, 3) == "flat_or_not_useful"
    assert classify_feature_direction(None, 3) == "coverage_limited"


def test_selection_design_loads_artifacts_and_writes_schema(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    report, output_paths = build_combined_p0_fingerprint_selection_design(
        **paths,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["source_report_confirmation"]["unique_launch_count"] == 4
    assert report["source_report_confirmation"]["all_three_p0_row_count"] == 4
    assert report["readiness_classification"] in {
        "fingerprint_selection_ready_for_formal_thesis",
        "fingerprint_selection_needs_support_audit",
        "fingerprint_selection_needs_enrichment",
        "fingerprint_selection_inconclusive",
    }
    assert len(report["selected_candidate_fingerprints"]) in {2, 3}
    for fingerprint in report["selected_candidate_fingerprints"]:
        assert {
            "fingerprint_id",
            "fingerprint_name",
            "visible_features",
            "hidden_structural_features",
            "expected_directions",
            "balanced_sample_support",
            "leftover_sample_support",
            "formal_thesis_recommendation",
        } <= set(fingerprint)
    assert report["thesis_design_stubs"]
    assert output_paths["summary_json_path"].exists()
    assert output_paths["selection_table_path"].exists()
    assert output_paths["thesis_design_stubs_path"].exists()


def test_selection_design_guardrails_and_determinism(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    first, _ = build_combined_p0_fingerprint_selection_design(
        **paths,
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_combined_p0_fingerprint_selection_design(
        **paths,
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["selected_candidate_fingerprints"] == second["selected_candidate_fingerprints"]
    assert "no_thesis_execution" in first["methodology_flags"]
    assert "no_validation_execution" in first["methodology_flags"]
    assert "no_trading_logic" in first["methodology_flags"]
    forbidden = json.dumps(first).lower()
    assert "insider" not in forbidden
    assert "scammer" not in forbidden
    assert "wash trader" not in forbidden
    assert "manipulator" not in forbidden
