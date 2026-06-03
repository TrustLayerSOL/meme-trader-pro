import json
from pathlib import Path

from research.mtp_research.validation.combined_p0_fingerprint_support_audit import (
    build_combined_p0_fingerprint_support_audit,
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


def _row(launch_id: str, tier: str, *, leftover: bool = False, creator: str = "creator-a", date: str = "2026-01-01") -> dict:
    high = tier == "reached_1m_plus"
    return {
        "launch_id": launch_id,
        "mint": f"mint-{launch_id}",
        "creator": creator,
        "launch_date": date,
        "milestone_tier": tier,
        "is_balanced_sample": not leftover,
        "is_leftover_sample": leftover,
        "fdv_per_event_at_20k": 10.0 if high else 2.0,
        "fdv_per_buy_at_20k": 9.0 if high else 1.0,
        "fdv_per_active_wallet_at_20k": 8.0 if high else 2.0,
        "active_wallets_at_20k": 3.0,
        "repeated_buyer_quality_proxy": 0.9 if high else 0.3,
        "early_buyer_with_prior_runner_count": 3.0 if high else 1.0,
        "early_buyer_prior_failure_count": 0.0 if high else 2.0,
        "top_holder_share_proxy": 0.95 if high else 0.6,
        "top_10_holder_share_proxy": 1.0,
        "shared_funding_proxy": False if high else True,
        "time_linked_funding_proxy": False if high else True,
        "launches_sharing_funder": 0.0 if high else 3.0,
        "creators_sharing_funder": 0.0 if high else 2.0,
    }


def _selection_summary(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "selection.json",
        {
            "report_id": "combined_p0_fingerprint_selection_design_v0",
            "readiness_classification": "fingerprint_selection_needs_support_audit",
            "selected_candidate_fingerprints": [
                {
                    "fingerprint_id": "FP001",
                    "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                    "visible_features": "fdv_per_event_at_20k;fdv_per_buy_at_20k;active_wallets_at_20k",
                    "hidden_structural_features": "shared_funding_proxy;time_linked_funding_proxy;launches_sharing_funder",
                    "expected_directions": json.dumps(
                        {
                            "fdv_per_event_at_20k": "higher",
                            "fdv_per_buy_at_20k": "higher",
                            "active_wallets_at_20k": "not_zero",
                            "shared_funding_proxy": "lower",
                            "time_linked_funding_proxy": "lower",
                            "launches_sharing_funder": "lower",
                        },
                        sort_keys=True,
                    ),
                    "formal_thesis_recommendation": "needs_more_support_analysis",
                },
                {
                    "fingerprint_id": "FP002",
                    "fingerprint_name": "Efficient Expansion With Proven Buyer Quality",
                    "visible_features": "fdv_per_event_at_20k;fdv_per_buy_at_20k",
                    "hidden_structural_features": "repeated_buyer_quality_proxy;early_buyer_with_prior_runner_count",
                    "expected_directions": json.dumps(
                        {
                            "fdv_per_event_at_20k": "higher",
                            "fdv_per_buy_at_20k": "higher",
                            "repeated_buyer_quality_proxy": "higher",
                            "early_buyer_with_prior_runner_count": "higher",
                        },
                        sort_keys=True,
                    ),
                    "formal_thesis_recommendation": "needs_more_support_analysis",
                },
            ],
        },
    )


def test_support_audit_recomputes_support_and_writes_reports(tmp_path: Path) -> None:
    selection = _selection_summary(tmp_path)
    dataset = _write_jsonl(
        tmp_path / "dataset.jsonl",
        [
            _row("a", "reached_1m_plus", creator="creator-a", date="2026-01-01"),
            _row("b", "reached_1m_plus", leftover=True, creator="creator-b", date="2026-01-02"),
            _row("c", "reached_20k_but_never_50k", creator="creator-c", date="2026-01-03"),
            _row("d", "reached_20k_but_never_50k", leftover=True, creator="creator-d", date="2026-01-04"),
        ],
    )

    report, paths = build_combined_p0_fingerprint_support_audit(
        selection_summary_path=selection,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == "combined_p0_fingerprint_support_audit_v0"
    assert report["source_counts"]["combined_rows"] == 4
    assert report["readiness_classification"] in {
        "fingerprint_support_ready_for_formal_thesis",
        "fingerprint_support_needs_more_review",
        "fingerprint_support_inconclusive",
    }
    assert report["fingerprint_audits"]
    assert all("balanced_high_tier_capture_pct" in row for row in report["fingerprint_audits"])
    assert all("leftover_high_tier_capture_pct" in row for row in report["fingerprint_audits"])
    assert paths["summary_json_path"].exists()
    assert paths["fingerprint_support_table_path"].exists()
    assert paths["status_path"].exists()


def test_support_audit_preserves_guardrails_and_determinism(tmp_path: Path) -> None:
    selection = _selection_summary(tmp_path)
    dataset = _write_jsonl(
        tmp_path / "dataset.jsonl",
        [
            _row("a", "reached_1m_plus", creator="creator-a"),
            _row("b", "reached_20k_but_never_50k", creator="creator-b"),
        ],
    )
    first, _ = build_combined_p0_fingerprint_support_audit(
        selection_summary_path=selection,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_combined_p0_fingerprint_support_audit(
        selection_summary_path=selection,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["fingerprint_audits"] == second["fingerprint_audits"]
    assert "no_thesis_execution" in first["methodology_flags"]
    assert "no_validation_execution" in first["methodology_flags"]
    assert "no_trading_logic" in first["methodology_flags"]
    forbidden = json.dumps(first).lower()
    assert "insider" not in forbidden
    assert "scammer" not in forbidden
    assert "wash trader" not in forbidden
    assert "manipulator" not in forbidden
