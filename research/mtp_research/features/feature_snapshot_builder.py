"""Rolling feature snapshot builder for normalized trade events."""

from __future__ import annotations

from collections import Counter, defaultdict

from research.mtp_research.features.feature_models import (
    FeatureSnapshot,
    FeatureWindow,
    make_snapshot_id,
)
from research.mtp_research.ingestion.normalization_models import NormalizedEvent


class FeatureSnapshotBuilder:
    """Build deterministic token-level rolling-window feature snapshots."""

    def __init__(self, windows: list[FeatureWindow] | None = None):
        self.windows = windows or self.default_windows()

    @staticmethod
    def default_windows() -> list[FeatureWindow]:
        return [
            FeatureWindow(name="1m", seconds=60),
            FeatureWindow(name="5m", seconds=300),
            FeatureWindow(name="15m", seconds=900),
        ]

    def group_events_by_token(
        self,
        events: list[NormalizedEvent],
    ) -> dict[str, list[NormalizedEvent]]:
        grouped: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in events:
            if event.token_mint:
                grouped[event.token_mint].append(event)
        return {
            token_mint: sorted(token_events, key=lambda event: event.block_time or 0)
            for token_mint, token_events in grouped.items()
        }

    def get_token_first_seen_ts(self, events: list[NormalizedEvent]) -> dict[str, int]:
        first_seen: dict[str, int] = {}
        for event in events:
            if not event.token_mint or event.block_time is None:
                continue
            current = first_seen.get(event.token_mint)
            if current is None or event.block_time < current:
                first_seen[event.token_mint] = event.block_time
        return first_seen

    def build_snapshot_for_token(
        self,
        token_mint: str,
        events: list[NormalizedEvent],
        snapshot_ts: int,
        window: FeatureWindow,
        first_seen_ts: int | None = None,
    ) -> FeatureSnapshot:
        missing_block_time_count = sum(1 for event in events if event.block_time is None)
        window_start = snapshot_ts - window.seconds
        included = [
            event
            for event in events
            if event.token_mint == token_mint
            and event.block_time is not None
            and event.block_time <= snapshot_ts
            and event.block_time > window_start
        ]

        possible_buy_count = _count_type(included, "possible_buy")
        possible_sell_count = _count_type(included, "possible_sell")
        token_accumulation_count = _count_type(included, "token_accumulation")
        token_distribution_count = _count_type(included, "token_distribution")

        base_volume = sum(abs(event.base_qty or 0.0) for event in included)
        quote_volume = sum(abs(event.quote_qty or 0.0) for event in included)
        net_base_flow = sum(_signed_base_flow(event) for event in included)
        net_quote_flow = sum(_signed_quote_flow(event) for event in included)

        buy_sell_total = possible_buy_count + possible_sell_count
        buy_sell_imbalance = (
            (possible_buy_count - possible_sell_count) / max(buy_sell_total, 1)
        )

        confidences = [_confidence(event) for event in included]
        confidence_weighted_buy_flow = sum(
            abs(event.base_qty or 0.0) * _confidence(event)
            for event in included
            if event.event_type == "possible_buy"
        )
        confidence_weighted_sell_flow = sum(
            abs(event.base_qty or 0.0) * _confidence(event)
            for event in included
            if event.event_type == "possible_sell"
        )
        venue_counts = Counter(event.venue or "unknown" for event in included)
        event_type_counts = Counter(event.event_type for event in included)

        return FeatureSnapshot(
            snapshot_id=make_snapshot_id(token_mint, snapshot_ts, window.name),
            token_mint=token_mint,
            snapshot_ts=snapshot_ts,
            window_name=window.name,
            window_seconds=window.seconds,
            age_sec=(snapshot_ts - first_seen_ts) if first_seen_ts is not None else None,
            venue=_dominant_venue(venue_counts),
            event_count=len(included),
            possible_buy_count=possible_buy_count,
            possible_sell_count=possible_sell_count,
            token_accumulation_count=token_accumulation_count,
            token_distribution_count=token_distribution_count,
            unique_actor_count=len({event.actor for event in included if event.actor}),
            base_volume=base_volume,
            quote_volume=quote_volume,
            net_base_flow=net_base_flow,
            net_quote_flow=net_quote_flow,
            buy_sell_imbalance=buy_sell_imbalance,
            confidence_weighted_buy_flow=confidence_weighted_buy_flow,
            confidence_weighted_sell_flow=confidence_weighted_sell_flow,
            confidence_weighted_net_flow=(
                confidence_weighted_buy_flow - confidence_weighted_sell_flow
            ),
            avg_event_confidence=(
                sum(confidences) / len(confidences) if confidences else None
            ),
            max_event_confidence=max(confidences) if confidences else None,
            venue_counts=dict(sorted(venue_counts.items())),
            event_type_counts=dict(sorted(event_type_counts.items())),
            metadata_json={"missing_block_time_count": missing_block_time_count},
        )

    def build_snapshots(
        self,
        events: list[NormalizedEvent],
        snapshot_times: list[int] | None = None,
        token_mints: list[str] | None = None,
    ) -> list[FeatureSnapshot]:
        grouped = self.group_events_by_token(events)
        first_seen = self.get_token_first_seen_ts(events)
        selected_tokens = token_mints or sorted(grouped.keys())

        if snapshot_times is None:
            snapshot_times = sorted(
                {
                    event.block_time
                    for event in events
                    if event.block_time is not None
                    and (not token_mints or event.token_mint in token_mints)
                }
            )

        snapshots: list[FeatureSnapshot] = []
        for token_mint in selected_tokens:
            token_events = grouped.get(token_mint, [])
            for snapshot_ts in snapshot_times:
                for window in self.windows:
                    snapshots.append(
                        self.build_snapshot_for_token(
                            token_mint=token_mint,
                            events=token_events,
                            snapshot_ts=snapshot_ts,
                            window=window,
                            first_seen_ts=first_seen.get(token_mint),
                        )
                    )
        return snapshots


def _count_type(events: list[NormalizedEvent], event_type: str) -> int:
    return sum(1 for event in events if event.event_type == event_type)


def _confidence(event: NormalizedEvent) -> float:
    value = event.metadata_json.get("confidence", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _signed_base_flow(event: NormalizedEvent) -> float:
    amount = abs(event.base_qty or 0.0)
    if event.event_type in {"possible_buy", "token_accumulation"}:
        return amount
    if event.event_type in {"possible_sell", "token_distribution"}:
        return -amount
    return 0.0


def _signed_quote_flow(event: NormalizedEvent) -> float:
    amount = abs(event.quote_qty or 0.0)
    if event.event_type == "possible_sell":
        return amount
    if event.event_type == "possible_buy":
        return -amount
    return 0.0


def _dominant_venue(venue_counts: Counter[str]) -> str | None:
    if not venue_counts:
        return None
    return max(venue_counts.items(), key=lambda item: (item[1], item[0]))[0]
