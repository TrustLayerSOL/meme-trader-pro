import csv
import json
from pathlib import Path

from research.mtp_research.validation.axiom_historical_parity_mapper import (
    build_axiom_historical_parity_report,
)


def test_axiom_field_mapping_schema_and_outputs(tmp_path: Path) -> None:
    report, paths = build_axiom_historical_parity_report(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "AXIOM_HISTORICAL_PARITY_STATUS.md",
    )

    assert report["report_id"] == "axiom_historical_parity_v0"
    assert report["readiness_classification"] == "axiom_historical_parity_plan_ready"
    assert len(report["field_map"]) >= 45

    required_columns = {
        "axiom_concept",
        "historical_field",
        "current_availability",
        "coverage",
        "source",
        "local_or_offline",
        "helius_needed",
        "dexscreener_needed",
        "priority",
        "entry_or_exit_side",
        "blocker",
        "feasibility_classification",
    }
    assert required_columns <= set(report["field_map"][0])

    assert paths["field_map_csv_path"].exists()
    assert paths["summary_json_path"].exists()
    assert paths["summary_markdown_path"].exists()
    assert paths["status_path"].exists()

    with paths["field_map_csv_path"].open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(report["field_map"])
    assert any(row["historical_field"] == "top_10_holder_share_at_milestone" for row in rows)


def test_axiom_mapper_uses_neutral_labels_and_guardrails(tmp_path: Path) -> None:
    report, _ = build_axiom_historical_parity_report(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "AXIOM_HISTORICAL_PARITY_STATUS.md",
    )

    text = json.dumps(report).lower()
    assert "neutral_proxy_labels_only" in report["methodology_flags"]
    assert "no_trading_logic" in report["methodology_flags"]
    assert "no_live_trading" in report["methodology_flags"]
    assert "no_paper_trading" in report["methodology_flags"]
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_grid_search" in report["methodology_flags"]
    assert "no_ml_black_boxes" in report["methodology_flags"]
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text


def test_axiom_mapper_readiness_budget_and_recommendation(tmp_path: Path) -> None:
    report, _ = build_axiom_historical_parity_report(
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "AXIOM_HISTORICAL_PARITY_STATUS.md",
    )

    feasibility = {row["feasibility_classification"] for row in report["field_map"]}
    budget = report["helius_budget_policy"]
    recommendation = report["recommended_next_execution"]

    assert {"ready_now", "ready_with_join", "ready_with_helius_pilot", "blocked"} <= feasibility
    assert budget["pilot_cap_credits"] == 25_000
    assert budget["medium_enrichment_confirmation_threshold_credits"] == 100_000
    assert budget["blocked_above_credits"] == 500_000
    assert recommendation["selection"] == "B"
    assert recommendation["action"] == "run_creator_funder_transfer_graph_pilot"
    assert recommendation["execute_now"] is False


def test_axiom_mapper_is_deterministic(tmp_path: Path) -> None:
    first, _ = build_axiom_historical_parity_report(
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_axiom_historical_parity_report(
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["field_map"] == second["field_map"]
    assert first["pilot_prioritization"] == second["pilot_prioritization"]
    assert first["recommended_next_execution"] == second["recommended_next_execution"]
