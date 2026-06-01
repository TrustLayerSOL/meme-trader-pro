"""Planner for bounded backfills that expand chronological evidence span."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)
from research.mtp_research.pipeline.real_candidate_filter import filter_real_candidates
from research.mtp_research.pipeline.time_span_backfill_models import (
    TimeSpanBackfillPlan,
    TimeSpanBackfillPlanItem,
    TokenEvidenceCoverage,
    make_time_span_backfill_plan_id,
)
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


TRADE_EVENT_TYPES = {
    "possible_buy",
    "possible_sell",
    "token_accumulation",
    "token_distribution",
}


class TimeSpanBackfillPlanner:
    """Build deterministic target plans for extending evidence time span."""

    def __init__(
        self,
        raw_store: RawTransactionStore | None = None,
        event_store: NormalizedEventStore | None = None,
        feature_store: FeatureSnapshotStore | None = None,
        outcome_store: OutcomeLabelStore | None = None,
        dataset_store: ResearchDatasetStore | None = None,
        include_derived_coverage: bool = True,
    ):
        self.raw_store = raw_store or RawTransactionStore()
        self.event_store = event_store or NormalizedEventStore()
        self.feature_store = feature_store or FeatureSnapshotStore()
        self.outcome_store = outcome_store or OutcomeLabelStore()
        self.dataset_store = dataset_store or ResearchDatasetStore()
        self.include_derived_coverage = include_derived_coverage

    def load_real_candidates(
        self,
        registry_path: Path | str | None = None,
        min_liquidity_usd: float | None = None,
        require_pool_address: bool = True,
    ) -> list[LaunchCandidate]:
        registry = CandidateRegistry(registry_path) if registry_path else CandidateRegistry()
        candidates = filter_real_candidates(
            registry.load_all(),
            require_pool_address=require_pool_address,
            min_liquidity_usd=min_liquidity_usd,
        )
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.pool_address is None,
                -(candidate.liquidity_usd or 0.0),
                candidate.first_seen_ts,
                candidate.token_mint,
            ),
        )

    def build_token_coverage(
        self,
        candidates: list[LaunchCandidate],
        raw_records: list[RawTransactionRecord],
        events: list[NormalizedEvent],
        feature_snapshots: list[FeatureSnapshot],
        outcome_labels: list[OutcomeLabel],
        research_rows: list[ResearchDatasetRow],
        target_time_span_seconds: int = 3600,
        min_raw_tx_per_token: int = 50,
        min_research_rows_per_token: int = 100,
        include_derived_coverage: bool = True,
    ) -> list[TokenEvidenceCoverage]:
        stats_by_token = _build_coverage_stats_by_token(
            raw_records,
            events,
            feature_snapshots,
            outcome_labels,
            research_rows,
        )
        output = []
        for candidate in candidates:
            token = candidate.token_mint
            stats = stats_by_token.get(token, _CoverageStats())
            first = stats.first_block_time
            last = stats.last_block_time
            span = (last - first) if first is not None and last is not None else None
            warning_flags = []
            if stats.raw_tx_count == 0:
                warning_flags.append("no_raw_transactions")
            if span is None:
                warning_flags.append("missing_time_span")
            elif span < target_time_span_seconds:
                warning_flags.append("short_time_span")
            if stats.priced_event_count < 5:
                warning_flags.append("low_priced_event_count")
            if include_derived_coverage and stats.research_row_count < min_research_rows_per_token:
                warning_flags.append("low_research_row_count")
            if stats.raw_tx_count < min_raw_tx_per_token:
                warning_flags.append("low_raw_tx_count")
            if not include_derived_coverage:
                warning_flags.append("derived_coverage_not_loaded")
            needs_backfill = bool(warning_flags)
            output.append(
                TokenEvidenceCoverage(
                    token_mint=token,
                    pool_address=candidate.pool_address,
                    venue=candidate.venue,
                    source=candidate.source,
                    liquidity_usd=candidate.liquidity_usd,
                    raw_tx_count=stats.raw_tx_count,
                    normalized_event_count=stats.normalized_event_count,
                    trade_event_count=stats.trade_event_count,
                    priced_event_count=stats.priced_event_count,
                    feature_snapshot_count=stats.feature_snapshot_count,
                    outcome_label_count=stats.outcome_label_count,
                    research_row_count=stats.research_row_count,
                    first_block_time=first,
                    last_block_time=last,
                    time_span_seconds=span,
                    has_pool_target=bool(candidate.pool_address),
                    needs_backfill=needs_backfill,
                    warning_flags=warning_flags,
                    metadata_json={
                        "target_time_span_seconds": target_time_span_seconds,
                        "min_raw_tx_per_token": min_raw_tx_per_token,
                        "min_research_rows_per_token": min_research_rows_per_token,
                        "include_derived_coverage": include_derived_coverage,
                    },
                )
            )
        return output

    def build_plan(
        self,
        min_liquidity_usd: float | None = 10000,
        candidate_limit: int = 10,
        target_time_span_seconds: int = 3600,
        min_raw_tx_per_token: int = 50,
        min_research_rows_per_token: int = 100,
        recommended_signature_limit: int = 100,
        recommended_transaction_limit: int = 100,
        registry_path: Path | str | None = None,
    ) -> TimeSpanBackfillPlan:
        all_candidates = CandidateRegistry(registry_path).load_all() if registry_path else CandidateRegistry().load_all()
        real_candidates = self.load_real_candidates(
            registry_path=registry_path,
            min_liquidity_usd=min_liquidity_usd,
            require_pool_address=True,
        )
        selected_candidates = real_candidates[:candidate_limit]
        coverage = self.build_token_coverage(
            selected_candidates,
            self.raw_store.load_all(),
            self.event_store.load_all(),
            self.feature_store.load_all() if self.include_derived_coverage else [],
            self.outcome_store.load_all() if self.include_derived_coverage else [],
            self.dataset_store.load_all() if self.include_derived_coverage else [],
            target_time_span_seconds=target_time_span_seconds,
            min_raw_tx_per_token=min_raw_tx_per_token,
            min_research_rows_per_token=min_research_rows_per_token,
            include_derived_coverage=self.include_derived_coverage,
        )
        plan_items = self._coverage_to_plan_items(
            coverage,
            recommended_signature_limit=recommended_signature_limit,
            recommended_transaction_limit=recommended_transaction_limit,
        )
        command = _recommended_command(
            candidate_limit=min(5, candidate_limit),
            min_liquidity_usd=min_liquidity_usd,
            signature_limit=75,
            transaction_limit=75,
        )
        warning_flags = ["dry_run_default", "requires_execute_for_helius", "no_live_trading"]
        if not plan_items:
            warning_flags.append("no_backfill_targets_needed_or_available")
        return TimeSpanBackfillPlan(
            plan_id=make_time_span_backfill_plan_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            candidate_count=len(all_candidates),
            real_candidate_count=len(real_candidates),
            coverage_items=coverage,
            plan_items=plan_items,
            target_token_count=len({item.token_mint for item in plan_items}),
            target_pool_count=sum(1 for item in plan_items if item.role == "pool"),
            estimated_signature_requests=sum(item.recommended_signature_limit for item in plan_items),
            estimated_transaction_requests=sum(item.recommended_transaction_limit for item in plan_items),
            recommended_next_command=command,
            warning_flags=warning_flags,
            metadata_json={
                "target_time_span_seconds": target_time_span_seconds,
                "min_raw_tx_per_token": min_raw_tx_per_token,
                "min_research_rows_per_token": min_research_rows_per_token,
                "min_liquidity_usd": min_liquidity_usd,
                "candidate_limit": candidate_limit,
                "include_derived_coverage": self.include_derived_coverage,
            },
        )

    def _coverage_to_plan_items(
        self,
        coverage: list[TokenEvidenceCoverage],
        recommended_signature_limit: int,
        recommended_transaction_limit: int,
    ) -> list[TimeSpanBackfillPlanItem]:
        items = []
        seen_targets = set()
        for item in sorted(coverage, key=_coverage_priority):
            if not item.needs_backfill:
                continue
            target = item.pool_address or item.token_mint
            role = "pool" if item.pool_address else "mint"
            if target in seen_targets:
                continue
            seen_targets.add(target)
            priority, reason = _priority_and_reason(item)
            items.append(
                TimeSpanBackfillPlanItem(
                    token_mint=item.token_mint,
                    pool_address=item.pool_address,
                    target_address=target,
                    role=role,
                    reason=reason,
                    recommended_signature_limit=recommended_signature_limit,
                    recommended_transaction_limit=recommended_transaction_limit,
                    current_time_span_seconds=item.time_span_seconds,
                    current_raw_tx_count=item.raw_tx_count,
                    priority=priority,
                    metadata_json={
                        "warning_flags": item.warning_flags,
                        "liquidity_usd": item.liquidity_usd,
                    },
                )
            )
        return items


def _coverage_priority(item: TokenEvidenceCoverage) -> tuple[int, int, int, float, str]:
    priority, _ = _priority_and_reason(item)
    span = item.time_span_seconds if item.time_span_seconds is not None else -1
    return (priority, item.raw_tx_count, span, -(item.liquidity_usd or 0.0), item.token_mint)


def _priority_and_reason(item: TokenEvidenceCoverage) -> tuple[int, str]:
    if item.raw_tx_count == 0:
        return 1, "no_raw_transactions"
    if item.time_span_seconds is None:
        return 2, "missing_time_span"
    if "short_time_span" in item.warning_flags:
        return 3, "short_time_span"
    if "low_research_row_count" in item.warning_flags:
        return 4, "low_research_row_count"
    return 5, "coverage_below_threshold"


def _recommended_command(
    candidate_limit: int,
    min_liquidity_usd: float | None,
    signature_limit: int,
    transaction_limit: int,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute",
        f"--candidate-limit {candidate_limit}",
        f"--max-signatures-per-target {signature_limit}",
        f"--max-transactions-per-target {transaction_limit}",
        "--stop-after-targets 10",
    ]
    if min_liquidity_usd is not None:
        parts.append(f"--min-liquidity-usd {int(min_liquidity_usd)}")
    parts.append("--execute")
    return " ".join(parts)


@dataclass
class _CoverageStats:
    raw_tx_count: int = 0
    normalized_event_count: int = 0
    trade_event_count: int = 0
    priced_event_count: int = 0
    feature_snapshot_count: int = 0
    outcome_label_count: int = 0
    research_row_count: int = 0
    first_block_time: int | None = None
    last_block_time: int | None = None

    def observe_time(self, block_time: int | None) -> None:
        if block_time is None:
            return
        self.first_block_time = (
            block_time
            if self.first_block_time is None
            else min(self.first_block_time, block_time)
        )
        self.last_block_time = (
            block_time
            if self.last_block_time is None
            else max(self.last_block_time, block_time)
        )


def _build_coverage_stats_by_token(
    raw_records: list[RawTransactionRecord],
    events: list[NormalizedEvent],
    feature_snapshots: list[FeatureSnapshot],
    outcome_labels: list[OutcomeLabel],
    research_rows: list[ResearchDatasetRow],
) -> dict[str, _CoverageStats]:
    stats_by_token: defaultdict[str, _CoverageStats] = defaultdict(_CoverageStats)
    for record in raw_records:
        if not record.token_mint:
            continue
        stats = stats_by_token[record.token_mint]
        stats.raw_tx_count += 1
        stats.observe_time(record.block_time)
    for event in events:
        if not event.token_mint:
            continue
        stats = stats_by_token[event.token_mint]
        stats.normalized_event_count += 1
        stats.observe_time(event.block_time)
        if event.event_type in TRADE_EVENT_TYPES:
            stats.trade_event_count += 1
        if event.price_quote is not None and event.price_quote > 0:
            stats.priced_event_count += 1
    for snapshot in feature_snapshots:
        stats_by_token[snapshot.token_mint].feature_snapshot_count += 1
    for label in outcome_labels:
        stats_by_token[label.token_mint].outcome_label_count += 1
    for row in research_rows:
        stats_by_token[row.token_mint].research_row_count += 1
    return dict(stats_by_token)
