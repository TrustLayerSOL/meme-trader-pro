from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_builder import ResearchDatasetBuilder


def _snapshot(snapshot_id: str = "snapshot-1", token_mint: str = "mint-1") -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        token_mint=token_mint,
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        age_sec=30,
        venue="unknown",
        event_count=3,
        possible_buy_count=2,
        possible_sell_count=1,
        base_volume=10,
        quote_volume=2,
        venue_counts={"unknown": 3},
        event_type_counts={"possible_buy": 2, "possible_sell": 1},
        metadata_json={"feature": True},
    )


def _label(
    outcome_id: str = "outcome-1",
    snapshot_id: str = "snapshot-1",
    token_mint: str = "mint-1",
    horizon_name: str = "1m",
    quality: str = "good",
    forward_return: float | None = 0.2,
) -> OutcomeLabel:
    return OutcomeLabel(
        outcome_id=outcome_id,
        snapshot_id=snapshot_id,
        token_mint=token_mint,
        snapshot_ts=100,
        horizon_name=horizon_name,
        horizon_seconds=60,
        entry_price=1.0,
        forward_return=forward_return,
        label_quality=quality,
        metadata_json={"outcome": True},
    )


def test_joins_matching_snapshot_to_outcome_and_copies_fields() -> None:
    row = ResearchDatasetBuilder().join_snapshots_to_outcomes([_snapshot()], [_label()])[0]
    assert row.snapshot_id == "snapshot-1"
    assert row.outcome_id == "outcome-1"
    assert row.event_count == 3
    assert row.possible_buy_count == 2
    assert row.entry_price == 1.0
    assert row.forward_return == 0.2
    assert row.venue_counts == {"unknown": 3}
    assert row.event_type_counts == {"possible_buy": 2, "possible_sell": 1}
    assert row.feature_metadata_json == {"feature": True}
    assert row.outcome_metadata_json == {"outcome": True}
    assert row.metadata_json["builder_version"] == "research_dataset_builder_v0"


def test_does_not_join_nonmatching_token_mint() -> None:
    rows = ResearchDatasetBuilder().join_snapshots_to_outcomes([_snapshot()], [_label(token_mint="other")])
    assert rows == []


def test_creates_one_row_per_horizon() -> None:
    rows = ResearchDatasetBuilder().join_snapshots_to_outcomes(
        [_snapshot()],
        [_label("outcome-1", horizon_name="1m"), _label("outcome-2", horizon_name="5m")],
    )
    assert len(rows) == 2
    assert {row.horizon_name for row in rows} == {"1m", "5m"}


def test_filters_by_token_window_horizon_quality_and_requirements() -> None:
    builder = ResearchDatasetBuilder()
    rows = builder.join_snapshots_to_outcomes(
        [_snapshot(), _snapshot("snapshot-2", token_mint="mint-2")],
        [
            _label("outcome-1", quality="good"),
            _label("outcome-2", snapshot_id="snapshot-2", token_mint="mint-2", quality="sparse", forward_return=None),
        ],
    )
    filtered = builder.filter_rows(
        rows,
        token_mints=["mint-1"],
        window_names=["1m"],
        horizon_names=["1m"],
        min_label_quality="sparse",
        require_entry_price=True,
        require_forward_return=True,
    )
    assert len(filtered) == 1
    assert filtered[0].token_mint == "mint-1"


def test_unknown_label_quality_ranks_lowest() -> None:
    builder = ResearchDatasetBuilder()
    rows = builder.join_snapshots_to_outcomes([_snapshot()], [_label(quality="unknown")])
    assert builder.filter_rows(rows, min_label_quality="no_price") == []
