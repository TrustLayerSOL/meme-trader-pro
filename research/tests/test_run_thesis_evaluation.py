from pathlib import Path

from research.mtp_research.validation.run_thesis_evaluation import main
from research.mtp_research.validation.thesis_decision_store import ThesisDecisionStore
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def _write_thesis(path: Path) -> None:
    path.write_text(
        """---
thesis_id: MTP-T999
name: Test Thesis
status: active
priority: high
strategy_family: test
current_stage: research
---

# Linked Rules
- rule-1
""",
        encoding="utf-8",
    )


def _validation() -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at="2026-05-31T00:00:00+00:00",
        config=WalkForwardConfig("cfg", 10, 5, 5),
        dataset_path="dataset.jsonl",
        row_count=100,
        filtered_row_count=100,
        fold_count=3,
        rules_tested=1,
        rule_summaries=[
            RuleWalkForwardSummary(
                rule_id="rule-1",
                rule_name="Rule 1",
                valid_test_fold_count=3,
                total_test_selected_count=100,
                avg_test_net_return=0.05,
                positive_test_fold_rate=0.75,
                consistency_score=0.04,
            )
        ],
    )


def test_thesis_evaluation_cli_writes_decisions_and_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    theses_dir = tmp_path / "theses"
    theses_dir.mkdir()
    _write_thesis(theses_dir / "MTP-T999-test.md")
    wf_store_path = tmp_path / "walk_forward.jsonl"
    decision_store_path = tmp_path / "decisions.jsonl"
    output_dir = tmp_path / "reports"
    WalkForwardValidationStore(wf_store_path).upsert(_validation())

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_thesis_evaluation",
            "--theses-dir",
            str(theses_dir),
            "--walk-forward-store-path",
            str(wf_store_path),
            "--decision-store-path",
            str(decision_store_path),
            "--output-dir",
            str(output_dir),
            "--min-total-test-selected-count",
            "50",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "theses_loaded=1" in output
    assert "validation_results_loaded=1" in output
    assert "decisions_generated=1" in output
    assert len(ThesisDecisionStore(decision_store_path).load_all()) == 1
    assert (output_dir / "thesis_evaluation_report.md").exists()
    assert (output_dir / "thesis_evaluation_report.json").exists()
