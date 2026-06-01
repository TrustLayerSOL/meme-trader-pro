from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord, RawTransactionStore
from research.mtp_research.pipeline.time_span_backfill_planner import TimeSpanBackfillPlanner
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def _candidate(token: str, pool: str | None, is_mock: bool = False, liquidity: float = 20000) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token,
        source="dexscreener" if not is_mock else "mock",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        venue="raydium" if not is_mock else "mock",
        pool_address=pool,
        liquidity_usd=liquidity,
        metadata_json={"is_mock": is_mock},
    )


def _raw(sig: str, token: str, ts: int) -> RawTransactionRecord:
    return RawTransactionRecord(
        signature=sig,
        slot=1,
        block_time=ts,
        success=True,
        token_mint=token,
    )


def _event(event_id: str, token: str, ts: int, price: float | None = 1.0) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=f"sig-{event_id}",
        slot=1,
        block_time=ts,
        event_type="possible_buy",
        token_mint=token,
        price_quote=price,
    )


def _row(row_id: str, token: str) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token,
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        forward_return=0.1,
        label_quality="sparse",
    )


def test_planner_loads_only_real_candidates(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    registry = CandidateRegistry(registry_path)
    registry.upsert(_candidate("real-token", "pool-real"))
    registry.upsert(_candidate("mock-token", "pool-mock", is_mock=True))
    registry.upsert(_candidate("no-pool-token", None))

    candidates = TimeSpanBackfillPlanner().load_real_candidates(registry_path)

    assert [candidate.token_mint for candidate in candidates] == ["real-token"]


def test_coverage_computes_time_span_and_needs_backfill() -> None:
    candidate = _candidate("token-1", "pool-1")
    coverage = TimeSpanBackfillPlanner().build_token_coverage(
        [candidate],
        [_raw("sig-1", "token-1", 100), _raw("sig-2", "token-1", 200)],
        [_event("event-1", "token-1", 100), _event("event-2", "token-1", 200)],
        [FeatureSnapshot("snapshot-1", "token-1", 100, "1m", 60)],
        [OutcomeLabel("outcome-1", "snapshot-1", "token-1", 100, "5m", 300)],
        [_row("row-1", "token-1")],
        target_time_span_seconds=3600,
    )[0]

    assert coverage.time_span_seconds == 100
    assert coverage.trade_event_count == 2
    assert coverage.priced_event_count == 2
    assert coverage.needs_backfill is True
    assert "short_time_span" in coverage.warning_flags


def test_coverage_identifies_no_raw_token_needing_backfill() -> None:
    candidate = _candidate("token-1", "pool-1")
    coverage = TimeSpanBackfillPlanner().build_token_coverage(
        [candidate],
        [],
        [],
        [],
        [],
        [],
    )[0]

    assert coverage.raw_tx_count == 0
    assert coverage.needs_backfill is True
    assert "no_raw_transactions" in coverage.warning_flags


def test_plan_prioritizes_no_raw_and_uses_pool_targets_first(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    event_path = tmp_path / "events.jsonl"
    feature_path = tmp_path / "features.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    registry = CandidateRegistry(registry_path)
    registry.upsert(_candidate("no-raw", "pool-no-raw", liquidity=30000))
    registry.upsert(_candidate("short-span", "pool-short", liquidity=25000))
    RawTransactionStore(raw_path).upsert(_raw("sig-1", "short-span", 100))

    planner = TimeSpanBackfillPlanner(
        raw_store=RawTransactionStore(raw_path),
        event_store=NormalizedEventStore(event_path),
        feature_store=FeatureSnapshotStore(feature_path),
        outcome_store=OutcomeLabelStore(outcome_path),
        dataset_store=ResearchDatasetStore(dataset_path),
    )
    plan = planner.build_plan(registry_path=registry_path, min_liquidity_usd=10000, candidate_limit=2)

    assert plan.plan_items[0].token_mint == "no-raw"
    assert plan.plan_items[0].target_address == "pool-no-raw"
    assert plan.plan_items[0].role == "pool"
    assert len({item.target_address for item in plan.plan_items}) == len(plan.plan_items)
