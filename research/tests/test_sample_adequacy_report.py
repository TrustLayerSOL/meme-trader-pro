from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.sample_adequacy import SampleAdequacyAnalyzer
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)


def _row(row_id: str, token: str, ts: int) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token,
        snapshot_ts=ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="1m",
        horizon_seconds=60,
    )


def _validation() -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at=utc_now_iso(),
        config=WalkForwardConfig("cfg", 900, 300, 300),
        dataset_path="dataset.jsonl",
        row_count=10,
        filtered_row_count=10,
        fold_count=4,
        rules_tested=1,
        rule_summaries=[
            RuleWalkForwardSummary(
                rule_id="rule-1",
                rule_name="Rule 1",
                valid_test_fold_count=4,
                total_test_selected_count=52,
            )
        ],
    )


def test_sample_adequacy_report_recommends_more_data_for_small_sample() -> None:
    rows = [_row("1", "mint-1", 100), _row("2", "mint-2", 200)]
    report = SampleAdequacyAnalyzer().build_report(rows, [_validation()])

    assert report.real_token_count == 2
    assert report.time_span_seconds == 100
    assert report.valid_test_fold_count == 4
    assert report.total_test_selected_count == 52
    assert report.adequate_for_rejection is False
    assert report.adequate_for_promotion is False
    assert report.recommended_data_expansion == "add_more_real_candidates_and_expand_time_span"
