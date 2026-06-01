"""Plan bounded evidence expansion from sample adequacy gaps."""

from __future__ import annotations

from pathlib import Path

from research.mtp_research.pipeline.sample_adequacy_expansion_models import (
    SampleAdequacyExpansionPlan,
    make_sample_adequacy_expansion_plan_id,
    utc_now_iso,
)
from research.mtp_research.pipeline.time_span_backfill_planner import TimeSpanBackfillPlanner
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.sample_adequacy import SampleAdequacyAnalyzer
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


class SampleAdequacyExpansionPlanner:
    """Combine sample adequacy thresholds with dry-run backfill target planning."""

    def __init__(
        self,
        min_real_token_count: int = 10,
        min_time_span_seconds: int = 43_200,
        min_valid_test_folds: int = 10,
        min_total_test_selected_count: int = 100,
        min_independent_batches: int = 1,
    ):
        self.min_real_token_count = min_real_token_count
        self.min_time_span_seconds = min_time_span_seconds
        self.min_valid_test_folds = min_valid_test_folds
        self.min_total_test_selected_count = min_total_test_selected_count
        self.min_independent_batches = min_independent_batches

    def build_plan(
        self,
        registry_path: Path | str | None = None,
        dataset_path: Path | str = "data/backtests/diagnostics/research_dataset_nearest300.jsonl",
        walk_forward_store_path: Path | str = "data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl",
        candidate_limit: int = 10,
        min_liquidity_usd: float | None = 10_000,
        recommended_signature_limit: int = 75,
        recommended_transaction_limit: int = 75,
        raw_store_path: Path | str | None = None,
        event_store_path: Path | str | None = None,
        feature_store_path: Path | str | None = None,
        outcome_store_path: Path | str | None = None,
    ) -> SampleAdequacyExpansionPlan:
        rows = ResearchDatasetStore(dataset_path).load_all()
        validations = WalkForwardValidationStore(walk_forward_store_path).load_all()
        sample = SampleAdequacyAnalyzer(
            min_real_token_count=self.min_real_token_count,
            min_time_span_seconds=self.min_time_span_seconds,
            min_valid_test_folds=self.min_valid_test_folds,
            min_total_test_selected_count=self.min_total_test_selected_count,
            min_independent_batches=self.min_independent_batches,
        ).build_report(rows, validations)
        time_span_planner = TimeSpanBackfillPlanner(
            raw_store=RawTransactionStore(raw_store_path) if raw_store_path else None,
            event_store=NormalizedEventStore(event_store_path) if event_store_path else None,
            feature_store=FeatureSnapshotStore(feature_store_path) if feature_store_path else None,
            outcome_store=OutcomeLabelStore(outcome_store_path) if outcome_store_path else None,
            dataset_store=ResearchDatasetStore(dataset_path),
        )
        time_span_plan = time_span_planner.build_plan(
            registry_path=registry_path,
            min_liquidity_usd=min_liquidity_usd,
            candidate_limit=candidate_limit,
            target_time_span_seconds=self.min_time_span_seconds,
            min_research_rows_per_token=max(100, self.min_total_test_selected_count),
            recommended_signature_limit=recommended_signature_limit,
            recommended_transaction_limit=recommended_transaction_limit,
        )
        token_shortfall = max(self.min_real_token_count - sample.real_token_count, 0)
        span_shortfall = max(self.min_time_span_seconds - (sample.time_span_seconds or 0), 0)
        selected_shortfall = max(
            self.min_total_test_selected_count - sample.total_test_selected_count,
            0,
        )
        warnings = [
            "dry_run_only_no_helius",
            "requires_human_review_before_execute",
            "no_live_trading",
        ]
        if not sample.adequate_for_rejection or not sample.adequate_for_promotion:
            warnings.append("sample_not_adequate_for_thesis_status_changes")
        return SampleAdequacyExpansionPlan(
            plan_id=make_sample_adequacy_expansion_plan_id(),
            created_at=utc_now_iso(),
            sample_adequacy=sample,
            time_span_plan=time_span_plan,
            sample_adequate=sample.adequate_for_rejection and sample.adequate_for_promotion,
            token_shortfall=token_shortfall,
            time_span_shortfall_seconds=span_shortfall,
            selected_count_shortfall=selected_shortfall,
            recommended_next_action=sample.recommended_data_expansion,
            recommended_bounded_command=time_span_plan.recommended_next_command,
            warning_flags=sorted(set(warnings + sample.warning_flags + time_span_plan.warning_flags)),
            metadata_json={
                "min_real_token_count": self.min_real_token_count,
                "min_time_span_seconds": self.min_time_span_seconds,
                "min_valid_test_folds": self.min_valid_test_folds,
                "min_total_test_selected_count": self.min_total_test_selected_count,
                "min_independent_batches": self.min_independent_batches,
                "candidate_limit": candidate_limit,
                "min_liquidity_usd": min_liquidity_usd,
            },
        )
