import pytest

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_label_builder import OutcomeLabelBuilder
from research.mtp_research.validation.outcome_models import OutcomeHorizon
from research.mtp_research.validation.price_series_builder import TokenPriceSeriesBuilder


TOKEN = "mint-1"
OTHER_TOKEN = "mint-2"


def _snapshot(token_mint: str = TOKEN, snapshot_id: str = "snapshot-1") -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        token_mint=token_mint,
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
    )


def _event(
    event_id: str,
    block_time: int,
    price_quote: float | None,
    event_type: str = "possible_buy",
    actor: str | None = "actor-1",
    token_mint: str = TOKEN,
    base_qty: float | None = 1.0,
    quote_qty: float | None = 2.0,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=block_time,
        event_type=event_type,
        token_mint=token_mint,
        actor=actor,
        base_qty=base_qty,
        quote_qty=quote_qty,
        price_quote=price_quote,
        metadata_json={"confidence": 0.7},
    )


def _label(events: list[NormalizedEvent]):
    builder = OutcomeLabelBuilder(horizons=[OutcomeHorizon(name="1m", seconds=60)])
    points = TokenPriceSeriesBuilder().build_price_points(events)
    return builder.build_label_for_snapshot(_snapshot(), events, points, builder.horizons[0])


def test_forward_return_runup_drawdown_and_rug_label() -> None:
    label = _label(
        [
            _event("entry", 100, 1.0),
            _event("up", 120, 1.5),
            _event("down", 140, 0.2),
            _event("end", 160, 1.2),
        ]
    )

    assert label.forward_return == pytest.approx(0.2)
    assert label.max_runup == pytest.approx(0.5)
    assert label.max_drawdown == pytest.approx(-0.8)
    assert label.rug_like_drop is True
    assert label.survived_horizon is True
    assert label.label_quality == "good"


def test_no_future_liquidity_and_label_quality() -> None:
    label = _label([_event("entry", 100, 1.0)])

    assert label.no_future_liquidity is True
    assert label.label_quality == "no_future_events"
    assert label.survived_horizon is False
    assert label.rug_like_drop is None


def test_sparse_and_no_price_quality() -> None:
    sparse = _label([_event("entry", 100, 1.0), _event("future", 120, 1.1)])
    no_price = _label([_event("future", 120, 1.1)])

    assert sparse.label_quality == "sparse"
    assert no_price.label_quality == "no_price"
    assert no_price.entry_price_source == "missing"


def test_future_event_counts_and_volumes() -> None:
    label = _label(
        [
            _event("entry", 100, 1.0),
            _event("buy", 110, 1.1, "possible_buy", "a", base_qty=2, quote_qty=3),
            _event("sell", 120, 1.2, "possible_sell", "b", base_qty=4, quote_qty=5),
            _event("acc", 130, 1.3, "token_accumulation", "a", base_qty=6, quote_qty=None),
            _event("dist", 140, 1.4, "token_distribution", None, base_qty=8, quote_qty=None),
        ]
    )

    assert label.future_event_count == 4
    assert label.future_possible_buy_count == 1
    assert label.future_possible_sell_count == 1
    assert label.future_token_accumulation_count == 1
    assert label.future_token_distribution_count == 1
    assert label.future_unique_actor_count == 2
    assert label.future_base_volume == 20
    assert label.future_quote_volume == 8


def test_token_mints_filter_and_one_label_per_snapshot_per_horizon() -> None:
    builder = OutcomeLabelBuilder(
        horizons=[OutcomeHorizon("1m", 60), OutcomeHorizon("5m", 300)]
    )
    snapshots = [_snapshot(TOKEN, "s1"), _snapshot(OTHER_TOKEN, "s2")]
    events = [_event("entry", 100, 1.0), _event("other", 100, 1.0, token_mint=OTHER_TOKEN)]

    labels = builder.build_labels(snapshots, events, token_mints=[TOKEN])

    assert len(labels) == 2
    assert {label.token_mint for label in labels} == {TOKEN}
    assert {label.horizon_name for label in labels} == {"1m", "5m"}


def test_first_after_entry_source_when_allowed() -> None:
    builder = OutcomeLabelBuilder(
        horizons=[OutcomeHorizon(name="1m", seconds=60)],
        allow_first_after_entry=True,
    )
    events = [_event("after", 110, 1.0)]
    points = TokenPriceSeriesBuilder().build_price_points(events)

    label = builder.build_label_for_snapshot(_snapshot(), events, points, builder.horizons[0])

    assert label.entry_price_source == "first_after_snapshot"
