"""Build local token price series from normalized events."""

from __future__ import annotations

from collections import defaultdict

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_models import TokenPricePoint


class TokenPriceSeriesBuilder:
    """Extract v0 price proxy points from normalized events."""

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
        prior_points = [point for point in sorted_points if point.ts <= snapshot_ts]
        if prior_points:
            latest_prior = prior_points[-1]
            if snapshot_ts - latest_prior.ts <= max_staleness_sec:
                return latest_prior

        if allow_first_after:
            for point in sorted_points:
                if point.ts > snapshot_ts:
                    return point
        return None

    def get_forward_points(
        self,
        token_points: list[TokenPricePoint],
        snapshot_ts: int,
        horizon_seconds: int,
    ) -> list[TokenPricePoint]:
        horizon_end = snapshot_ts + horizon_seconds
        return [
            point
            for point in sorted(token_points, key=lambda point: point.ts)
            if point.ts > snapshot_ts and point.ts <= horizon_end
        ]


def _confidence(event: NormalizedEvent) -> float | None:
    value = event.metadata_json.get("confidence")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
