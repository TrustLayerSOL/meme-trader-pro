from datetime import datetime
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.launch_regime.builder import LaunchRegimeBuilder


PACIFIC = ZoneInfo("America/Los_Angeles")


def _candidate() -> LaunchCandidate:
    return LaunchCandidate(
        token_mint="token-1",
        source="test",
        first_seen_ts=datetime(2026, 6, 1, 6, 0, tzinfo=PACIFIC),
        first_tradeable_ts=datetime(2026, 6, 1, 6, 0, tzinfo=PACIFIC),
        venue="pumpswap",
        pool_address="pool-1",
        liquidity_usd=20_000,
    )


def test_launch_regime_candidate_stores_local_time_fields() -> None:
    launch = LaunchRegimeBuilder().candidate_to_launch(_candidate())

    assert launch is not None
    assert launch.launch_weekday == "Monday"
    assert launch.launch_hour_local == 6
    assert launch.launch_minute_local == 0
    assert launch.launch_day_of_week == 0
    assert launch.launch_is_weekend is False
    assert launch.launch_regime == "mon_tue_wed_0600_1200_pt"


def test_launch_snapshots_store_launch_age_seconds() -> None:
    builder = LaunchRegimeBuilder()
    launch = builder.candidate_to_launch(_candidate())
    events = [
        NormalizedEvent(
            event_id="e1",
            signature="sig-1",
            slot=1,
            block_time=launch.launch_ts + 30,
            event_type="possible_buy",
            token_mint="token-1",
            actor="wallet-1",
            side="buy",
            price_quote=1.0,
            metadata_json={"confidence": 0.8},
        ),
        NormalizedEvent(
            event_id="e2",
            signature="sig-2",
            slot=2,
            block_time=launch.launch_ts + 300,
            event_type="possible_sell",
            token_mint="token-1",
            actor="wallet-2",
            side="sell",
            price_quote=1.5,
            metadata_json={"confidence": 0.7},
        ),
    ]

    snapshots = builder.build_snapshots([launch], events)
    by_age = {snapshot.launch_age_seconds: snapshot for snapshot in snapshots}

    assert by_age[30].launch_age_seconds == 30
    assert by_age[300].launch_age_seconds == 300
    assert by_age[300].launch_hour_local == 6
    assert by_age[300].buy_count == 1
    assert by_age[300].sell_count == 1
    assert by_age[300].price_change_since_launch == 0.5


def test_launch_outcomes_store_interval_returns_and_survival() -> None:
    builder = LaunchRegimeBuilder()
    launch = builder.candidate_to_launch(_candidate())
    events = [
        NormalizedEvent(
            event_id="e1",
            signature="sig-1",
            slot=1,
            block_time=launch.launch_ts + 30,
            event_type="possible_buy",
            token_mint="token-1",
            price_quote=1.0,
        ),
        NormalizedEvent(
            event_id="e2",
            signature="sig-2",
            slot=2,
            block_time=launch.launch_ts + 7200,
            event_type="possible_buy",
            token_mint="token-1",
            price_quote=2.0,
        ),
    ]

    outcome = builder.build_outcomes([launch], events)[0]

    assert outcome.returns["return_120m"] == 1.0
    assert outcome.runups["max_runup_120m"] == 1.0
    assert outcome.survived_120m is True
    assert outcome.died_within_120m is False


def test_event_inferred_launches_include_requested_local_fields() -> None:
    event_ts = int(datetime(2026, 6, 1, 17, 30, tzinfo=PACIFIC).timestamp())
    launches = LaunchRegimeBuilder().build_event_inferred_launches(
        [
            NormalizedEvent(
                event_id="e1",
                signature="sig-1",
                slot=1,
                block_time=event_ts,
                event_type="possible_buy",
                token_mint="token-2",
                venue="pumpswap",
            )
        ]
    )

    assert len(launches) == 1
    assert launches[0].launch_weekday == "Monday"
    assert launches[0].launch_hour_local == 17
    assert launches[0].launch_minute_local == 30
    assert launches[0].source == "normalized_event_first_seen"
