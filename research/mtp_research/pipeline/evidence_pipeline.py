"""Controlled evidence population pipeline for v3 research."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from time import perf_counter

from research.mtp_research.features.feature_snapshot_builder import FeatureSnapshotBuilder
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.basic_transaction_normalizer import (
    transaction_summary_to_observed_event,
)
from research.mtp_research.ingestion.backfill_jobs import BackfillTarget
from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)
from research.mtp_research.ingestion.solana_transaction_parser import summarize_raw_transaction
from research.mtp_research.ingestion.trade_event_normalizer import TradeEventNormalizer
from research.mtp_research.ingestion.venue_classifier import classify_venue
from research.mtp_research.pipeline.backfill_target_planner import BackfillTargetPlanner
from research.mtp_research.pipeline.evidence_models import (
    EvidenceRunConfig,
    EvidenceRunSummary,
    utc_now_iso,
)
from research.mtp_research.validation.outcome_label_builder import OutcomeLabelBuilder
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_builder import ResearchDatasetBuilder
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


class EvidencePipeline:
    """Orchestrate bounded backfill and offline rebuild steps."""

    def __init__(
        self,
        candidate_registry: CandidateRegistry | None = None,
        raw_transaction_store: RawTransactionStore | None = None,
        normalized_event_store: NormalizedEventStore | None = None,
        feature_snapshot_store: FeatureSnapshotStore | None = None,
        outcome_label_store: OutcomeLabelStore | None = None,
        research_dataset_store: ResearchDatasetStore | None = None,
        helius_adapter: HeliusHistoricalAdapter | None = None,
    ):
        self.candidate_registry = candidate_registry or CandidateRegistry()
        self.raw_transaction_store = raw_transaction_store or RawTransactionStore()
        self.normalized_event_store = normalized_event_store or NormalizedEventStore()
        self.feature_snapshot_store = feature_snapshot_store or FeatureSnapshotStore()
        self.outcome_label_store = outcome_label_store or OutcomeLabelStore()
        self.research_dataset_store = research_dataset_store or ResearchDatasetStore()
        self.helius_adapter = helius_adapter
        self.target_planner = BackfillTargetPlanner()

    def select_candidates(self, limit: int | None = None) -> list[LaunchCandidate]:
        candidates = self.candidate_registry.load_all()
        return candidates[:limit] if limit is not None else candidates

    def plan_targets(
        self,
        candidates: list[LaunchCandidate],
        roles: list[str],
        exclude_mock: bool = True,
    ) -> list[BackfillTarget]:
        return self.target_planner.candidates_to_targets(candidates, roles=roles, exclude_mock=exclude_mock)

    def run_backfill_targets(
        self,
        targets: list[BackfillTarget],
        config: EvidenceRunConfig,
        execute: bool = False,
    ) -> EvidenceRunSummary:
        summary = EvidenceRunSummary(
            run_id=config.run_id,
            created_at=utc_now_iso(),
            dry_run=config.dry_run or not execute,
            targets_planned=len(targets),
            artifact_paths={"raw_transactions": str(self.raw_transaction_store.path)},
        )
        if config.dry_run or not execute:
            summary.warning_flags.append("dry_run_no_network_calls")
            return summary

        adapter = self.helius_adapter
        if adapter is None:
            try:
                adapter = HeliusHistoricalAdapter.from_env(
                    transaction_workers=config.transaction_workers,
                    timeout_sec=config.helius_timeout_sec,
                )
            except ValueError as exc:
                summary.warning_flags.append("missing_helius_api_key")
                summary.metadata_json["error"] = str(exc)
                return summary

        existing_signatures = {record.signature for record in self.raw_transaction_store.load_all()}
        summary.metadata_json["performance_config"] = {
            "transaction_workers": config.transaction_workers,
            "helius_timeout_sec": config.helius_timeout_sec,
            "signature_pages_per_target": config.signature_pages_per_target,
        }
        target_timings = []
        for target in targets:
            target_started = perf_counter()
            target_timing = {
                "target_id": target.target_id,
                "role": target.role,
                "token_mint": target.token_mint,
                "signature_seconds": 0.0,
                "transaction_seconds": 0.0,
                "store_seconds": 0.0,
                "pages": 0,
                "signatures_seen": 0,
                "transactions_fetched": 0,
            }
            try:
                next_before = None
                transactions_for_target = 0
                page_count = max(1, config.signature_pages_per_target)
                for _page_index in range(page_count):
                    request = HeliusBackfillRequest(
                        address=target.address,
                        token_mint=target.token_mint,
                        role=target.role,
                        limit=config.max_signatures_per_target,
                        before=next_before,
                        include_failed=config.include_failed,
                    )
                    signature_started = perf_counter()
                    signature_result = adapter.fetch_signatures_for_address(request)
                    target_timing["signature_seconds"] += perf_counter() - signature_started
                    target_timing["pages"] += 1
                    signatures = [record.signature for record in signature_result.records]
                    summary.signatures_seen += len(signatures)
                    target_timing["signatures_seen"] += len(signatures)

                    remaining_transactions = config.max_transactions_per_target - transactions_for_target
                    if remaining_transactions <= 0:
                        break

                    missing_signatures = [
                        signature for signature in signatures if signature not in existing_signatures
                    ]
                    selected_signatures = missing_signatures[:remaining_transactions]
                    if selected_signatures:
                        transaction_started = perf_counter()
                        bodies = adapter.fetch_transactions(selected_signatures)
                        target_timing["transaction_seconds"] += perf_counter() - transaction_started
                        raw_records = [
                            _raw_record_from_body(signature, body, target)
                            for signature, body in zip(selected_signatures, bodies, strict=False)
                            if body
                        ]
                        store_started = perf_counter()
                        counts = self.raw_transaction_store.upsert_many(raw_records)
                        target_timing["store_seconds"] += perf_counter() - store_started
                        summary.transactions_fetched += len(raw_records)
                        target_timing["transactions_fetched"] += len(raw_records)
                        summary.raw_transactions_inserted += counts["inserted"]
                        summary.raw_transactions_updated += counts["updated"]
                        transactions_for_target += len(raw_records)
                        existing_signatures.update(record.signature for record in raw_records)

                    next_before = signature_result.next_before
                    if not next_before or transactions_for_target >= config.max_transactions_per_target:
                        break
            except Exception as exc:  # noqa: BLE001 - continue per target in bounded research runs
                summary.warning_flags.append(f"target_backfill_failed:{target.target_id}")
                summary.metadata_json.setdefault("target_errors", {})[target.target_id] = str(exc)
            finally:
                target_timing["total_seconds"] = perf_counter() - target_started
                target_timings.append(target_timing)
        summary.metadata_json["target_timings"] = target_timings
        return summary

    def parse_raw_transactions(self, limit: int | None = None) -> dict[str, int]:
        raw_records = self.raw_transaction_store.load_all()
        selected = raw_records[:limit] if limit is not None else raw_records
        events = []
        skipped = 0
        for record in selected:
            try:
                summary = summarize_raw_transaction(record)
                summary.venue_classification = classify_venue(summary)
                events.append(transaction_summary_to_observed_event(summary))
            except Exception:
                skipped += 1
        counts = self.normalized_event_store.upsert_many(events)
        return {
            "processed": len(selected),
            "inserted": counts["inserted"],
            "updated": counts["updated"],
            "skipped": skipped,
        }

    def normalize_trade_events(self, limit: int | None = None) -> dict[str, int]:
        raw_records = self.raw_transaction_store.load_all()
        selected = raw_records[:limit] if limit is not None else raw_records
        normalizer = TradeEventNormalizer()
        events = []
        skipped = 0
        for record in selected:
            try:
                summary = summarize_raw_transaction(record)
                summary.venue_classification = classify_venue(summary)
                result = normalizer.normalize_summary(summary)
                events.extend(
                    normalizer.flow_to_normalized_event(summary, flow, index)
                    for index, flow in enumerate(result.flows)
                )
            except Exception:
                skipped += 1
        counts = self.normalized_event_store.upsert_many(events)
        return {
            "processed": len(selected),
            "inserted": counts["inserted"],
            "updated": counts["updated"],
            "skipped": skipped,
        }

    def build_features(self, max_snapshots: int | None = None) -> dict[str, int]:
        events = self.normalized_event_store.load_all()
        snapshot_times = _snapshot_times(sorted({event.block_time for event in events if event.block_time is not None}), 60)
        if max_snapshots is not None:
            snapshot_times = snapshot_times[:max_snapshots]
        snapshots = FeatureSnapshotBuilder().build_snapshots(events, snapshot_times=snapshot_times)
        counts = self.feature_snapshot_store.upsert_many(snapshots)
        return {"loaded_events": len(events), "generated": len(snapshots), **counts}

    def build_outcomes(self, max_snapshots: int | None = None) -> dict[str, int]:
        snapshots = self.feature_snapshot_store.load_all()
        if max_snapshots is not None:
            snapshots = snapshots[:max_snapshots]
        events = self.normalized_event_store.load_all()
        labels = OutcomeLabelBuilder().build_labels(snapshots, events)
        counts = self.outcome_label_store.upsert_many(labels)
        return {"loaded_snapshots": len(snapshots), "loaded_events": len(events), "generated": len(labels), **counts}

    def build_research_dataset(self) -> dict[str, int]:
        snapshots = self.feature_snapshot_store.load_all()
        labels = self.outcome_label_store.load_all()
        rows = ResearchDatasetBuilder().join_snapshots_to_outcomes(snapshots, labels)
        counts = self.research_dataset_store.upsert_many(rows)
        return {"loaded_snapshots": len(snapshots), "loaded_labels": len(labels), "generated": len(rows), **counts}

    def run_offline_rebuild(
        self,
        config: EvidenceRunConfig,
        parse_limit: int | None = None,
        normalize_limit: int | None = None,
        max_snapshots: int | None = None,
    ) -> EvidenceRunSummary:
        summary = EvidenceRunSummary(
            run_id=config.run_id,
            created_at=utc_now_iso(),
            dry_run=False,
            warning_flags=["offline_rebuild_no_network_calls"],
            artifact_paths={
                "raw_transactions": str(self.raw_transaction_store.path),
                "normalized_events": str(self.normalized_event_store.path),
                "feature_snapshots": str(self.feature_snapshot_store.path),
                "outcome_labels": str(self.outcome_label_store.path),
                "research_dataset": str(self.research_dataset_store.path),
            },
        )
        parsed = self.parse_raw_transactions(limit=parse_limit)
        trades = self.normalize_trade_events(limit=normalize_limit)
        features = self.build_features(max_snapshots=max_snapshots)
        outcomes = self.build_outcomes(max_snapshots=max_snapshots)
        dataset = self.build_research_dataset()
        summary.normalized_events_inserted = parsed["inserted"]
        summary.normalized_events_updated = parsed["updated"]
        summary.trade_events_inserted = trades["inserted"]
        summary.trade_events_updated = trades["updated"]
        summary.feature_snapshots_inserted = features["inserted"]
        summary.feature_snapshots_updated = features["updated"]
        summary.outcome_labels_inserted = outcomes["inserted"]
        summary.outcome_labels_updated = outcomes["updated"]
        summary.research_rows_inserted = dataset["inserted"]
        summary.research_rows_updated = dataset["updated"]
        summary.metadata_json = {
            "parse": parsed,
            "trade_normalization": trades,
            "features": features,
            "outcomes": outcomes,
            "dataset": dataset,
        }
        return summary


def _raw_record_from_body(
    signature: str,
    body: dict,
    target: BackfillTarget,
) -> RawTransactionRecord:
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return RawTransactionRecord(
        signature=signature,
        slot=body.get("slot"),
        block_time=body.get("blockTime"),
        success=(meta.get("err") is None if meta else None),
        address=target.address,
        role=target.role,
        token_mint=target.token_mint,
        fetched_at=datetime.now(timezone.utc),
        raw_json=body,
        metadata_json={"target_id": target.target_id, "source": target.source},
    )


def _snapshot_times(block_times: list[int], step_sec: int) -> list[int]:
    if not block_times:
        return []
    output = []
    current = min(block_times)
    end = max(block_times)
    while current <= end:
        output.append(current)
        current += step_sec
    if output[-1] != end:
        output.append(end)
    return output
