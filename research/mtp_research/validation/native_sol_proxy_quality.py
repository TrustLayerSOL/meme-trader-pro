"""Diagnostic quality gate for native SOL price proxy-backed rows."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.native_sol_proxy_quality_models import (
    NativeSolProxyQualityConfig,
    NativeSolProxyQualityReport,
    NativeSolProxyRowDecision,
    make_native_sol_proxy_quality_report_id,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


NATIVE_SOL_PROXY_METHOD = "transaction_native_sol_quote_over_base_v0"


class NativeSolProxyQualityAnalyzer:
    """Separate suspicious native-SOL proxy rows from diagnostic validation."""

    def is_native_sol_proxy_row(self, row: ResearchDatasetRow) -> bool:
        return any(
            _contains_proxy_marker(value)
            for value in [
                row.entry_price_source,
                row.feature_metadata_json,
                row.outcome_metadata_json,
                row.metadata_json,
            ]
        )

    def count_proxy_price_points(
        self,
        row: ResearchDatasetRow,
        events: list[NormalizedEvent],
    ) -> tuple[int, int]:
        local_events = _local_price_events(row, events)
        proxy_count = sum(1 for event in local_events if _event_uses_proxy(event))
        return proxy_count, len(local_events) - proxy_count

    def evaluate_row(
        self,
        row: ResearchDatasetRow,
        events: list[NormalizedEvent],
        config: NativeSolProxyQualityConfig,
    ) -> NativeSolProxyRowDecision:
        local_events = _local_price_events(row, events)
        proxy_events = [event for event in local_events if _event_uses_proxy(event)]
        non_proxy_events = [event for event in local_events if not _event_uses_proxy(event)]
        is_proxy = self.is_native_sol_proxy_row(row) or bool(proxy_events)
        reasons: list[str] = []
        warnings: list[str] = []
        if is_proxy:
            warnings.extend(["native_sol_proxy_backed", "diagnostic_proxy_method"])
        if row.entry_price is None or row.forward_return is None:
            reasons.append("missing_basic_price_fields")

        max_gap = _max_gap_sec(proxy_events)
        max_jump = _max_price_jump_ratio(proxy_events)
        if is_proxy:
            if config.max_abs_forward_return is not None and row.forward_return is not None:
                if abs(row.forward_return) > config.max_abs_forward_return:
                    reasons.append("excessive_forward_return")
            if config.max_abs_runup is not None and row.max_runup is not None:
                if abs(row.max_runup) > config.max_abs_runup:
                    reasons.append("excessive_runup")
            if len(proxy_events) < config.min_proxy_price_points_in_horizon:
                reasons.append("insufficient_proxy_price_points")
            if config.max_gap_between_proxy_points_sec is not None and max_gap is not None:
                if max_gap > config.max_gap_between_proxy_points_sec:
                    reasons.append("large_proxy_price_gap")
            if config.max_price_jump_ratio is not None and max_jump is not None:
                if max_jump > config.max_price_jump_ratio:
                    reasons.append("extreme_proxy_price_jump")
            if config.require_non_proxy_anchor and not non_proxy_events:
                reasons.append("missing_non_proxy_anchor")

        return NativeSolProxyRowDecision(
            row_id=row.row_id,
            token_mint=row.token_mint,
            passed=not reasons,
            is_native_sol_proxy_backed=is_proxy,
            proxy_price_point_count=len(proxy_events),
            non_proxy_price_point_count=len(non_proxy_events),
            max_proxy_gap_sec=max_gap,
            max_price_jump_ratio_observed=max_jump,
            reasons_failed=reasons,
            warning_flags=warnings,
            metadata_json={
                "snapshot_ts": row.snapshot_ts,
                "horizon_seconds": row.horizon_seconds,
                "entry_price_source": row.entry_price_source,
            },
        )

    def filter_rows(
        self,
        rows: list[ResearchDatasetRow],
        events: list[NormalizedEvent],
        config: NativeSolProxyQualityConfig,
        dataset_path: str = "",
    ) -> tuple[list[ResearchDatasetRow], list[NativeSolProxyRowDecision], NativeSolProxyQualityReport]:
        events_by_token: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in events:
            if event.token_mint:
                events_by_token[event.token_mint].append(event)
        decisions = [
            self.evaluate_row(row, events_by_token.get(row.token_mint, []), config)
            for row in rows
        ]
        passed_rows = [row for row, decision in zip(rows, decisions) if decision.passed]
        report = self.build_report(rows, decisions, passed_rows, config, dataset_path)
        return passed_rows, decisions, report

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        decisions: list[NativeSolProxyRowDecision],
        passed_rows: list[ResearchDatasetRow],
        config: NativeSolProxyQualityConfig,
        dataset_path: str,
    ) -> NativeSolProxyQualityReport:
        failure_counts: Counter[str] = Counter()
        for decision in decisions:
            failure_counts.update(decision.reasons_failed)
        native_decisions = [decision for decision in decisions if decision.is_native_sol_proxy_backed]
        token_counts = Counter(row.token_mint for row in rows)
        return NativeSolProxyQualityReport(
            report_id=make_native_sol_proxy_quality_report_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            dataset_path=str(dataset_path),
            row_count=len(rows),
            native_proxy_backed_count=len(native_decisions),
            native_proxy_passed_count=sum(1 for decision in native_decisions if decision.passed),
            native_proxy_failed_count=sum(1 for decision in native_decisions if not decision.passed),
            non_proxy_count=len(decisions) - len(native_decisions),
            pass_rate=(len(passed_rows) / len(rows)) if rows else None,
            failure_reason_counts=dict(sorted(failure_counts.items())),
            token_counts=dict(sorted(token_counts.items())),
            config=config,
            warning_flags=["diagnostic_only_not_trading_signal"],
            metadata_json={"passed_row_count": len(passed_rows)},
        )


def _local_price_events(row: ResearchDatasetRow, events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    start_ts = row.entry_price_ts or row.snapshot_ts
    end_ts = row.snapshot_ts + row.horizon_seconds
    return sorted(
        [
            event
            for event in events
            if event.token_mint == row.token_mint
            and event.price_quote is not None
            and event.block_time is not None
            and start_ts <= event.block_time <= end_ts
        ],
        key=lambda event: (event.block_time or 0, event.event_id),
    )


def _event_uses_proxy(event: NormalizedEvent) -> bool:
    return _contains_proxy_marker(event.metadata_json)


def _contains_proxy_marker(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return NATIVE_SOL_PROXY_METHOD in value
    if isinstance(value, dict):
        return any(_contains_proxy_marker(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_proxy_marker(item) for item in value)
    return False


def _max_gap_sec(events: list[NormalizedEvent]) -> int | None:
    times = [event.block_time for event in events if event.block_time is not None]
    if len(times) < 2:
        return None
    return max(b - a for a, b in zip(times, times[1:]))


def _max_price_jump_ratio(events: list[NormalizedEvent]) -> float | None:
    prices = [event.price_quote for event in events if event.price_quote and event.price_quote > 0]
    if len(prices) < 2:
        return None
    ratios = []
    for before, after in zip(prices, prices[1:]):
        lower = min(before, after)
        higher = max(before, after)
        if lower > 0:
            ratios.append(higher / lower)
    return max(ratios) if ratios else None
