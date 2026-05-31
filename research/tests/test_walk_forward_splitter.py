from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import WalkForwardConfig
from research.mtp_research.validation.walk_forward_splitter import WalkForwardSplitter


def _row(row_id: str, snapshot_ts: int) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        forward_return=0.1,
        label_quality="sparse",
    )


def _config(gap_seconds: int = 0) -> WalkForwardConfig:
    return WalkForwardConfig(
        config_id="cfg",
        train_window_seconds=10,
        test_window_seconds=5,
        step_seconds=5,
        gap_seconds=gap_seconds,
    )


def test_get_time_bounds_handles_empty_rows() -> None:
    assert WalkForwardSplitter(_config()).get_time_bounds([]) is None


def test_generates_chronological_folds_with_correct_boundaries() -> None:
    rows = [_row(f"row-{ts}", ts) for ts in range(0, 26)]
    folds = WalkForwardSplitter(_config()).generate_folds(rows)
    assert [(fold.train_start_ts, fold.train_end_ts, fold.test_start_ts, fold.test_end_ts) for fold in folds[:2]] == [
        (0, 9, 10, 14),
        (5, 14, 15, 19),
    ]
    assert [fold.fold_index for fold in folds] == list(range(len(folds)))


def test_gap_seconds_creates_gap_between_train_and_test() -> None:
    rows = [_row(f"row-{ts}", ts) for ts in range(0, 30)]
    fold = WalkForwardSplitter(_config(gap_seconds=2)).generate_folds(rows)[0]
    assert fold.train_end_ts == 9
    assert fold.test_start_ts == 12
    assert fold.test_start_ts - fold.train_end_ts - 1 == 2


def test_rows_for_train_and_test_fold_return_only_matching_rows_sorted() -> None:
    rows = [_row("row-12", 12), _row("row-1", 1), _row("row-10", 10), _row("row-14", 14), _row("row-15", 15)]
    splitter = WalkForwardSplitter(_config())
    fold = splitter.generate_folds(rows)[0]
    assert [row.snapshot_ts for row in splitter.rows_for_train_fold(rows, fold)] == [1, 10]
    assert [row.snapshot_ts for row in splitter.rows_for_test_fold(rows, fold)] == [12, 14, 15]


def test_no_randomization_same_folds_from_unsorted_rows() -> None:
    sorted_rows = [_row(f"row-{ts}", ts) for ts in range(0, 26)]
    unsorted_rows = list(reversed(sorted_rows))
    splitter = WalkForwardSplitter(_config())
    assert [fold.to_dict() for fold in splitter.generate_folds(sorted_rows)] == [
        fold.to_dict() for fold in splitter.generate_folds(unsorted_rows)
    ]


def test_handles_insufficient_range_safely() -> None:
    rows = [_row("row-1", 1), _row("row-2", 2)]
    assert WalkForwardSplitter(_config()).generate_folds(rows) == []
