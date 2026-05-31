import json
from pathlib import Path

from research.mtp_research.validation.diagnostic_validation_models import (
    DIAGNOSTIC_FALLBACK_WARNING,
)
from research.mtp_research.validation.diagnostic_validation_report import (
    review_to_dict,
    write_review_json,
    write_review_markdown,
)
from research.mtp_research.validation.diagnostic_validation_review import DiagnosticValidationReviewer
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, source: str | None = None) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        entry_price_source=source,
        forward_return=0.1,
        label_quality="sparse",
    )


def test_review_report_writes_markdown_and_json_with_warning(tmp_path: Path) -> None:
    reviewer = DiagnosticValidationReviewer()
    review = reviewer.build_review(
        clean_dataset_rows=[_row("clean")],
        diagnostic_dataset_rows=[_row("diag", "nearest_research_fallback")],
        clean_rule_results=[],
        diagnostic_rule_results=[],
        clean_walk_forward_results=[],
        diagnostic_walk_forward_results=[],
        clean_thesis_decisions=[],
        diagnostic_thesis_decisions=[],
        clean_dataset_path="clean.jsonl",
        diagnostic_dataset_path="diag.jsonl",
    )
    markdown_path = write_review_markdown(review, tmp_path / "review.md")
    json_path = write_review_json(review, tmp_path / "review.json")

    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert DIAGNOSTIC_FALLBACK_WARNING in markdown
    assert "Clean vs Diagnostic Dataset" in markdown
    assert payload["diagnostic_warning"] == DIAGNOSTIC_FALLBACK_WARNING
    assert review_to_dict(review)["review_id"] == review.review_id
