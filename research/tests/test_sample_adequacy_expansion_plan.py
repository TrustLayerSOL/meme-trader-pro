from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.sample_adequacy_expansion_planner import (
    SampleAdequacyExpansionPlanner,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def _candidate(token: str, pool: str, liquidity: float = 20_000) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token,
        source="dexscreener",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address=pool,
        liquidity_usd=liquidity,
    )


def _row(row_id: str, token: str, ts: int) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token,
        snapshot_ts=ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="1m",
        horizon_seconds=60,
    )


def _validation() -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at=utc_now_iso(),
        config=WalkForwardConfig("cfg", 900, 300, 300),
        dataset_path="dataset.jsonl",
        row_count=10,
        filtered_row_count=10,
        fold_count=1,
        rules_tested=1,
        rule_summaries=[
            RuleWalkForwardSummary(
                rule_id="rule-1",
                rule_name="Rule 1",
                valid_test_fold_count=2,
                total_test_selected_count=20,
            )
        ],
    )


def test_expansion_plan_recommends_candidates_and_time_span(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    wf_path = tmp_path / "wf.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    event_path = tmp_path / "events.jsonl"
    feature_path = tmp_path / "features.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    registry = CandidateRegistry(registry_path)
    registry.upsert(_candidate("token-1", "pool-1"))
    registry.upsert(_candidate("token-2", "pool-2"))
    ResearchDatasetStore(dataset_path).upsert(_row("1", "token-1", 100))
    ResearchDatasetStore(dataset_path).upsert(_row("2", "token-2", 200))
    WalkForwardValidationStore(wf_path).upsert(_validation())

    plan = SampleAdequacyExpansionPlanner().build_plan(
        registry_path=registry_path,
        dataset_path=dataset_path,
        walk_forward_store_path=wf_path,
        candidate_limit=10,
        raw_store_path=raw_path,
        event_store_path=event_path,
        feature_store_path=feature_path,
        outcome_store_path=outcome_path,
    )

    assert plan.sample_adequate is False
    assert plan.token_shortfall == 8
    assert plan.recommended_next_action == "add_more_real_candidates_and_expand_time_span"
    assert plan.time_span_plan.plan_items
    assert "dry_run_only_no_helius" in plan.warning_flags
