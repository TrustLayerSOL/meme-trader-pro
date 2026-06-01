from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.native_sol_proxy_quality import NativeSolProxyQualityAnalyzer
from research.mtp_research.validation.native_sol_proxy_quality_models import NativeSolProxyQualityConfig
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


METHOD = "transaction_native_sol_quote_over_base_v0"


def _row(row_id: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": "mint-1",
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "entry_price": 1.0,
        "entry_price_ts": 1_000,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.05,
        "max_runup": 0.1,
        "price_points_count": 3,
        "label_quality": "sparse",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def _event(event_id: str, ts: int, price: float, method: str | None = None) -> NormalizedEvent:
    metadata = {"price_inference_method": method} if method else {}
    return NormalizedEvent(
        event_id=event_id,
        signature=f"sig-{event_id}",
        slot=None,
        block_time=ts,
        event_type="trade",
        token_mint="mint-1",
        price_quote=price,
        metadata_json=metadata,
    )


def test_detects_native_sol_proxy_row_from_metadata() -> None:
    row = _row("proxy", metadata_json={"price_path": {"method": METHOD}})

    assert NativeSolProxyQualityAnalyzer().is_native_sol_proxy_row(row)


def test_detects_native_sol_proxy_event_method() -> None:
    row = _row("proxy")
    events = [_event("proxy", 1_010, 1.1, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert decision.is_native_sol_proxy_backed
    assert "native_sol_proxy_backed" in decision.warning_flags


def test_native_proxy_row_fails_excessive_forward_return() -> None:
    row = _row("proxy", forward_return=3.0)
    events = [_event("a", 1_010, 1.0, METHOD), _event("b", 1_020, 1.2, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert not decision.passed
    assert "excessive_forward_return" in decision.reasons_failed


def test_native_proxy_row_fails_excessive_runup() -> None:
    row = _row("proxy", max_runup=6.0)
    events = [_event("a", 1_010, 1.0, METHOD), _event("b", 1_020, 1.2, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert not decision.passed
    assert "excessive_runup" in decision.reasons_failed


def test_native_proxy_row_fails_insufficient_proxy_price_points() -> None:
    row = _row("proxy")
    events = [_event("a", 1_010, 1.0, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert not decision.passed
    assert "insufficient_proxy_price_points" in decision.reasons_failed


def test_native_proxy_row_fails_large_proxy_gap() -> None:
    row = _row("proxy")
    events = [_event("a", 1_010, 1.0, METHOD), _event("b", 1_400, 1.1, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert not decision.passed
    assert "large_proxy_price_gap" in decision.reasons_failed


def test_native_proxy_row_fails_extreme_price_jump() -> None:
    row = _row("proxy")
    events = [_event("a", 1_010, 1.0, METHOD), _event("b", 1_020, 50.0, METHOD)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert not decision.passed
    assert "extreme_proxy_price_jump" in decision.reasons_failed


def test_non_proxy_row_passes_basic_gate() -> None:
    row = _row("clean")
    events = [_event("a", 1_010, 1.0), _event("b", 1_020, 1.1)]

    decision = NativeSolProxyQualityAnalyzer().evaluate_row(row, events, NativeSolProxyQualityConfig())

    assert decision.passed
    assert not decision.is_native_sol_proxy_backed
