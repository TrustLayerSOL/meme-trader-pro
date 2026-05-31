import json
from pathlib import Path

from research.mtp_research.validation.walk_forward_models import (
    FoldRuleResult,
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardValidationResult,
)
from research.mtp_research.validation.walk_forward_report import (
    format_number,
    format_percent,
    result_to_dict,
    write_result_json,
    write_result_markdown,
)


def _result() -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at="2026-05-30T00:00:00+00:00",
        config=WalkForwardConfig("cfg", 10, 5, 5),
        dataset_path="dataset.jsonl",
        row_count=20,
        filtered_row_count=18,
        fold_count=1,
        rules_tested=1,
        folds=[WalkForwardFold("fold-1", 0, 0, 9, 10, 14, train_row_count=10, test_row_count=5)],
        fold_rule_results=[
            FoldRuleResult(
                "fold-1",
                0,
                "rule-1",
                "Rule 1",
                train_selected_count=3,
                test_selected_count=2,
                train_avg_net_return=0.1,
                test_avg_net_return=0.05,
                train_win_rate=1.0,
                test_win_rate=0.5,
                warning_flags=["small_test_fold"],
            )
        ],
        rule_summaries=[
            RuleWalkForwardSummary(
                "rule-1",
                "Rule 1",
                valid_test_fold_count=1,
                total_test_selected_count=2,
                avg_test_net_return=0.05,
                median_test_net_return=0.05,
                positive_test_fold_rate=1.0,
                consistency_score=0.05,
                warning_flags=["small_total_test_sample"],
            )
        ],
        top_findings=["Exploratory finding; not a trading recommendation."],
        warning_flags=["exploratory_walk_forward_not_live_signal"],
    )


def test_result_to_dict_serializes_result() -> None:
    payload = result_to_dict(_result())
    assert payload["validation_id"] == "validation-1"
    assert payload["folds"][0]["fold_id"] == "fold-1"


def test_write_result_json_writes_valid_json(tmp_path: Path) -> None:
    output_path = write_result_json(_result(), tmp_path / "result.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["validation_id"] == "validation-1"


def test_write_result_markdown_writes_readable_markdown_sections(tmp_path: Path) -> None:
    output_path = write_result_markdown(_result(), tmp_path / "result.md")
    text = output_path.read_text(encoding="utf-8")
    assert "# Walk-Forward Validation Report v0" in text
    assert "`exploratory_walk_forward_not_live_signal`" in text
    assert "## Folds" in text
    assert "| Fold | Train Start |" in text
    assert "## Rule Summaries" in text
    assert "| Rule | Valid Test Folds |" in text
    assert "small_test_fold" in text


def test_format_helpers_handle_none_safely() -> None:
    assert format_percent(None) == "n/a"
    assert format_number(None) == "n/a"
    assert format_percent(0.25) == "25.00%"
    assert format_number(1.2345678) == "1.234568"
