import pytest

from research.mtp_research.features.feature_models import FeatureWindow
from research.mtp_research.features.feature_snapshot_builder import FeatureSnapshotBuilder
from research.mtp_research.ingestion.normalization_models import NormalizedEvent


TOKEN = "mint-1"
OTHER_TOKEN = "mint-2"


def _event(
    event_id: str,
    event_type: str,
    block_time: int | None,
    *,
    token_mint: str = TOKEN,
    actor: str | None = "actor-1",
    base_qty: float | None = 1.0,
    quote_qty: float | None = 2.0,
    confidence: float = 0.5,
    venue: str | None = "unknown_token_swap_candidate",
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=block_time,
        event_type=event_type,
        token_mint=token_mint,
        venue=venue,
        actor=actor,
        base_qty=base_qty,
        quote_qty=quote_qty,
        metadata_json={"confidence": confidence},
    )


def _events() -> list[NormalizedEvent]:
    return [
        _event("e1", "possible_buy", 100, actor="actor-1", base_qty=10, quote_qty=2, confidence=0.7),
        _event("e2", "possible_sell", 120, actor="actor-2", base_qty=4, quote_qty=1, confidence=0.6),
        _event("e3", "token_accumulation", 130, actor="actor-1", base_qty=3, quote_qty=None, confidence=0.3),
        _event("e4", "token_distribution", 140, actor=None, base_qty=2, quote_qty=None, confidence=0.2),
        _event("e5", "possible_buy", 20, actor="old", base_qty=100, quote_qty=50, confidence=0.9),
        _event("e6", "possible_buy", 150, token_mint=OTHER_TOKEN, actor="other"),
        _event("e7", "possible_buy", None, actor="missing-time"),
    ]


def test_groups_events_by_token_mint() -> None:
    grouped = FeatureSnapshotBuilder().group_events_by_token(_events())

    assert set(grouped) == {TOKEN, OTHER_TOKEN}
    assert len(grouped[TOKEN]) == 6


def test_calculates_first_seen_ts() -> None:
    first_seen = FeatureSnapshotBuilder().get_token_first_seen_ts(_events())

    assert first_seen[TOKEN] == 20
    assert first_seen[OTHER_TOKEN] == 150


def test_builds_1m_snapshot_with_core_counts_and_window_filtering() -> None:
    snapshot = FeatureSnapshotBuilder().build_snapshot_for_token(
        token_mint=TOKEN,
        events=_events(),
        snapshot_ts=140,
        window=FeatureWindow(name="1m", seconds=60),
        first_seen_ts=20,
    )

    assert snapshot.event_count == 4
    assert snapshot.possible_buy_count == 1
    assert snapshot.possible_sell_count == 1
    assert snapshot.token_accumulation_count == 1
    assert snapshot.token_distribution_count == 1
    assert snapshot.age_sec == 120
    assert snapshot.metadata_json["missing_block_time_count"] == 1


def test_calculates_actor_volume_flow_imbalance_and_confidence_features() -> None:
    snapshot = FeatureSnapshotBuilder().build_snapshot_for_token(
        token_mint=TOKEN,
        events=_events(),
        snapshot_ts=140,
        window=FeatureWindow(name="1m", seconds=60),
        first_seen_ts=20,
    )

    assert snapshot.unique_actor_count == 2
    assert snapshot.base_volume == 19
    assert snapshot.quote_volume == 3
    assert snapshot.net_base_flow == 7
    assert snapshot.net_quote_flow == -1
    assert snapshot.buy_sell_imbalance == 0.0
    assert snapshot.confidence_weighted_buy_flow == 7.0
    assert snapshot.confidence_weighted_sell_flow == 2.4
    assert snapshot.confidence_weighted_net_flow == 4.6
    assert snapshot.avg_event_confidence == pytest.approx(0.45)
    assert snapshot.max_event_confidence == 0.7


def test_builds_venue_and_event_type_counts() -> None:
    snapshot = FeatureSnapshotBuilder().build_snapshot_for_token(
        token_mint=TOKEN,
        events=_events(),
        snapshot_ts=140,
        window=FeatureWindow(name="1m", seconds=60),
    )

    assert snapshot.venue_counts == {"unknown_token_swap_candidate": 4}
    assert snapshot.event_type_counts == {
        "possible_buy": 1,
        "possible_sell": 1,
        "token_accumulation": 1,
        "token_distribution": 1,
    }


def test_ignores_unrelated_token_and_missing_block_time_without_crashing() -> None:
    snapshot = FeatureSnapshotBuilder().build_snapshot_for_token(
        token_mint=OTHER_TOKEN,
        events=_events(),
        snapshot_ts=150,
        window=FeatureWindow(name="1m", seconds=60),
    )

    assert snapshot.event_count == 1
    assert snapshot.possible_buy_count == 1


def test_build_snapshots_target_token_filtering() -> None:
    builder = FeatureSnapshotBuilder(windows=[FeatureWindow(name="1m", seconds=60)])
    snapshots = builder.build_snapshots(
        _events(),
        snapshot_times=[140],
        token_mints=[TOKEN],
    )

    assert len(snapshots) == 1
    assert snapshots[0].token_mint == TOKEN


def test_build_snapshots_for_token_active_windows_uses_each_tokens_own_time_range() -> None:
    builder = FeatureSnapshotBuilder(windows=[FeatureWindow(name="1m", seconds=60)])
    snapshots = builder.build_snapshots_for_token_active_windows(
        [
            _event("a1", "possible_buy", 100, token_mint=TOKEN),
            _event("a2", "possible_buy", 160, token_mint=TOKEN),
            _event("b1", "possible_buy", 1000, token_mint=OTHER_TOKEN),
        ],
        snapshot_step_sec=60,
    )

    by_token = {
        token: sorted(snapshot.snapshot_ts for snapshot in snapshots if snapshot.token_mint == token)
        for token in {TOKEN, OTHER_TOKEN}
    }
    assert by_token[TOKEN] == [100, 160]
    assert by_token[OTHER_TOKEN] == [1000]
