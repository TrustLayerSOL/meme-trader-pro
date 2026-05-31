from research.mtp_research.validation.price_quality_gate import PriceQualityGate
from research.mtp_research.validation.price_quality_models import PriceQualityConfig
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(**overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": "row-1",
        "snapshot_id": "snapshot-1",
        "outcome_id": "outcome-1",
        "token_mint": "mint-1",
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "entry_price": 1.0,
        "entry_price_ts": 940,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.1,
        "max_runup": 0.2,
        "price_points_count": 3,
        "no_future_liquidity": False,
        "rug_like_drop": False,
        "label_quality": "sparse",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def test_row_passes_with_clean_price_context() -> None:
    decision = PriceQualityGate().evaluate_row(_row(), PriceQualityConfig())

    assert decision.passed is True
    assert decision.reasons_failed == []
    assert decision.entry_staleness_sec == 60


def test_nearest_fallback_fails_by_default() -> None:
    decision = PriceQualityGate().evaluate_row(
        _row(entry_price_source="nearest_research_fallback"),
        PriceQualityConfig(),
    )

    assert decision.passed is False
    assert "nearest_fallback_disallowed" in decision.reasons_failed


def test_stale_entry_fails() -> None:
    decision = PriceQualityGate().evaluate_row(
        _row(entry_price_ts=700),
        PriceQualityConfig(max_entry_staleness_sec=120),
    )

    assert decision.passed is False
    assert "stale_entry_price" in decision.reasons_failed


def test_insufficient_future_price_points_fails() -> None:
    decision = PriceQualityGate().evaluate_row(
        _row(price_points_count=2),
        PriceQualityConfig(min_future_price_points=3),
    )

    assert decision.passed is False
    assert "insufficient_future_price_points" in decision.reasons_failed


def test_no_future_liquidity_fails_by_default() -> None:
    decision = PriceQualityGate().evaluate_row(
        _row(no_future_liquidity=True),
        PriceQualityConfig(),
    )

    assert decision.passed is False
    assert "no_future_liquidity_disallowed" in decision.reasons_failed


def test_extreme_forward_return_cap_fails() -> None:
    decision = PriceQualityGate().evaluate_row(
        _row(forward_return=3.0),
        PriceQualityConfig(max_forward_return_abs=1.0),
    )

    assert decision.passed is False
    assert "extreme_forward_return" in decision.reasons_failed


def test_gate_report_counts_failure_reasons() -> None:
    rows = [
        _row(row_id="pass-row"),
        _row(row_id="fallback-row", entry_price_source="nearest_research_fallback"),
        _row(row_id="points-row", price_points_count=1),
    ]

    passed, decisions, report = PriceQualityGate().filter_rows(rows, PriceQualityConfig())

    assert [row.row_id for row in passed] == ["pass-row"]
    assert len(decisions) == 3
    assert report.input_row_count == 3
    assert report.passed_row_count == 1
    assert report.failure_reason_counts["nearest_fallback_disallowed"] == 1
    assert report.failure_reason_counts["insufficient_future_price_points"] == 1
