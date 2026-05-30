from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.price_series_builder import TokenPriceSeriesBuilder


def _event(
    event_id: str,
    token_mint: str | None,
    block_time: int | None,
    price_quote: float | None,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=block_time,
        event_type="possible_buy",
        token_mint=token_mint,
        price_quote=price_quote,
        venue="unknown",
        metadata_json={"confidence": 0.7},
    )


def test_builds_price_points_only_from_valid_events() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points(
        [
            _event("valid", "mint-1", 100, 1.5),
            _event("missing-token", None, 100, 1.5),
            _event("missing-time", "mint-1", None, 1.5),
            _event("missing-price", "mint-1", 100, None),
            _event("zero-price", "mint-1", 100, 0),
            _event("negative-price", "mint-1", 100, -1),
        ]
    )

    assert len(points) == 1
    assert points[0].token_mint == "mint-1"
    assert points[0].price_quote == 1.5
    assert points[0].source_event_id == "valid"
    assert points[0].confidence == 0.7


def test_groups_by_token() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points(
        [_event("a", "mint-1", 100, 1), _event("b", "mint-2", 100, 2)]
    )

    grouped = builder.group_by_token(points)

    assert set(grouped) == {"mint-1", "mint-2"}


def test_get_entry_price_exact_and_last_prior_within_staleness() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points(
        [
            _event("prior", "mint-1", 90, 1),
            _event("exact", "mint-1", 100, 2),
        ]
    )

    assert builder.get_entry_price(points, 100).source_event_id == "exact"
    assert builder.get_entry_price(points, 95).source_event_id == "prior"


def test_get_entry_price_returns_none_if_stale() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points([_event("prior", "mint-1", 10, 1)])

    assert builder.get_entry_price(points, 100, max_staleness_sec=60) is None


def test_get_entry_price_can_use_first_after() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points([_event("after", "mint-1", 110, 1)])

    assert builder.get_entry_price(points, 100, allow_first_after=True).source_event_id == "after"


def test_get_forward_points_strict_future_and_horizon_boundary() -> None:
    builder = TokenPriceSeriesBuilder()
    points = builder.build_price_points(
        [
            _event("before", "mint-1", 99, 1),
            _event("exact", "mint-1", 100, 1),
            _event("inside", "mint-1", 150, 2),
            _event("boundary", "mint-1", 160, 3),
            _event("outside", "mint-1", 161, 4),
        ]
    )

    forward = builder.get_forward_points(points, snapshot_ts=100, horizon_seconds=60)

    assert [point.source_event_id for point in forward] == ["inside", "boundary"]
