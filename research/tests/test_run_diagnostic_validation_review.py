from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_diagnostic_validation_review import main


def _write_thesis(path: Path) -> None:
    path.write_text(
        """---
thesis_id: MTP-T999
name: Diagnostic Test Thesis
status: active
priority: high
strategy_family: test
current_stage: research
---

# Linked Rules
- positive_flow_basic
""",
        encoding="utf-8",
    )


def _row(row_id: str, snapshot_ts: int, source: str | None = None) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        entry_price_source=source,
        end_price=1.1,
        forward_return=0.1,
        possible_buy_count=3,
        possible_sell_count=0,
        confidence_weighted_net_flow=1.0,
        buy_sell_imbalance=0.75,
        unique_actor_count=3,
        quote_volume=1.0,
        label_quality="sparse",
    )


def test_diagnostic_validation_review_cli_writes_only_diagnostic_outputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    clean_dataset_path = tmp_path / "clean_dataset.jsonl"
    diagnostic_dataset_path = tmp_path / "diagnostics" / "research_dataset_nearest300.jsonl"
    diagnostic_output_dir = tmp_path / "diagnostics" / "reports"
    diagnostic_rule_store = tmp_path / "diagnostics" / "rule_results.jsonl"
    diagnostic_walk_store = tmp_path / "diagnostics" / "walk_forward.jsonl"
    diagnostic_decision_store = tmp_path / "diagnostics" / "thesis_decisions.jsonl"
    theses_dir = tmp_path / "theses"
    theses_dir.mkdir()
    _write_thesis(theses_dir / "MTP-T999-test.md")

    clean_store = ResearchDatasetStore(clean_dataset_path)
    diagnostic_store = ResearchDatasetStore(diagnostic_dataset_path)
    for idx in range(8):
        clean_store.upsert(_row(f"clean-{idx}", idx, "exact_snapshot"))
    for idx in range(20):
        source = "nearest_research_fallback" if idx >= 8 else "exact_snapshot"
        diagnostic_store.upsert(_row(f"diag-{idx}", idx, source))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_diagnostic_validation_review",
            "--clean-dataset-path",
            str(clean_dataset_path),
            "--diagnostic-dataset-path",
            str(diagnostic_dataset_path),
            "--diagnostic-output-dir",
            str(diagnostic_output_dir),
            "--diagnostic-rule-store-path",
            str(diagnostic_rule_store),
            "--diagnostic-walk-forward-store-path",
            str(diagnostic_walk_store),
            "--diagnostic-decision-store-path",
            str(diagnostic_decision_store),
            "--clean-rule-store-path",
            str(tmp_path / "clean_rule_results.jsonl"),
            "--clean-walk-forward-store-path",
            str(tmp_path / "clean_walk_forward.jsonl"),
            "--clean-decision-store-path",
            str(tmp_path / "clean_thesis_decisions.jsonl"),
            "--theses-dir",
            str(theses_dir),
            "--train-window-seconds",
            "10",
            "--test-window-seconds",
            "5",
            "--step-seconds",
            "5",
            "--min-train-rows",
            "1",
            "--min-test-rows",
            "1",
            "--min-rule-rows",
            "1",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "clean_row_count=8" in output
    assert "diagnostic_row_count=20" in output
    assert "nearest_fallback_row_count=12" in output
    assert "recommended_next_action=" in output
    assert "network_calls=0" in output
    assert diagnostic_rule_store.exists()
    assert diagnostic_walk_store.exists()
    assert diagnostic_decision_store.exists()
    assert list(diagnostic_output_dir.glob("*.md"))
    assert list(diagnostic_output_dir.glob("*.json"))
    assert all(str(path).startswith(str(tmp_path / "diagnostics")) for path in diagnostic_output_dir.rglob("*"))
