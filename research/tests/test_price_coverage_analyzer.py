from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.price_coverage_analyzer import PriceCoverageAnalyzer


def _event(event_id: str, token: str, event_type: str, price: float | None):
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=100 + len(event_id),
        event_type=event_type,
        token_mint=token,
        price_quote=price,
    )


def _label(**kwargs):
    payload = {
        "outcome_id": "outcome-1",
        "snapshot_id": "snapshot-1",
        "token_mint": "token-a",
        "snapshot_ts": 100,
        "horizon_name": "5m",
        "horizon_seconds": 300,
        "label_quality": "no_price",
        "entry_price": None,
        "end_price": None,
        "price_points_count": 0,
        "entry_price_source": "missing",
    }
    payload.update(kwargs)
    return OutcomeLabel(**payload)


def test_price_coverage_analyzer_counts_priced_events_and_tokens() -> None:
    report = PriceCoverageAnalyzer().build_report(
        [
            _event("e1", "token-a", "possible_buy", 0.01),
            _event("e2", "token-a", "possible_sell", None),
            _event("e3", "token-b", "transaction_observed", 0.02),
        ]
    )

    assert report.event_count == 3
    assert report.events_with_price_quote == 2
    assert report.token_count == 2
    assert report.tokens_with_price == 2
    assert report.event_type_counts["possible_buy"] == 1
    assert report.priced_event_type_counts["possible_buy"] == 1


def test_price_coverage_analyzer_counts_no_price_causes() -> None:
    report = PriceCoverageAnalyzer().build_report(
        [_event("e1", "token-a", "possible_buy", None)],
        [
            _label(),
            _label(outcome_id="outcome-2", entry_price=1.0, entry_price_source="last_before_snapshot"),
        ],
    )

    assert report.no_price_label_count == 2
    assert report.likely_no_price_causes["missing_entry_price"] == 1
    assert report.likely_no_price_causes["missing_end_price"] == 2
    assert report.likely_no_price_causes["no_price_points_in_horizon"] == 2
    assert "low_price_coverage" in report.warning_flags
