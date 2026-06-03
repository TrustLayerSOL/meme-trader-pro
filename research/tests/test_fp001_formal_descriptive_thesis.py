import json
from pathlib import Path

from research.mtp_research.validation.fp001_formal_descriptive_thesis import (
    build_fp001_formal_descriptive_thesis,
    load_frozen_fp001_definition,
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
        "has_all_three_p0_layers": True,
        "is_balanced_sample": not leftover,
        "is_leftover_sample": leftover,
        "fdv_per_event_at_20k": 10.0 if high else 1.0,
        "fdv_per_buy_at_20k": 8.0 if high else 1.0,
        "fdv_per_active_wallet_at_20k": 6.0 if high else 1.0,
        "active_wallets_at_20k": 3.0,
        "shared_funding_proxy": False if high else True,
        "time_linked_funding_proxy": False if high else True,
        "launches_sharing_funder": 0.0 if high else 3.0,
        "creators_sharing_funder": 0.0 if high else 2.0,
    }


def _support_summary(tmp_path: Path, *, include_fp001: bool = True) -> Path:
    audits = []
    if include_fp001:
        audits.append(
            {
                "fingerprint_id": "FP001",
                "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                "features_audited": "fdv_per_event_at_20k;fdv_per_buy_at_20k;fdv_per_active_wallet_at_20k;active_wallets_at_20k;shared_funding_proxy;time_linked_funding_proxy;launches_sharing_funder;creators_sharing_funder",
                "support_method": "fixed_median_reference_no_threshold_search",
                "support_audit_decision": "ready_for_formal_descriptive_thesis",
                "balanced_support_rows": 2,
                "leftover_support_rows": 1,
                "combined_support_rows": 3,
                "balanced_high_tier_capture_pct": 50,
                "leftover_high_tier_capture_pct": 100,
                "direction_consistency": "consistent_or_flat",
            }
        )
    selection = _write_json(
        tmp_path / "selection.json",
        {
            "selected_candidate_fingerprints": [
                {
                    "fingerprint_id": "FP001",
                    "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
                    "visible_features": "fdv_per_event_at_20k;fdv_per_buy_at_20k;fdv_per_active_wallet_at_20k;active_wallets_at_20k",
                    "hidden_structural_features": "shared_funding_proxy;time_linked_funding_proxy;launches_sharing_funder;creators_sharing_funder",
                    "entry_side_or_exit_side": "entry_side",
                    "expected_directions": json.dumps(
                        {
                            "fdv_per_event_at_20k": "higher",
                            "fdv_per_buy_at_20k": "higher",
                            "fdv_per_active_wallet_at_20k": "higher",
                            "active_wallets_at_20k": "not_zero",
                            "shared_funding_proxy": "lower",
                            "time_linked_funding_proxy": "lower",
                            "launches_sharing_funder": "lower",
                            "creators_sharing_funder": "lower",
                        },
                        sort_keys=True,
                    ),
                    "data_still_missing": "true_market_cap;full_holder_addresses",
                    "what_could_invalidate_it": "If balanced and leftover samples disagree.",
                }
            ]
        },
    )
    return _write_json(
        tmp_path / "support.json",
        {
            "fingerprint_audits": audits,
            "source_paths": {"selection_summary_path": str(selection)},
        },
    )


def test_loads_frozen_fp001_definition_from_artifacts(tmp_path: Path) -> None:
    support = _support_summary(tmp_path)
    definition = load_frozen_fp001_definition(support)

    assert definition["fingerprint_id"] == "FP001"
    assert definition["fingerprint_name"] == "Efficient Expansion With Clean Funding Structure"
    assert "fdv_per_event_at_20k" in definition["feature_list"]
    assert definition["expected_directions"]["shared_funding_proxy"] == "lower"
    assert definition["entry_side_or_exit_side"] == "entry_side"
    assert definition["support_audit_decision"] == "ready_for_formal_descriptive_thesis"


def test_fp001_thesis_fails_closed_when_definition_missing(tmp_path: Path) -> None:
    support = _support_summary(tmp_path, include_fp001=False)
    dataset = _write_jsonl(tmp_path / "dataset.jsonl", [_row("a", "reached_1m_plus")])
    report, paths = build_fp001_formal_descriptive_thesis(
        support_summary_path=support,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["classification"] == "definition_missing"
    assert report["readiness_classification"] == "fp001_definition_missing"
    assert "repair_support_audit_before_thesis_execution" in report["next_recommendation"]
    assert paths["summary_json_path"].exists()


def test_fp001_thesis_analyzes_only_fp001_and_writes_reports(tmp_path: Path) -> None:
    support = _support_summary(tmp_path)
    dataset = _write_jsonl(
        tmp_path / "dataset.jsonl",
        [
            _row("a", "reached_1m_plus", creator="creator-a", date="2026-01-01"),
            _row("b", "reached_1m_plus", leftover=True, creator="creator-b", date="2026-01-02"),
            _row("c", "reached_20k_but_never_50k", creator="creator-c", date="2026-01-03"),
            _row("d", "reached_50k_but_never_100k", leftover=True, creator="creator-d", date="2026-01-04"),
        ],
    )

    report, paths = build_fp001_formal_descriptive_thesis(
        support_summary_path=support,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == "fp001_formal_descriptive_thesis_v0"
    assert report["frozen_fp001_definition"]["fingerprint_id"] == "FP001"
    assert report["rows_analyzed"] == 4
    assert report["feature_coverage"]["rows_with_all_fp001_fields"] == 4
    assert "FP002" not in json.dumps(report["formal_context_note"])
    assert "fp002_status" in report["formal_context_note"]
    assert report["tier_support_table"]
    assert report["balanced_leftover_results"]["combined"]["rows"] == 4
    assert report["robustness_checks"]
    assert report["classification"] in {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited", "definition_missing"}
    assert paths["tier_support_table_path"].exists()
    assert paths["robustness_table_path"].exists()


def test_fp001_thesis_guardrails_and_determinism(tmp_path: Path) -> None:
    support = _support_summary(tmp_path)
    dataset = _write_jsonl(
        tmp_path / "dataset.jsonl",
        [_row("a", "reached_1m_plus"), _row("b", "reached_20k_but_never_50k", creator="creator-b")],
    )
    first, _ = build_fp001_formal_descriptive_thesis(
        support_summary_path=support,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_fp001_formal_descriptive_thesis(
        support_summary_path=support,
        combined_dataset_path=dataset,
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["tier_support_table"] == second["tier_support_table"]
    assert "no_validation_execution" in first["methodology_flags"]
    assert "no_trading_logic" in first["methodology_flags"]
    assert "no_fp002_or_fp003_thesis_execution" in first["methodology_flags"]
    forbidden = json.dumps(first).lower()
    assert "insider" not in forbidden
    assert "scammer" not in forbidden
    assert "wash trader" not in forbidden
    assert "manipulator" not in forbidden
