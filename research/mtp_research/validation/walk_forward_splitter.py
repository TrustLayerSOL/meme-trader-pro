"""Chronological fold splitter for walk-forward validation."""

from __future__ import annotations

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
        min_ts, max_ts = bounds
        folds: list[WalkForwardFold] = []
        fold_index = 0
        train_start_ts = min_ts
        while True:
            train_end_ts = train_start_ts + self.config.train_window_seconds - 1
            test_start_ts = train_end_ts + self.config.gap_seconds + 1
            test_end_ts = test_start_ts + self.config.test_window_seconds - 1
            if test_end_ts > max_ts:
                break
            fold = WalkForwardFold(
                fold_id=make_fold_id(self.config.config_id, fold_index),
                fold_index=fold_index,
                train_start_ts=train_start_ts,
                train_end_ts=train_end_ts,
                test_start_ts=test_start_ts,
                test_end_ts=test_end_ts,
                gap_seconds=self.config.gap_seconds,
            )
            train_rows = self.rows_for_train_fold(rows, fold)
            test_rows = self.rows_for_test_fold(rows, fold)
            fold.train_row_count = len(train_rows)
            fold.test_row_count = len(test_rows)
            folds.append(fold)
            fold_index += 1
            train_start_ts += self.config.step_seconds
        return folds

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
