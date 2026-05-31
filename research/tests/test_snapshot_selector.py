from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.validation.snapshot_selection_models import SnapshotSelectionConfig
from research.mtp_research.validation.snapshot_selector import SnapshotSelector


def _snapshot(token: str, ts: int, window: str = "1m") -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"{token}-{ts}-{window}",
        token_mint=token,
        snapshot_ts=ts,
        window_name=window,
        window_seconds=60,
    )


def test_head_strategy_selects_first_n() -> None:
    snapshots = [_snapshot("a", ts) for ts in [100, 200, 300]]

    selected, summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="head", max_snapshots=2),
    )

    assert [snapshot.snapshot_ts for snapshot in selected] == [100, 200]
    assert summary.selected_snapshot_count == 2


def test_latest_strategy_selects_latest_n() -> None:
    snapshots = [_snapshot("a", ts) for ts in [100, 200, 300]]

    selected, _summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="latest", max_snapshots=2),
    )

    assert [snapshot.snapshot_ts for snapshot in selected] == [200, 300]


def test_full_span_even_covers_broad_timestamp_span() -> None:
    snapshots = [_snapshot("a", ts) for ts in range(0, 1000, 100)]

    selected, summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="full_span_even", max_snapshots=3),
    )

    assert selected[0].snapshot_ts == 0
    assert selected[-1].snapshot_ts == 900
    assert summary.selected_time_span_seconds == 900


def test_per_token_even_selects_from_multiple_tokens() -> None:
    snapshots = [_snapshot("a", ts) for ts in [100, 200, 300]] + [
        _snapshot("b", ts) for ts in [1000, 1100, 1200]
    ]

    selected, summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="per_token_even", max_snapshots_per_token=2),
    )

    assert summary.selected_by_token == {"a": 2, "b": 2}
    assert {snapshot.token_mint for snapshot in selected} == {"a", "b"}


def test_per_token_even_respects_max_snapshots_per_token() -> None:
    snapshots = [_snapshot("a", ts) for ts in [100, 200, 300, 400]]

    selected, summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="per_token_even", max_snapshots_per_token=2),
    )

    assert len(selected) == 2
    assert summary.selected_by_token == {"a": 2}


def test_min_time_gap_seconds_reduces_dense_duplicate_picks() -> None:
    snapshots = [_snapshot("a", ts) for ts in [0, 10, 20, 100]]

    selected, _summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(
            strategy="per_token_even",
            max_snapshots_per_token=4,
            min_time_gap_seconds=60,
        ),
    )

    assert [snapshot.snapshot_ts for snapshot in selected] == [0, 100]


def test_summary_warns_when_selected_span_is_much_smaller_than_input() -> None:
    snapshots = [_snapshot("a", ts) for ts in [0, 100, 200, 10_000]]

    _selected, summary = SnapshotSelector().select_snapshots(
        snapshots,
        SnapshotSelectionConfig(strategy="head", max_snapshots=2),
    )

    assert "selected_time_span_much_smaller_than_input" in summary.warning_flags
