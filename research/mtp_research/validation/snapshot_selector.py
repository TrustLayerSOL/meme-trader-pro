"""Deterministic feature snapshot selection for validation artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.snapshot_selection_models import (
    SnapshotSelectionConfig,
    SnapshotSelectionSummary,
)


class SnapshotSelector:
    """Select feature snapshots without silently truncating to early-only slices."""

    VALID_STRATEGIES = {"head", "latest", "all", "full_span_even", "per_token_even"}

    def select_snapshots(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> tuple[list[FeatureSnapshot], SnapshotSelectionSummary]:
        if config.strategy not in self.VALID_STRATEGIES:
            raise ValueError(f"unsupported snapshot selection strategy: {config.strategy}")

        filtered = self._apply_filters(snapshots, config)
        if config.strategy == "head":
            selected = self.select_head(filtered, config)
        elif config.strategy == "latest":
            selected = self.select_latest(filtered, config)
        elif config.strategy == "all":
            selected = list(filtered)
        elif config.strategy == "full_span_even":
            selected = self.select_full_span_even(filtered, config)
        else:
            selected = self.select_per_token_even(filtered, config)

        if config.min_time_gap_seconds and config.strategy not in {"per_token_even"}:
            selected = self._apply_min_gap_by_token(selected, config.min_time_gap_seconds)

        summary = self.summarize_selection(filtered, selected, config)
        return selected, summary

    def select_head(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> list[FeatureSnapshot]:
        if config.max_snapshots is None:
            return list(snapshots)
        return list(snapshots[: config.max_snapshots])

    def select_latest(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> list[FeatureSnapshot]:
        ordered = sorted(snapshots, key=self._time_key)
        if config.max_snapshots is None:
            return ordered
        return ordered[-config.max_snapshots :]

    def select_full_span_even(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> list[FeatureSnapshot]:
        ordered = sorted(snapshots, key=self._time_key)
        return self._even_pick(ordered, config.max_snapshots)

    def select_per_token_even(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> list[FeatureSnapshot]:
        by_token: dict[str, list[FeatureSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            by_token[snapshot.token_mint].append(snapshot)

        token_mints = sorted(by_token)
        if not token_mints:
            return []

        limits = self._per_token_limits(token_mints, by_token, config)
        selected: list[FeatureSnapshot] = []
        for token_mint in token_mints:
            ordered = sorted(by_token[token_mint], key=self._time_key)
            token_selected = self._even_pick(ordered, limits.get(token_mint))
            if config.min_time_gap_seconds:
                token_selected = self._apply_min_gap(token_selected, config.min_time_gap_seconds)
            selected.extend(token_selected)
        return sorted(selected, key=self._time_key)

    def summarize_selection(
        self,
        input_snapshots: list[FeatureSnapshot],
        selected_snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> SnapshotSelectionSummary:
        input_times = [snapshot.snapshot_ts for snapshot in input_snapshots if snapshot.snapshot_ts is not None]
        selected_times = [
            snapshot.snapshot_ts for snapshot in selected_snapshots if snapshot.snapshot_ts is not None
        ]
        selected_by_token = dict(
            sorted(Counter(snapshot.token_mint for snapshot in selected_snapshots).items())
        )
        summary = SnapshotSelectionSummary(
            strategy=config.strategy,
            input_snapshot_count=len(input_snapshots),
            selected_snapshot_count=len(selected_snapshots),
            input_token_count=len({snapshot.token_mint for snapshot in input_snapshots}),
            selected_token_count=len({snapshot.token_mint for snapshot in selected_snapshots}),
            input_time_min=min(input_times) if input_times else None,
            input_time_max=max(input_times) if input_times else None,
            selected_time_min=min(selected_times) if selected_times else None,
            selected_time_max=max(selected_times) if selected_times else None,
            selected_by_token=selected_by_token,
            metadata_json=dict(config.metadata_json),
        )
        summary.input_time_span_seconds = self._span(summary.input_time_min, summary.input_time_max)
        summary.selected_time_span_seconds = self._span(
            summary.selected_time_min,
            summary.selected_time_max,
        )

        if summary.selected_snapshot_count == 0 and summary.input_snapshot_count > 0:
            summary.warning_flags.append("no_snapshots_selected")
        if (
            summary.input_time_span_seconds
            and summary.selected_time_span_seconds is not None
            and summary.selected_time_span_seconds < summary.input_time_span_seconds * 0.5
        ):
            summary.warning_flags.append("selected_time_span_much_smaller_than_input")
        if (
            summary.input_token_count
            and summary.selected_token_count < summary.input_token_count
            and not config.token_mints
        ):
            summary.warning_flags.append("selected_token_count_lower_than_input")
        return summary

    def _apply_filters(
        self,
        snapshots: list[FeatureSnapshot],
        config: SnapshotSelectionConfig,
    ) -> list[FeatureSnapshot]:
        filtered = list(snapshots)
        if config.token_mints:
            allowed = set(config.token_mints)
            filtered = [snapshot for snapshot in filtered if snapshot.token_mint in allowed]
        if config.real_only:
            allowed = real_token_mints_from_registry(min_liquidity_usd=config.min_liquidity_usd)
            filtered = [snapshot for snapshot in filtered if snapshot.token_mint in allowed]
        return filtered

    def _per_token_limits(
        self,
        token_mints: list[str],
        by_token: dict[str, list[FeatureSnapshot]],
        config: SnapshotSelectionConfig,
    ) -> dict[str, int | None]:
        if config.max_snapshots_per_token is not None:
            return {token_mint: config.max_snapshots_per_token for token_mint in token_mints}
        if config.max_snapshots is None:
            return {token_mint: None for token_mint in token_mints}
        if config.max_snapshots <= 0:
            return {token_mint: 0 for token_mint in token_mints}

        base = config.max_snapshots // len(token_mints)
        remainder = config.max_snapshots % len(token_mints)
        limits: dict[str, int] = {}
        for index, token_mint in enumerate(token_mints):
            limit = base + (1 if index < remainder else 0)
            limits[token_mint] = min(limit, len(by_token[token_mint]))
        return limits

    def _even_pick(
        self,
        snapshots: list[FeatureSnapshot],
        limit: int | None,
    ) -> list[FeatureSnapshot]:
        if limit is None or limit >= len(snapshots):
            return list(snapshots)
        if limit <= 0 or not snapshots:
            return []
        if limit == 1:
            return [snapshots[0]]

        last_index = len(snapshots) - 1
        indexes = [round(index * last_index / (limit - 1)) for index in range(limit)]
        selected_indexes: list[int] = []
        for index in indexes:
            if index not in selected_indexes:
                selected_indexes.append(index)
        candidate = 0
        while len(selected_indexes) < limit and candidate <= last_index:
            if candidate not in selected_indexes:
                selected_indexes.append(candidate)
            candidate += 1
        return [snapshots[index] for index in sorted(selected_indexes[:limit])]

    def _apply_min_gap_by_token(
        self,
        snapshots: list[FeatureSnapshot],
        gap_seconds: int,
    ) -> list[FeatureSnapshot]:
        by_token: dict[str, list[FeatureSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            by_token[snapshot.token_mint].append(snapshot)
        selected: list[FeatureSnapshot] = []
        for token_snapshots in by_token.values():
            selected.extend(self._apply_min_gap(sorted(token_snapshots, key=self._time_key), gap_seconds))
        return sorted(selected, key=self._time_key)

    def _apply_min_gap(
        self,
        snapshots: list[FeatureSnapshot],
        gap_seconds: int,
    ) -> list[FeatureSnapshot]:
        selected: list[FeatureSnapshot] = []
        last_ts: int | None = None
        for snapshot in snapshots:
            if last_ts is None or snapshot.snapshot_ts - last_ts >= gap_seconds:
                selected.append(snapshot)
                last_ts = snapshot.snapshot_ts
        return selected

    def _time_key(self, snapshot: FeatureSnapshot) -> tuple[int, str, int, str]:
        return (
            snapshot.snapshot_ts,
            snapshot.token_mint,
            snapshot.window_seconds,
            snapshot.snapshot_id,
        )

    def _span(self, time_min: int | None, time_max: int | None) -> int | None:
        if time_min is None or time_max is None:
            return None
        return max(0, time_max - time_min)
