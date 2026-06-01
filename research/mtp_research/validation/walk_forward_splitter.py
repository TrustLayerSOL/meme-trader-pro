"""Chronological fold splitter for walk-forward validation."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import (
    WalkForwardConfig,
    WalkForwardFold,
    make_fold_id,
)


class WalkForwardSplitter:
    """Create explicit chronological train/test folds from snapshot timestamps."""

    def __init__(self, config: WalkForwardConfig):
        self.config = config

    def get_time_bounds(self, rows: list[ResearchDatasetRow]) -> tuple[int, int] | None:
        if not rows:
            return None
        timestamps = [row.snapshot_ts for row in rows]
        return min(timestamps), max(timestamps)

    def generate_folds(self, rows: list[ResearchDatasetRow]) -> list[WalkForwardFold]:
        bounds = self.get_time_bounds(rows)
        if bounds is None:
            return []
        sorted_timestamps = sorted(row.snapshot_ts for row in rows)
        min_ts, max_ts = bounds
        starts = self._fold_start_timestamps(min_ts, max_ts)
        folds: list[WalkForwardFold] = []
        for fold_index, train_start_ts in enumerate(starts):
            train_end_ts = train_start_ts + self.config.train_window_seconds - 1
            test_start_ts = train_end_ts + self.config.gap_seconds + 1
            test_end_ts = test_start_ts + self.config.test_window_seconds - 1
            if test_end_ts > max_ts:
                continue
            fold = WalkForwardFold(
                fold_id=make_fold_id(self.config.config_id, fold_index),
                fold_index=fold_index,
                train_start_ts=train_start_ts,
                train_end_ts=train_end_ts,
                test_start_ts=test_start_ts,
                test_end_ts=test_end_ts,
                gap_seconds=self.config.gap_seconds,
            )
            fold.train_row_count = _count_in_window(sorted_timestamps, fold.train_start_ts, fold.train_end_ts)
            fold.test_row_count = _count_in_window(sorted_timestamps, fold.test_start_ts, fold.test_end_ts)
            folds.append(fold)
        return folds

    def _fold_start_timestamps(self, min_ts: int, max_ts: int) -> list[int]:
        latest_start = (
            max_ts
            - self.config.train_window_seconds
            - self.config.gap_seconds
            - self.config.test_window_seconds
            + 1
        )
        if latest_start < min_ts:
            return []
        step = max(1, self.config.step_seconds)
        full_count = ((latest_start - min_ts) // step) + 1
        max_folds = self.config.max_folds
        if max_folds is None or max_folds <= 0 or full_count <= max_folds:
            return [min_ts + (index * step) for index in range(full_count)]
        if max_folds == 1:
            return [min_ts]
        spread = latest_start - min_ts
        return sorted({
            min_ts + round((spread * index) / (max_folds - 1))
            for index in range(max_folds)
        })

    def rows_for_train_fold(
        self,
        rows: list[ResearchDatasetRow],
        fold: WalkForwardFold,
    ) -> list[ResearchDatasetRow]:
        return sorted(
            [
                row for row in rows
                if fold.train_start_ts <= row.snapshot_ts <= fold.train_end_ts
            ],
            key=lambda row: (row.snapshot_ts, row.row_id),
        )

    def rows_for_test_fold(
        self,
        rows: list[ResearchDatasetRow],
        fold: WalkForwardFold,
    ) -> list[ResearchDatasetRow]:
        return sorted(
            [
                row for row in rows
                if fold.test_start_ts <= row.snapshot_ts <= fold.test_end_ts
            ],
            key=lambda row: (row.snapshot_ts, row.row_id),
        )


def _count_in_window(sorted_timestamps: list[int], start_ts: int, end_ts: int) -> int:
    if not sorted_timestamps:
        return 0
    return bisect_right(sorted_timestamps, end_ts) - bisect_left(sorted_timestamps, start_ts)
