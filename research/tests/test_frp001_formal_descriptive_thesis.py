from pathlib import Path

import pandas as pd

from research.mtp_research.validation.frp001_formal_descriptive_thesis import (
    CLASSIFICATION_DEFINITION_MISSING,
    REPORT_ID,
    build_frp001_formal_descriptive_thesis,
    load_frp001_definition,
)


def _candidate_table(path: Path, *, include: bool = True) -> Path:
    rows = []
    if include:
        rows.append(
            {
                "fingerprint_id": "FRP-001",
                "fingerprint_name": "Efficient visible expansion with better wallet-quality proxy",
                "description": "Higher FDV-proxy efficiency and better early buyer history appear together in stronger runners.",
                "feature_families_included": "visible_fdv_flow;wallet_quality_repeated_buyers",
                "specific_features": "fdv_per_event_at_20k;fdv_per_buy_at_20k;smart_money_quality_proxy;early_buyer_with_prior_runner_count",
                "expected_direction": '{"fdv_per_event_at_20k": "higher_in_stronger_runners", "fdv_per_buy_at_20k": "higher_in_stronger_runners", "smart_money_quality_proxy": "flat_or_unknown", "early_buyer_with_prior_runner_count": "flat_or_unknown"}',
                "entry_side_vs_path_side_vs_exit_side": "entry_side",
                "coverage": '{"usable_feature_count": 4, "median_coverage_pct": 80.0}',
                "missing_fields": "LP control; priority fee; true market cap",
                "limitations": "Descriptive FDV-proxy comparison only.",
                "what_would_invalidate_it": "Directional disappearance.",
                "deserves_formal_descriptive_thesis_design_later": True,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _master(path: Path) -> Path:
    rows = []
    tiers = [
        ("weak-a", "reached_20k_but_never_50k", "2026-01-01", "creator-a", 1000, 2000, 0.1, 1),
        ("weak-b", "reached_50k_but_never_100k", "2026-01-02", "creator-b", 1100, 2100, 0.2, 1),
        ("mid-a", "reached_100k_but_never_200k", "2026-01-03", "creator-c", 2500, 3500, 0.3, 2),
        ("mid-b", "reached_200k_but_never_500k", "2026-01-04", "creator-d", 3000, 4000, 0.4, 3),
        ("run-a", "reached_500k_but_never_1m", "2026-01-05", "creator-e", 6000, 8000, 0.7, 6),
        ("run-b", "reached_1m_plus", "2026-01-06", "creator-f", 7000, 9000, 0.8, 8),
    ]
    for launch_id, tier, date, creator, fdv_event, fdv_buy, wallet_quality, prior_runner in tiers:
        rows.append(
            {
                "launch_id": launch_id,
                "mint": f"mint-{launch_id}",
                "creator": creator,
                "launch_date": date,
                "launch_ts": 1_700_000_000 + len(rows) * 86_400,
                "milestone_tier": tier,
                "fdv_per_event_at_20k": fdv_event,
                "fdv_per_buy_at_20k": fdv_buy,
                "smart_money_quality_proxy": wallet_quality,
                "early_buyer_with_prior_runner_count": prior_runner,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_load_frp001_definition_from_candidate_fingerprints(tmp_path: Path) -> None:
    definition = load_frp001_definition(_candidate_table(tmp_path / "candidates.csv"))

    assert definition["fingerprint_id"] == "FRP-001"
    assert definition["fingerprint_name"] == "Efficient visible expansion with better wallet-quality proxy"
    assert definition["visible_features"] == ["fdv_per_event_at_20k", "fdv_per_buy_at_20k"]
    assert definition["wallet_quality_features"] == ["smart_money_quality_proxy", "early_buyer_with_prior_runner_count"]
    assert definition["expected_direction"]["fdv_per_buy_at_20k"] == "higher_in_stronger_runners"


def test_fail_closed_when_frp001_definition_missing(tmp_path: Path) -> None:
    report, paths = build_frp001_formal_descriptive_thesis(
        candidate_fingerprints_path=_candidate_table(tmp_path / "candidates.csv", include=False),
        master_path=_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["classification"] == CLASSIFICATION_DEFINITION_MISSING
    assert report["rows_analyzed"] == 0
    assert paths["summary_json_path"].exists()


def test_frp001_formal_descriptive_outputs_and_guardrails(tmp_path: Path) -> None:
    report, paths = build_frp001_formal_descriptive_thesis(
        candidate_fingerprints_path=_candidate_table(tmp_path / "candidates.csv"),
        master_path=_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["frozen_definition"]["fingerprint_id"] == "FRP-001"
    assert report["rows_analyzed"] == 6
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["guardrails"]["frp002_runs"] == 0
    assert report["feature_coverage"]["features"]["fdv_per_buy_at_20k"]["coverage_pct"] == 100.0
    assert report["tier_support_table"]
    assert report["visible_vs_wallet_quality_comparison"]["wallet_quality_adds_information"] in {True, False}
    assert report["robustness_summary"]["checks_run"] >= 4
    assert report["classification"] in {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited", "definition_missing"}

    assert paths["summary_json_path"].exists()
    assert paths["summary_markdown_path"].exists()
    assert paths["tier_support_table_path"].exists()
    assert paths["feature_coverage_table_path"].exists()
    assert paths["visible_vs_wallet_quality_comparison_path"].exists()
    assert paths["robustness_table_path"].exists()
    assert paths["status_path"].exists()


def test_deterministic_and_no_unsupported_labels(tmp_path: Path) -> None:
    kwargs = {
        "candidate_fingerprints_path": _candidate_table(tmp_path / "candidates.csv"),
        "master_path": _master(tmp_path / "master.parquet"),
    }
    first, _ = build_frp001_formal_descriptive_thesis(
        **kwargs,
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_frp001_formal_descriptive_thesis(
        **kwargs,
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["tier_support_table"] == second["tier_support_table"]
    assert first["robustness_table"] == second["robustness_table"]
    text = str(first).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        assert blocked not in text
