from research.mtp_research.validation.price_quality_failure_analysis import (
    PriceQualityFailureAnalyzer,
)
from research.mtp_research.validation.price_quality_gate import PriceQualityGate
from research.mtp_research.validation.price_quality_models import PriceQualityConfig
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, token_mint: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": token_mint,
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "entry_price": 1.0,
        "entry_price_ts": 940,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.1,
        "price_points_count": 3,
        "label_quality": "good",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def test_failure_analysis_ranks_tokens_and_failure_combinations() -> None:
    rows = [
        _row("a-1", "mint-a", entry_price_source="nearest_research_fallback", price_points_count=1),
        _row("a-2", "mint-a", entry_price_source="nearest_research_fallback"),
        _row("b-1", "mint-b", entry_price_ts=700),
        _row("c-1", "mint-c"),
    ]
    _passed, decisions, gate_report = PriceQualityGate().filter_rows(rows, PriceQualityConfig())

    report = PriceQualityFailureAnalyzer().build_report(rows, decisions, gate_report, top_n=2)

    assert report.input_row_count == 4
    assert report.failed_row_count == 3
    assert report.top_tokens[0].token_mint == "mint-a"
    assert report.top_tokens[0].failed_row_count == 2
    assert report.top_tokens[0].failure_reason_counts["nearest_fallback_disallowed"] == 2
    assert report.failure_combo_counts["insufficient_future_price_points+nearest_fallback_disallowed"] == 1
    assert report.failure_combo_counts["nearest_fallback_disallowed"] == 1


def test_failure_analysis_recommends_price_inference_when_fallback_dominates() -> None:
    rows = [
        _row("fallback-1", "mint-a", entry_price_source="nearest_research_fallback"),
        _row("fallback-2", "mint-b", entry_price_source="nearest_research_fallback"),
        _row("clean", "mint-c"),
    ]
    _passed, decisions, gate_report = PriceQualityGate().filter_rows(rows, PriceQualityConfig())

    report = PriceQualityFailureAnalyzer().build_report(rows, decisions, gate_report)

    assert report.recommended_next_action == "improve_price_inference_before_scaling"
    assert "fallback_rows_dominate_failures" in report.warning_flags
