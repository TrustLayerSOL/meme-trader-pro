"""Build local token price series from normalized events."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_models import TokenPricePoint


class TokenPriceSeriesBuilder:
    """Extract v0 price proxy points from normalized events."""

    def __init__(
        self,
        allow_nearest_price: bool = False,
        max_nearest_staleness_sec: int = 300,
    ):
        self.allow_nearest_price = allow_nearest_price
        self.max_nearest_staleness_sec = max_nearest_staleness_sec

    def build_price_points(self, events: list[NormalizedEvent]) -> list[TokenPricePoint]:
        points: list[TokenPricePoint] = []
        for event in events:
            if not event.token_mint or event.block_time is None:
                continue
            if event.price_quote is None or event.price_quote <= 0:
                continue
            points.append(
                TokenPricePoint(
                    token_mint=event.token_mint,
                    ts=event.block_time,
                    price_quote=event.price_quote,
                    source_event_id=event.event_id,
                    source_signature=event.signature,
                    venue=event.venue,
                    confidence=_confidence(event),
                )
            )
        return sorted(points, key=lambda point: (point.token_mint, point.ts))

    def group_by_token(
        self,
        price_points: list[TokenPricePoint],
    ) -> dict[str, list[TokenPricePoint]]:
        grouped: dict[str, list[TokenPricePoint]] = defaultdict(list)
        for point in price_points:
            grouped[point.token_mint].append(point)
        return {
            token_mint: sorted(points, key=lambda point: point.ts)
            for token_mint, points in grouped.items()
        }

    def get_entry_price(
        self,
        token_points: list[TokenPricePoint],
        snapshot_ts: int,
        max_staleness_sec: int = 60,
        allow_first_after: bool = False,
    ) -> TokenPricePoint | None:
        sorted_points = sorted(token_points, key=lambda point: point.ts)
        return self.get_entry_price_from_sorted(
            sorted_points,
            snapshot_ts,
            max_staleness_sec=max_staleness_sec,
            allow_first_after=allow_first_after,
        )

    def get_nearest_price(
        self,
        token_points: list[TokenPricePoint],
        snapshot_ts: int,
        max_staleness_sec: int,
    ) -> TokenPricePoint | None:
        sorted_points = sorted(token_points, key=lambda point: point.ts)
        return self.get_nearest_price_from_sorted(
            sorted_points,
            snapshot_ts,
            max_staleness_sec=max_staleness_sec,
        )

    def get_forward_points(
        self,
        token_points: list[TokenPricePoint],
        snapshot_ts: int,
        horizon_seconds: int,
    ) -> list[TokenPricePoint]:
        sorted_points = sorted(token_points, key=lambda point: point.ts)
        return self.get_forward_points_from_sorted(sorted_points, snapshot_ts, horizon_seconds)

    def get_entry_price_from_sorted(
        self,
        sorted_points: list[TokenPricePoint],
        snapshot_ts: int,
        max_staleness_sec: int = 60,
        allow_first_after: bool = False,
        timestamps: list[int] | None = None,
    ) -> TokenPricePoint | None:
        timestamps = timestamps if timestamps is not None else [point.ts for point in sorted_points]
        prior_index = bisect_right(timestamps, snapshot_ts) - 1
        if prior_index >= 0:
            latest_prior = sorted_points[prior_index]
            if snapshot_ts - latest_prior.ts <= max_staleness_sec:
                return latest_prior

        if allow_first_after:
            after_index = bisect_right(timestamps, snapshot_ts)
            if after_index < len(sorted_points):
                return sorted_points[after_index]
        if self.allow_nearest_price:
            return self.get_nearest_price_from_sorted(
                sorted_points,
                snapshot_ts,
                max_staleness_sec=self.max_nearest_staleness_sec,
                timestamps=timestamps,
            )
        return None

    def get_nearest_price_from_sorted(
        self,
        sorted_points: list[TokenPricePoint],
        snapshot_ts: int,
        max_staleness_sec: int,
        timestamps: list[int] | None = None,
    ) -> TokenPricePoint | None:
        timestamps = timestamps if timestamps is not None else [point.ts for point in sorted_points]
        left = bisect_left(timestamps, snapshot_ts - max_staleness_sec)
        right = bisect_right(timestamps, snapshot_ts + max_staleness_sec)
        candidates = sorted_points[left:right]
        if not candidates:
            return None
        return min(candidates, key=lambda point: (abs(point.ts - snapshot_ts), point.ts > snapshot_ts))

    def get_forward_points_from_sorted(
        self,
        sorted_points: list[TokenPricePoint],
        snapshot_ts: int,
        horizon_seconds: int,
        timestamps: list[int] | None = None,
    ) -> list[TokenPricePoint]:
        timestamps = timestamps if timestamps is not None else [point.ts for point in sorted_points]
        horizon_end = snapshot_ts + horizon_seconds
        start = bisect_right(timestamps, snapshot_ts)
        end = bisect_right(timestamps, horizon_end)
        return sorted_points[start:end]


def _confidence(event: NormalizedEvent) -> float | None:
    value = event.metadata_json.get("confidence")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
