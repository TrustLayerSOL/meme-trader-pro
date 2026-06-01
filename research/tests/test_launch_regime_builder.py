from datetime import datetime
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow
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
    assert outcome.has_activity_at_or_after_120m is True
    assert outcome.has_price_at_120m is True
    assert outcome.price_available_120m is True
    assert outcome.has_liquidity_proxy_at_120m is False
    assert outcome.liquidity_survival_120m is False
    assert outcome.lifecycle_observed_to_120m is True
    assert outcome.survival_label_quality == "price_observed_through_120m_without_liquidity_proxy"
    assert outcome.market_cap_available is False
    assert outcome.market_cap_source is None
    assert outcome.market_cap_missing_reason == "market_cap_not_present_in_launch_or_events"
    assert outcome.threshold_outcomes_usable is False


def test_launch_outcomes_separate_price_proxy_survival_from_trade_activity() -> None:
    builder = LaunchRegimeBuilder()
    launch = builder.candidate_to_launch(_candidate())
    events = [
        NormalizedEvent(
            event_id="e1",
            signature="sig-1",
            slot=1,
            block_time=launch.launch_ts + 60,
            event_type="possible_buy",
            token_mint="token-1",
            price_quote=1.0,
            quote_qty=2.0,
        ),
    ]

    outcome = builder.build_outcomes([launch], events)[0]

    assert outcome.has_activity_at_or_after_120m is False
    assert outcome.survived_120m is False
    assert outcome.price_available_120m is True
    assert outcome.has_price_at_120m is True
    assert outcome.has_liquidity_proxy_at_120m is True
    assert outcome.liquidity_survival_120m is True
    assert outcome.lifecycle_observed_to_120m is True
    assert outcome.survival_label_quality == "liquidity_proxy_available_by_120m_no_activity_at_120m"


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


def test_build_launches_from_pumpfun_census_uses_verified_creation_time() -> None:
    launch_ts = int(datetime(2026, 6, 1, 6, 45, tzinfo=PACIFIC).timestamp())
    rows = [
        PumpFunCreationCensusRow(
            mint="mint-1",
            creator_deployer="creator-1",
            creation_signature="sig-1",
            slot=123,
            block_time=launch_ts,
            parser_confidence="high",
            instruction_type="create_v2",
            source_method="pumpfun_gtfa_census",
            accepted=True,
            bonding_curve="curve-1",
            associated_bonding_curve="assoc-curve-1",
        ),
        PumpFunCreationCensusRow(
            mint="rejected",
            creator_deployer="creator-2",
            creation_signature="sig-2",
            slot=124,
            block_time=launch_ts,
            parser_confidence="rejected",
            instruction_type="unknown",
            source_method="pumpfun_gtfa_census",
            accepted=False,
        ),
    ]

    launches = LaunchRegimeBuilder().build_launches_from_pumpfun_census(rows)

    assert len(launches) == 1
    assert launches[0].token_mint == "mint-1"
    assert launches[0].pool_address == "curve-1"
    assert launches[0].launch_timestamp_source == "verified_pair_creation"
    assert launches[0].launch_timestamp_verified is True
    assert launches[0].launch_hour_local == 6
    assert launches[0].metadata_json["creation_signature"] == "sig-1"


def test_build_launches_from_pumpfun_census_can_include_outside_configured_regime() -> None:
    launch_ts = int(datetime(2026, 6, 1, 14, 15, tzinfo=PACIFIC).timestamp())
    rows = [
        PumpFunCreationCensusRow(
            mint="mint-outside",
            creator_deployer="creator-1",
            creation_signature="sig-1",
            slot=123,
            block_time=launch_ts,
            parser_confidence="high",
            instruction_type="create_v2",
            source_method="pumpfun_gtfa_census",
            accepted=True,
            bonding_curve="curve-1",
        )
    ]

    strict = LaunchRegimeBuilder().build_launches_from_pumpfun_census(rows)
    inclusive = LaunchRegimeBuilder().build_launches_from_pumpfun_census(
        rows,
        include_outside_configured_regime=True,
    )

    assert strict == []
    assert len(inclusive) == 1
    assert inclusive[0].launch_regime == "outside_configured_regime"
