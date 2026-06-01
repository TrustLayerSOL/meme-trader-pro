"""Build launch-relative early lifecycle datasets from registry and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow
from research.mtp_research.launch_regime.models import (
    LaunchFeatureSnapshot,
    LaunchOutcomeLabel,
    LaunchRegimeCandidate,
    make_launch_id,
    make_outcome_id,
    make_snapshot_id,
    utc_iso_from_ts,
)
from research.mtp_research.validation.launch_timestamp_confidence import (
    confidence_rank,
    classify_launch_timestamp_source,
    is_verified_launch_timestamp,
)


PACIFIC = ZoneInfo("America/Los_Angeles")
SNAPSHOT_AGES = [30, 60, 120, 180, 300, 600, 1200, 1800, 2700, 3600, 5400, 7200]
INTERVAL_SECONDS = [60, 120, 180, 300, 600, 1800, 2700, 3600, 5400, 7200]
TRADE_TYPES = {"possible_buy", "possible_sell", "token_accumulation", "token_distribution"}


@dataclass
class LaunchRegimeConfig:
    weekdays: set[int] = field(default_factory=lambda: {0, 1, 2})
    windows: list[tuple[int, int]] = field(default_factory=lambda: [(6 * 3600, 12 * 3600), (17 * 3600, 22 * 3600)])
    max_lifecycle_seconds: int = 7200


class LaunchRegimeBuilder:
    def __init__(self, config: LaunchRegimeConfig | None = None):
        self.config = config or LaunchRegimeConfig()

    def candidate_to_launch(self, candidate: LaunchCandidate) -> LaunchRegimeCandidate | None:
        launch_dt = candidate.first_tradeable_ts or candidate.first_seen_ts
        if launch_dt.tzinfo is None:
            launch_dt = launch_dt.replace(tzinfo=PACIFIC)
        launch_ts = int(launch_dt.timestamp())
        local = launch_dt.astimezone(PACIFIC)
        seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
        in_window = any(start <= seconds_since_midnight <= end for start, end in self.config.windows)
        if local.weekday() not in self.config.weekdays or not in_window:
            return None
        launch_id = make_launch_id(candidate.token_mint, launch_ts)
        timestamp_source = classify_launch_timestamp_source(candidate.to_dict())
        return LaunchRegimeCandidate(
            launch_id=launch_id,
            token_mint=candidate.token_mint,
            pool_address=candidate.pool_address,
            venue=candidate.venue,
            launch_ts=launch_ts,
            launch_time_utc=utc_iso_from_ts(launch_ts),
            launch_weekday=local.strftime("%A"),
            launch_hour_local=local.hour,
            launch_minute_local=local.minute,
            launch_day_of_week=local.weekday(),
            launch_is_weekend=local.weekday() >= 5,
            launch_regime=self._launch_regime_name(local),
            source=candidate.source,
            liquidity_usd=candidate.liquidity_usd,
            market_cap=candidate.market_cap,
            launch_timestamp_source=timestamp_source,
            launch_timestamp_confidence=confidence_rank(timestamp_source),
            launch_timestamp_verified=is_verified_launch_timestamp(timestamp_source),
            metadata_json={
                "dexscreener_url": candidate.dexscreener_url,
                "candidate_metadata": candidate.metadata_json,
            },
        )

    def build_launches(self, candidates: list[LaunchCandidate]) -> list[LaunchRegimeCandidate]:
        launches = [launch for candidate in candidates if (launch := self.candidate_to_launch(candidate))]
        deduped = {launch.token_mint: launch for launch in sorted(launches, key=lambda item: item.launch_ts)}
        return sorted(deduped.values(), key=lambda item: (item.launch_ts, item.token_mint))

    def census_row_to_launch(
        self,
        row: PumpFunCreationCensusRow,
        *,
        include_outside_configured_regime: bool = False,
    ) -> LaunchRegimeCandidate | None:
        if not row.accepted or not row.mint or row.block_time is None:
            return None
        local = datetime.fromtimestamp(int(row.block_time), tz=PACIFIC)
        seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
        in_window = any(start <= seconds_since_midnight <= end for start, end in self.config.windows)
        if not include_outside_configured_regime and (
            local.weekday() not in self.config.weekdays or not in_window
        ):
            return None
        timestamp_source = classify_launch_timestamp_source(
            {"metadata_json": {"launch_timestamp_quality": "verified_pair_creation"}}
        )
        launch_ts = int(row.block_time)
        return LaunchRegimeCandidate(
            launch_id=make_launch_id(row.mint, launch_ts),
            token_mint=row.mint,
            pool_address=row.bonding_curve,
            venue="pumpfun",
            launch_ts=launch_ts,
            launch_time_utc=utc_iso_from_ts(launch_ts),
            launch_weekday=local.strftime("%A"),
            launch_hour_local=local.hour,
            launch_minute_local=local.minute,
            launch_day_of_week=local.weekday(),
            launch_is_weekend=local.weekday() >= 5,
            launch_regime=self._launch_regime_name(local),
            source=row.source_method,
            launch_timestamp_source=timestamp_source,
            launch_timestamp_confidence=confidence_rank(timestamp_source),
            launch_timestamp_verified=is_verified_launch_timestamp(timestamp_source),
            metadata_json={
                "creation_signature": row.creation_signature,
                "creator_deployer": row.creator_deployer,
                "slot": row.slot,
                "parser_confidence": row.parser_confidence,
                "instruction_type": row.instruction_type,
                "bonding_curve": row.bonding_curve,
                "associated_bonding_curve": row.associated_bonding_curve,
                "instruction_index": row.instruction_index,
                "instruction_discriminator": row.instruction_discriminator,
                "census_metadata": row.metadata_json,
            },
        )

    def build_launches_from_pumpfun_census(
        self,
        rows: list[PumpFunCreationCensusRow],
        *,
        include_outside_configured_regime: bool = False,
    ) -> list[LaunchRegimeCandidate]:
        launches = [
            launch
            for row in rows
            if (
                launch := self.census_row_to_launch(
                    row,
                    include_outside_configured_regime=include_outside_configured_regime,
                )
            )
        ]
        deduped = {launch.token_mint: launch for launch in sorted(launches, key=lambda item: item.launch_ts)}
        return sorted(deduped.values(), key=lambda item: (item.launch_ts, item.token_mint))

    def build_event_inferred_launches(self, events: list[NormalizedEvent]) -> list[LaunchRegimeCandidate]:
        first_by_token: dict[str, NormalizedEvent] = {}
        for event in sorted(events, key=lambda item: (item.block_time or 0, item.signature, item.event_id)):
            if not event.token_mint or event.block_time is None or event.event_type not in TRADE_TYPES:
                continue
            first_by_token.setdefault(event.token_mint, event)

        launches: list[LaunchRegimeCandidate] = []
        for token, event in first_by_token.items():
            launch_dt = datetime.fromtimestamp(event.block_time or 0, tz=PACIFIC)
            local = launch_dt.astimezone(PACIFIC)
            seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
            in_window = any(start <= seconds_since_midnight <= end for start, end in self.config.windows)
            if local.weekday() not in self.config.weekdays or not in_window:
                continue
            launch_id = make_launch_id(token, int(event.block_time or 0))
            timestamp_source = classify_launch_timestamp_source(
                {
                    "source": "normalized_event_first_seen",
                    "metadata_json": {"launch_timestamp_quality": "first_observed_event_not_verified_pair_creation"},
                }
            )
            launches.append(
                LaunchRegimeCandidate(
                    launch_id=launch_id,
                    token_mint=token,
                    launch_ts=int(event.block_time or 0),
                    launch_time_utc=utc_iso_from_ts(int(event.block_time or 0)),
                    launch_weekday=local.strftime("%A"),
                    launch_hour_local=local.hour,
                    launch_minute_local=local.minute,
                    launch_day_of_week=local.weekday(),
                    launch_is_weekend=local.weekday() >= 5,
                    launch_regime=self._launch_regime_name(local),
                    source="normalized_event_first_seen",
                    venue=event.venue,
                    launch_timestamp_source=timestamp_source,
                    launch_timestamp_confidence=confidence_rank(timestamp_source),
                    launch_timestamp_verified=is_verified_launch_timestamp(timestamp_source),
                    metadata_json={
                        "first_seen_signature": event.signature,
                        "launch_timestamp_quality": "first_observed_event_not_verified_pair_creation",
                        "source_event_id": event.event_id,
                    },
                )
            )
        return sorted(launches, key=lambda item: (item.launch_ts, item.token_mint))

    def build_snapshots(
        self,
        launches: list[LaunchRegimeCandidate],
        events: list[NormalizedEvent],
    ) -> list[LaunchFeatureSnapshot]:
        events_by_token = _events_by_token(events)
        snapshots: list[LaunchFeatureSnapshot] = []
        for launch in launches:
            token_events = _lifecycle_events(launch, events_by_token.get(launch.token_mint, []), self.config.max_lifecycle_seconds)
            launch_price = _first_price(token_events)
            for age in SNAPSHOT_AGES:
                window_events = [event for event in token_events if event.block_time is not None and event.block_time <= launch.launch_ts + age]
                priced = [event for event in window_events if event.price_quote is not None and event.price_quote > 0]
                last_price = priced[-1].price_quote if priced else None
                snapshots.append(
                    LaunchFeatureSnapshot(
                        snapshot_id=make_snapshot_id(launch.launch_id, age),
                        launch_id=launch.launch_id,
                        token_mint=launch.token_mint,
                        pool_address=launch.pool_address,
                        venue=launch.venue,
                        launch_regime=launch.launch_regime,
                        launch_ts=launch.launch_ts,
                        snapshot_ts=launch.launch_ts + age,
                        launch_age_seconds=age,
                        launch_weekday=launch.launch_weekday,
                        launch_hour_local=launch.launch_hour_local,
                        launch_minute_local=launch.launch_minute_local,
                        launch_day_of_week=launch.launch_day_of_week,
                        launch_is_weekend=launch.launch_is_weekend,
                        launch_timestamp_source=launch.launch_timestamp_source,
                        launch_timestamp_confidence=launch.launch_timestamp_confidence,
                        launch_timestamp_verified=launch.launch_timestamp_verified,
                        buy_count=sum(1 for event in window_events if event.side in {"buy", "accumulate"}),
                        sell_count=sum(1 for event in window_events if event.side in {"sell", "distribution"}),
                        buy_sell_imbalance=sum(1 for event in window_events if event.side in {"buy", "accumulate"})
                        - sum(1 for event in window_events if event.side in {"sell", "distribution"}),
                        unique_actors=len({event.actor for event in window_events if event.actor}),
                        active_wallets=len({event.actor for event in window_events if event.actor}),
                        confidence_weighted_net_flow=_confidence_weighted_net_flow(window_events),
                        price_change_since_launch=_return(launch_price, last_price),
                        tx_count=len({event.signature for event in window_events}),
                        liquidity_proxy=_liquidity_proxy(priced),
                        metadata_json={"event_count": len(window_events), "priced_event_count": len(priced)},
                    )
                )
        return snapshots

    def build_outcomes(
        self,
        launches: list[LaunchRegimeCandidate],
        events: list[NormalizedEvent],
    ) -> list[LaunchOutcomeLabel]:
        events_by_token = _events_by_token(events)
        outcomes: list[LaunchOutcomeLabel] = []
        for launch in launches:
            token_events = _lifecycle_events(launch, events_by_token.get(launch.token_mint, []), self.config.max_lifecycle_seconds)
            priced = [event for event in token_events if event.price_quote is not None and event.price_quote > 0]
            launch_price = _first_price(token_events)
            returns = {}
            runups = {}
            drawdowns = {}
            for seconds in INTERVAL_SECONDS:
                interval_prices = [
                    event.price_quote
                    for event in priced
                    if event.block_time is not None and event.block_time <= launch.launch_ts + seconds
                ]
                end_price = interval_prices[-1] if interval_prices else None
                returns[f"return_{seconds // 60}m"] = _return(launch_price, end_price)
                runups[f"max_runup_{seconds // 60}m"] = _max_runup(launch_price, interval_prices)
                drawdowns[f"max_drawdown_{seconds // 60}m"] = _max_drawdown(launch_price, interval_prices)
            last_age = max((event.block_time or 0) - launch.launch_ts for event in token_events) if token_events else 0
            market_cap_values = [
                launch.market_cap,
                *[
                    _float_or_none(event.metadata_json.get("market_cap"))
                    for event in token_events
                    if event.metadata_json
                ],
            ]
            max_market_cap = max([value for value in market_cap_values if value is not None], default=None)
            outcomes.append(
                LaunchOutcomeLabel(
                    outcome_id=make_outcome_id(launch.launch_id),
                    launch_id=launch.launch_id,
                    token_mint=launch.token_mint,
                    pool_address=launch.pool_address,
                    venue=launch.venue,
                    launch_regime=launch.launch_regime,
                    launch_ts=launch.launch_ts,
                    launch_weekday=launch.launch_weekday,
                    launch_hour_local=launch.launch_hour_local,
                    launch_minute_local=launch.launch_minute_local,
                    launch_day_of_week=launch.launch_day_of_week,
                    launch_is_weekend=launch.launch_is_weekend,
                    launch_timestamp_source=launch.launch_timestamp_source,
                    launch_timestamp_confidence=launch.launch_timestamp_confidence,
                    launch_timestamp_verified=launch.launch_timestamp_verified,
                    returns=returns,
                    runups=runups,
                    drawdowns=drawdowns,
                    survived_10m=last_age >= 600,
                    survived_30m=last_age >= 1800,
                    survived_60m=last_age >= 3600,
                    survived_120m=last_age >= 7200,
                    no_future_liquidity=not bool(token_events),
                    died_within_10m=last_age < 600,
                    died_within_30m=last_age < 1800,
                    died_within_60m=last_age < 3600,
                    died_within_120m=last_age < 7200,
                    ever_hit_15k=_hit_market_cap(max_market_cap, 15_000),
                    ever_hit_35k=_hit_market_cap(max_market_cap, 35_000),
                    ever_hit_50k=_hit_market_cap(max_market_cap, 50_000),
                    ever_hit_100k=_hit_market_cap(max_market_cap, 100_000),
                    metadata_json={
                        "priced_event_count": len(priced),
                        "market_cap_available": max_market_cap is not None,
                    },
                )
            )
        return outcomes

    def _launch_regime_name(self, local: datetime) -> str:
        hour_seconds = local.hour * 3600 + local.minute * 60 + local.second
        if 6 * 3600 <= hour_seconds <= 12 * 3600:
            return "mon_tue_wed_0600_1200_pt"
        if 17 * 3600 <= hour_seconds <= 22 * 3600:
            return "mon_tue_wed_1700_2200_pt"
        return "outside_configured_regime"


def _events_by_token(events: list[NormalizedEvent]) -> dict[str, list[NormalizedEvent]]:
    output: dict[str, list[NormalizedEvent]] = {}
    for event in events:
        if not event.token_mint or event.block_time is None or event.event_type not in TRADE_TYPES:
            continue
        output.setdefault(event.token_mint, []).append(event)
    for token_events in output.values():
        token_events.sort(key=lambda event: (event.block_time or 0, event.signature, event.event_id))
    return output


def _lifecycle_events(
    launch: LaunchRegimeCandidate,
    events: list[NormalizedEvent],
    max_lifecycle_seconds: int,
) -> list[NormalizedEvent]:
    return [
        event for event in events
        if event.block_time is not None
        and launch.launch_ts <= event.block_time <= launch.launch_ts + max_lifecycle_seconds
    ]


def _first_price(events: list[NormalizedEvent]) -> float | None:
    for event in events:
        if event.price_quote is not None and event.price_quote > 0:
            return event.price_quote
    return None


def _return(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start <= 0:
        return None
    return (end - start) / start


def _max_runup(start: float | None, prices: list[float]) -> float | None:
    if start is None or start <= 0 or not prices:
        return None
    return (max(prices) - start) / start


def _max_drawdown(start: float | None, prices: list[float]) -> float | None:
    if start is None or start <= 0 or not prices:
        return None
    return (min(prices) - start) / start


def _confidence_weighted_net_flow(events: list[NormalizedEvent]) -> float:
    total = 0.0
    for event in events:
        confidence = _float_or_none(event.metadata_json.get("confidence")) if event.metadata_json else None
        weight = confidence if confidence is not None else 1.0
        if event.side in {"buy", "accumulate"}:
            total += weight
        elif event.side in {"sell", "distribution"}:
            total -= weight
    return total


def _liquidity_proxy(priced_events: list[NormalizedEvent]) -> float | None:
    quotes = [event.quote_qty for event in priced_events if event.quote_qty is not None]
    return sum(abs(value) for value in quotes) if quotes else None


def _hit_market_cap(value: float | None, threshold: float) -> bool | None:
    if value is None:
        return None
    return value >= threshold


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
