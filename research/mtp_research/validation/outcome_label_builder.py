"""Build future outcome labels for feature snapshots."""

from __future__ import annotations

from collections import Counter

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_models import (
    OutcomeHorizon,
    OutcomeLabel,
    TokenPricePoint,
    make_outcome_id,
)
from research.mtp_research.validation.price_series_builder import TokenPriceSeriesBuilder


class OutcomeLabelBuilder:
    """Create leakage-separated labels from local future events."""

    def __init__(
        self,
        horizons: list[OutcomeHorizon] | None = None,
        entry_max_staleness_sec: int = 60,
        allow_first_after_entry: bool = False,
        rug_drop_threshold: float = -0.7,
    ):
        self.horizons = horizons or self.default_horizons()
        self.entry_max_staleness_sec = entry_max_staleness_sec
        self.allow_first_after_entry = allow_first_after_entry
        self.rug_drop_threshold = rug_drop_threshold
        self.price_builder = TokenPriceSeriesBuilder()

    @staticmethod
    def default_horizons() -> list[OutcomeHorizon]:
        return [
            OutcomeHorizon(name="1m", seconds=60),
            OutcomeHorizon(name="5m", seconds=300),
            OutcomeHorizon(name="15m", seconds=900),
        ]

    def build_label_for_snapshot(
        self,
        snapshot: FeatureSnapshot,
        events: list[NormalizedEvent],
        token_price_points: list[TokenPricePoint],
        horizon: OutcomeHorizon,
    ) -> OutcomeLabel:
        entry_point = self.price_builder.get_entry_price(
            token_price_points,
            snapshot.snapshot_ts,
            max_staleness_sec=self.entry_max_staleness_sec,
            allow_first_after=self.allow_first_after_entry,
        )
        forward_points = self.price_builder.get_forward_points(
            token_price_points,
            snapshot.snapshot_ts,
            horizon.seconds,
        )
        future_events = _future_events(
            events,
            token_mint=snapshot.token_mint,
            snapshot_ts=snapshot.snapshot_ts,
            horizon_seconds=horizon.seconds,
        )

        entry_price_source = _entry_price_source(entry_point, snapshot.snapshot_ts)
        entry_price = entry_point.price_quote if entry_point else None
        end_point = forward_points[-1] if forward_points else None
        end_price = end_point.price_quote if end_point else None

        forward_return = None
        max_runup = None
        max_drawdown = None
        if entry_price and end_price:
            forward_return = (end_price - entry_price) / entry_price
        if entry_price and forward_points:
            returns = [(point.price_quote - entry_price) / entry_price for point in forward_points]
            max_runup = max(returns)
            max_drawdown = min(returns)

        survived_horizon = None
        if entry_point:
            near_end_ts = snapshot.snapshot_ts + horizon.seconds * 0.8
            survived_horizon = any(point.ts >= near_end_ts for point in forward_points)

        rug_like_drop = None
        if max_drawdown is not None:
            rug_like_drop = max_drawdown <= self.rug_drop_threshold

        event_type_counts = Counter(event.event_type for event in future_events)
        outcome = OutcomeLabel(
            outcome_id=make_outcome_id(snapshot.snapshot_id, horizon.name),
            snapshot_id=snapshot.snapshot_id,
            token_mint=snapshot.token_mint,
            snapshot_ts=snapshot.snapshot_ts,
            horizon_name=horizon.name,
            horizon_seconds=horizon.seconds,
            entry_price=entry_price,
            entry_price_ts=entry_point.ts if entry_point else None,
            entry_price_source=entry_price_source,
            end_price=end_price,
            end_price_ts=end_point.ts if end_point else None,
            forward_return=forward_return,
            max_runup=max_runup,
            max_drawdown=max_drawdown,
            price_points_count=len(forward_points),
            future_event_count=len(future_events),
            future_possible_buy_count=event_type_counts["possible_buy"],
            future_possible_sell_count=event_type_counts["possible_sell"],
            future_token_accumulation_count=event_type_counts["token_accumulation"],
            future_token_distribution_count=event_type_counts["token_distribution"],
            future_unique_actor_count=len({event.actor for event in future_events if event.actor}),
            future_quote_volume=sum(abs(event.quote_qty or 0.0) for event in future_events),
            future_base_volume=sum(abs(event.base_qty or 0.0) for event in future_events),
            survived_horizon=survived_horizon,
            rug_like_drop=rug_like_drop,
            no_future_liquidity=len(forward_points) == 0,
            label_quality=_label_quality(entry_point, len(forward_points)),
            metadata_json={
                "parser_version": "outcome_labeler_v0",
                "entry_max_staleness_sec": self.entry_max_staleness_sec,
                "allow_first_after_entry": self.allow_first_after_entry,
                "rug_drop_threshold": self.rug_drop_threshold,
                "price_points_count": len(forward_points),
                "source_snapshot_window_name": snapshot.window_name,
                "source_snapshot_window_seconds": snapshot.window_seconds,
            },
        )
        return outcome

    def build_labels(
        self,
        snapshots: list[FeatureSnapshot],
        events: list[NormalizedEvent],
        token_mints: list[str] | None = None,
    ) -> list[OutcomeLabel]:
        selected_mints = set(token_mints or [])
        filtered_snapshots = [
            snapshot
            for snapshot in snapshots
            if not selected_mints or snapshot.token_mint in selected_mints
        ]
        price_points = self.price_builder.build_price_points(events)
        points_by_token = self.price_builder.group_by_token(price_points)

        labels: list[OutcomeLabel] = []
        for snapshot in filtered_snapshots:
            token_points = points_by_token.get(snapshot.token_mint, [])
            for horizon in self.horizons:
                labels.append(
                    self.build_label_for_snapshot(
                        snapshot=snapshot,
                        events=events,
                        token_price_points=token_points,
                        horizon=horizon,
                    )
                )
        return labels


def _future_events(
    events: list[NormalizedEvent],
    token_mint: str,
    snapshot_ts: int,
    horizon_seconds: int,
) -> list[NormalizedEvent]:
    horizon_end = snapshot_ts + horizon_seconds
    return [
        event
        for event in events
        if event.token_mint == token_mint
        and event.block_time is not None
        and event.block_time > snapshot_ts
        and event.block_time <= horizon_end
    ]


def _entry_price_source(entry_point: TokenPricePoint | None, snapshot_ts: int) -> str:
    if entry_point is None:
        return "missing"
    if entry_point.ts == snapshot_ts:
        return "exact_snapshot"
    if entry_point.ts < snapshot_ts:
        return "last_before_snapshot"
    return "first_after_snapshot"


def _label_quality(entry_point: TokenPricePoint | None, forward_price_count: int) -> str:
    if entry_point is None:
        return "no_price"
    if forward_price_count >= 3:
        return "good"
    if forward_price_count >= 1:
        return "sparse"
    if forward_price_count == 0:
        return "no_future_events"
    return "unknown"
