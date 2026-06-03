from pathlib import Path

import pandas as pd

from research.mtp_research.validation.creator_net_flow_efficient_mover_thesis import (
    REPORT_ID,
    build_creator_net_flow_efficient_mover_thesis,
    build_fixed_creator_net_flow_buckets,
    load_frozen_definition,
)


def _master(path: Path) -> Path:
    rows = []
    specs = [
        ("weak-a", "reached_20k_but_never_50k", 1000, 1200, 12, 8, 8, -1.0, "2026-01-01", "creator-a"),
        ("weak-b", "reached_50k_but_never_100k", 1100, 1300, 11, 8, 8, -0.5, "2026-01-01", "creator-b"),
        ("mid-a", "reached_200k_but_never_500k", 3200, 4200, 8, 5, 6, 0.0, "2026-01-02", "creator-c"),
        ("run-a", "reached_500k_but_never_1m", 6200, 8200, 3, 2, 3, 0.05, "2026-01-02", "creator-d"),
        ("run-b", "reached_1m_plus", 7200, 9200, 2, 2, 3, 0.4, "2026-01-03", "creator-e"),
        ("run-c", "reached_1m_plus", 7400, 9400, 2, 2, 3, 0.6, "2026-01-04", "creator-f"),
        ("run-d", "reached_1m_plus", 7600, 9600, 2, 2, 3, 0.8, "2026-01-05", "creator-g"),
    ]
    for launch_id, tier, fdv_event, fdv_buy, events, buys, wallets, flow, date, creator in specs:
        rows.append(
            {
                "launch_id": launch_id,
                "token_mint": f"mint-{launch_id}",
                "creator": creator,
                "launch_date": date,
                "milestone_tier": tier,
                "fdv_per_event_at_20k": fdv_event,
                "fdv_per_buy_at_20k": fdv_buy,
                "fdv_per_active_wallet_at_20k": fdv_event / wallets,
                "event_count_at_20k": events,
                "buy_count_at_20k": buys,
                "active_wallets_at_20k": wallets,
                "creator_net_flow_sol_before_20k": flow,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _definition(path: Path, direction: str = "continuation_proxy") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "feature": "creator_net_flow_sol_before_20k",
                "feature_family": "creator_extraction",
                "classification": "continuation_positive_candidate",
                "higher_values_associated_with": direction,
                "effect_size_proxy": 0.9,
                "coverage_pct": 100.0,
                "feature_timing": "entry_side",
            }
        ]
    ).to_csv(path, index=False)
    return path


def test_loads_frozen_definition_from_prior_anatomy_report(tmp_path: Path) -> None:
    definition = load_frozen_definition(feature_comparison_path=_definition(tmp_path / "feature.csv"))

    assert definition["feature"] == "creator_net_flow_sol_before_20k"
    assert definition["expected_direction"] == "higher_creator_net_flow_supports_continuation_proxy"
    assert definition["classification"] == "continuation_positive_candidate"


def test_definition_missing_when_direction_is_ambiguous(tmp_path: Path) -> None:
    definition = load_frozen_definition(feature_comparison_path=_definition(tmp_path / "feature.csv", direction="flat"))

    assert definition["status"] == "definition_missing"


def test_fixed_tertile_buckets_are_deterministic(tmp_path: Path) -> None:
    frame = pd.read_parquet(_master(tmp_path / "master.parquet"))
    bucketed = build_fixed_creator_net_flow_buckets(frame, bucket_count=3)
    again = build_fixed_creator_net_flow_buckets(frame, bucket_count=3)

    assert bucketed["creator_net_flow_bucket"].equals(again["creator_net_flow_bucket"])
    assert set(bucketed["creator_net_flow_bucket"].dropna()) <= {"low", "middle", "high"}
    assert "creator_net_flow_bucket_rank" in bucketed.columns


def test_creator_net_flow_thesis_writes_outputs_and_guardrails(tmp_path: Path) -> None:
    report, paths = build_creator_net_flow_efficient_mover_thesis(
        master_path=_master(tmp_path / "master.parquet"),
        feature_comparison_path=_definition(tmp_path / "feature.csv"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
        "definition_missing",
    }
    assert report["coverage_audit"]["creator_net_flow_coverage_pct"] > 0
    assert report["descriptive_results"]["bucket_rows"]
    assert report["robustness_summary"]["checks_run"] > 0
    assert paths["summary_json_path"].exists()
    assert paths["summary_markdown_path"].exists()
    assert paths["tier_comparison_path"].exists()
    assert paths["robustness_table_path"].exists()
    assert paths["fdv_relationship_path"].exists()
    assert paths["status_path"].exists()
    text = str(report).lower() + paths["status_path"].read_text(encoding="utf-8").lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        assert blocked not in text
    assert "no_threshold_optimization" in report["methodology_flags"]
