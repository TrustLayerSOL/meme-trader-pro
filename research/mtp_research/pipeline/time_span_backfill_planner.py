"""Planner for bounded backfills that expand chronological evidence span."""

from __future__ import annotations

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
    ):
        self.raw_store = raw_store or RawTransactionStore()
        self.event_store = event_store or NormalizedEventStore()
        self.feature_store = feature_store or FeatureSnapshotStore()
        self.outcome_store = outcome_store or OutcomeLabelStore()
        self.dataset_store = dataset_store or ResearchDatasetStore()

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
    ) -> list[TokenEvidenceCoverage]:
        output = []
        for candidate in candidates:
            token = candidate.token_mint
            token_raw = [record for record in raw_records if record.token_mint == token]
            token_events = [event for event in events if event.token_mint == token]
            token_features = [item for item in feature_snapshots if item.token_mint == token]
            token_labels = [label for label in outcome_labels if label.token_mint == token]
            token_rows = [row for row in research_rows if row.token_mint == token]
            times = [
                value for value in [
                    *[record.block_time for record in token_raw],
                    *[event.block_time for event in token_events],
                ]
                if value is not None
            ]
            first = min(times) if times else None
            last = max(times) if times else None
            span = (last - first) if first is not None and last is not None else None
            priced_count = sum(1 for event in token_events if event.price_quote is not None and event.price_quote > 0)
            trade_count = sum(1 for event in token_events if event.event_type in TRADE_EVENT_TYPES)
            warning_flags = []
            if not token_raw:
                warning_flags.append("no_raw_transactions")
            if span is None:
                warning_flags.append("missing_time_span")
            elif span < target_time_span_seconds:
                warning_flags.append("short_time_span")
            if priced_count < 5:
                warning_flags.append("low_priced_event_count")
            if len(token_rows) < min_research_rows_per_token:
                warning_flags.append("low_research_row_count")
            if len(token_raw) < min_raw_tx_per_token:
                warning_flags.append("low_raw_tx_count")
            needs_backfill = bool(warning_flags)
            output.append(
                TokenEvidenceCoverage(
                    token_mint=token,
                    pool_address=candidate.pool_address,
                    venue=candidate.venue,
                    source=candidate.source,
                    liquidity_usd=candidate.liquidity_usd,
                    raw_tx_count=len(token_raw),
                    normalized_event_count=len(token_events),
                    trade_event_count=trade_count,
                    priced_event_count=priced_count,
                    feature_snapshot_count=len(token_features),
                    outcome_label_count=len(token_labels),
                    research_row_count=len(token_rows),
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
            self.feature_store.load_all(),
            self.outcome_store.load_all(),
            self.dataset_store.load_all(),
            target_time_span_seconds=target_time_span_seconds,
            min_raw_tx_per_token=min_raw_tx_per_token,
            min_research_rows_per_token=min_research_rows_per_token,
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
