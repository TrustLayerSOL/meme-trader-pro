import json

from research.mtp_research.validation.price_quality_validation_comparison import (
    build_price_quality_validation_comparison,
    write_comparison_json,
    write_comparison_markdown,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def _row(row_id: str, token_mint: str = "mint-1") -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=1_000,
        window_name="1m",
        window_seconds=60,
        horizon_name="15m",
        horizon_seconds=900,
        entry_price=1.0,
        forward_return=0.1,
        label_quality="sparse",
    )


def test_comparison_report_calculates_row_and_fold_loss(tmp_path) -> None:
    ungated_dataset = tmp_path / "ungated.jsonl"
    gated_dataset = tmp_path / "gated.jsonl"
    ResearchDatasetStore(ungated_dataset).replace_all([_row("a"), _row("b"), _row("c", "mint-2")])
    ResearchDatasetStore(gated_dataset).replace_all([_row("a")])
    ungated_fold = tmp_path / "ungated_fold.json"
    gated_fold = tmp_path / "gated_fold.json"
    ungated_fold.write_text(json.dumps({"config_results": [{"config_name": "x", "valid_fold_count": 4, "rule_sufficiency": [{"total_test_selected_count": 20}]}]}), encoding="utf-8")
    gated_fold.write_text(json.dumps({"config_results": [{"config_name": "x", "valid_fold_count": 1, "rule_sufficiency": [{"total_test_selected_count": 5}]}]}), encoding="utf-8")

    report = build_price_quality_validation_comparison(
        ungated_dataset_path=ungated_dataset,
        gated_dataset_path=gated_dataset,
        ungated_fold_json_path=ungated_fold,
        gated_fold_json_path=gated_fold,
    )

    assert report["row_loss_count"] == 2
    assert report["row_loss_rate"] == 2 / 3
    assert report["token_loss_count"] == 1
    assert report["fold_loss_count"] == 3
    assert report["selected_trade_loss_count"] == 15


def test_comparison_report_writers(tmp_path) -> None:
    report = {"report_id": "comparison-test", "row_loss_count": 1, "warning_flags": []}

    json_path = write_comparison_json(report, tmp_path / "comparison.json")
    markdown_path = write_comparison_markdown(report, tmp_path / "comparison.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["row_loss_count"] == 1
    assert "Price Quality Validation Comparison" in markdown_path.read_text(encoding="utf-8")
