import json
from pathlib import Path

from research.mtp_research.validation.structural_enrichment_master_plan import (
    build_structural_enrichment_master_plan,
)


def test_master_plan_inventory_coverage_priority_and_budget_schema(tmp_path: Path) -> None:
    report, paths = build_structural_enrichment_master_plan(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STRUCTURAL_ENRICHMENT_MASTER_PLAN_STATUS.md",
    )

    families = {row["data_family"] for row in report["inventory"]}
    priorities = {row["priority"] for row in report["priority_rank"]}
    helius_rows = report["helius_budget_plan"]

    assert report["report_id"] == "structural_enrichment_master_plan_v0"
    assert len(families) >= 15
    assert {"valuation_price_path_fdv_efficiency", "top_holder_structure", "funding_lineage"} <= families
    assert {"P0", "P1", "P2", "P3"} <= priorities
    assert all("coverage_all_launches" in row and "feasibility_classification" in row for row in report["coverage_matrix"])
    assert all("estimated_credits" in row and "stop_conditions" in row for row in helius_rows)
    assert any(row["budget_gate"] == "pilot_cap_25000" for row in helius_rows)
    assert paths["inventory_csv_path"].exists()
    assert paths["helius_budget_plan_path"].exists()


def test_master_plan_guardrails_and_recommendation(tmp_path: Path) -> None:
    report, _ = build_structural_enrichment_master_plan(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STRUCTURAL_ENRICHMENT_MASTER_PLAN_STATUS.md",
    )

    text = json.dumps(report).lower()
    assert "no_trading_logic" in report["methodology_flags"]
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_live_trading" in report["methodology_flags"]
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text
    assert report["recommended_campaign"]["campaign"] == "B"
    assert report["readiness_classification"] == "enrichment_plan_ready_for_combined_offline_and_helius"


def test_master_plan_is_deterministic(tmp_path: Path) -> None:
    first, _ = build_structural_enrichment_master_plan(
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_structural_enrichment_master_plan(
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["inventory"] == second["inventory"]
    assert first["priority_rank"] == second["priority_rank"]
    assert first["helius_budget_plan"] == second["helius_budget_plan"]
