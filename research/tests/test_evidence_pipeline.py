from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillResult,
    HeliusTransactionRecord,
)
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.pipeline.evidence_models import EvidenceRunConfig
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


class FakeHeliusAdapter:
    def __init__(self):
        self.signature_calls = 0
        self.transaction_calls = 0

    def fetch_signatures_for_address(self, request):
        self.signature_calls += 1
        return HeliusBackfillResult(
            request=request,
            records=[
                HeliusTransactionRecord("sig-1", 1, 100, True, {}),
                HeliusTransactionRecord("sig-2", 2, 101, True, {}),
            ],
            next_before="sig-2",
        )

    def fetch_transactions(self, signatures):
        self.transaction_calls += 1
        return [
            {"slot": index + 1, "blockTime": 100 + index, "meta": {"err": None}}
            for index, _signature in enumerate(signatures)
        ]


class PaginatedFakeHeliusAdapter:
    def __init__(self):
        self.requests = []
        self.transaction_batches = []

    def fetch_signatures_for_address(self, request):
        self.requests.append(request)
        if request.before is None:
            return HeliusBackfillResult(
                request=request,
                records=[
                    HeliusTransactionRecord("sig-new-1", 3, 103, True, {}),
                    HeliusTransactionRecord("sig-new-2", 2, 102, True, {}),
                ],
                next_before="sig-new-2",
            )
        if request.before == "sig-new-2":
            return HeliusBackfillResult(
                request=request,
                records=[
                    HeliusTransactionRecord("sig-old-1", 1, 101, True, {}),
                    HeliusTransactionRecord("sig-old-2", 0, 100, True, {}),
                ],
                next_before="sig-old-2",
            )
        return HeliusBackfillResult(request=request, records=[], next_before=None)

    def fetch_transactions(self, signatures):
        self.transaction_batches.append(list(signatures))
        return [
            {
                "slot": index + 1,
                "blockTime": 100 + index,
                "meta": {"err": None},
                "transaction": {"signatures": [signature]},
            }
            for index, signature in enumerate(signatures)
        ]


def _candidate(token_mint: str = "mint-1") -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token_mint,
        source="test",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address="pool-1",
    )


def _registry(path: Path, count: int = 2) -> CandidateRegistry:
    registry = CandidateRegistry(path)
    for index in range(count):
        registry.upsert(_candidate(f"mint-{index}"))
    return registry


def test_select_candidates_respects_limit(tmp_path: Path) -> None:
    pipeline = EvidencePipeline(candidate_registry=_registry(tmp_path / "registry.jsonl", 3))
    assert len(pipeline.select_candidates(2)) == 2


def test_plan_targets_works(tmp_path: Path) -> None:
    pipeline = EvidencePipeline(candidate_registry=_registry(tmp_path / "registry.jsonl", 1))
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint", "pool"])
    assert {target.role for target in targets} == {"mint", "pool"}


def test_run_backfill_targets_dry_run_makes_no_adapter_calls(tmp_path: Path) -> None:
    adapter = FakeHeliusAdapter()
    pipeline = EvidencePipeline(candidate_registry=_registry(tmp_path / "registry.jsonl", 1), helius_adapter=adapter)
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint"])
    summary = pipeline.run_backfill_targets(targets, EvidenceRunConfig("run-1", dry_run=True), execute=False)
    assert adapter.signature_calls == 0
    assert "dry_run_no_network_calls" in summary.warning_flags


def test_run_backfill_targets_execute_uses_mocked_adapter_and_tracks_counts(tmp_path: Path) -> None:
    adapter = FakeHeliusAdapter()
    raw_store = RawTransactionStore(tmp_path / "raw.jsonl")
    pipeline = EvidencePipeline(
        candidate_registry=_registry(tmp_path / "registry.jsonl", 1),
        raw_transaction_store=raw_store,
        helius_adapter=adapter,
    )
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint"])
    summary = pipeline.run_backfill_targets(
        targets,
        EvidenceRunConfig("run-1", max_signatures_per_target=2, max_transactions_per_target=1, dry_run=False),
        execute=True,
    )
    assert adapter.signature_calls == 1
    assert adapter.transaction_calls == 1
    assert summary.signatures_seen == 2
    assert summary.transactions_fetched == 1
    assert summary.raw_transactions_inserted == 1
    assert summary.metadata_json["target_timings"]
    assert raw_store.get_by_signature("sig-1") is not None


def test_run_backfill_targets_can_fetch_bounded_signature_pages(tmp_path: Path) -> None:
    adapter = PaginatedFakeHeliusAdapter()
    raw_store = RawTransactionStore(tmp_path / "raw.jsonl")
    pipeline = EvidencePipeline(
        candidate_registry=_registry(tmp_path / "registry.jsonl", 1),
        raw_transaction_store=raw_store,
        helius_adapter=adapter,
    )
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint"])

    summary = pipeline.run_backfill_targets(
        targets,
        EvidenceRunConfig(
            "run-1",
            max_signatures_per_target=2,
            max_transactions_per_target=3,
            signature_pages_per_target=2,
            dry_run=False,
        ),
        execute=True,
    )

    assert [request.before for request in adapter.requests] == [None, "sig-new-2"]
    assert adapter.transaction_batches == [["sig-new-1", "sig-new-2"], ["sig-old-1"]]
    assert summary.signatures_seen == 4
    assert summary.transactions_fetched == 3
    assert raw_store.get_by_signature("sig-old-1") is not None
    assert raw_store.get_by_signature("sig-old-2") is None


def test_run_backfill_targets_skips_existing_signatures_while_paging(tmp_path: Path) -> None:
    adapter = PaginatedFakeHeliusAdapter()
    raw_store = RawTransactionStore(tmp_path / "raw.jsonl")
    raw_store.upsert(
        RawTransactionRecord(
            signature="sig-new-1",
            slot=3,
            block_time=103,
            success=True,
            address="mint-0",
            role="mint",
            token_mint="mint-0",
            fetched_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
            raw_json={"signature": "sig-new-1"},
        )
    )
    pipeline = EvidencePipeline(
        candidate_registry=_registry(tmp_path / "registry.jsonl", 1),
        raw_transaction_store=raw_store,
        helius_adapter=adapter,
    )
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint"])

    summary = pipeline.run_backfill_targets(
        targets,
        EvidenceRunConfig(
            "run-1",
            max_signatures_per_target=2,
            max_transactions_per_target=3,
            signature_pages_per_target=2,
            dry_run=False,
        ),
        execute=True,
    )

    assert adapter.transaction_batches == [["sig-new-2"], ["sig-old-1", "sig-old-2"]]
    assert summary.signatures_seen == 4
    assert summary.transactions_fetched == 3
    assert summary.raw_transactions_inserted == 3
    assert summary.raw_transactions_updated == 0


def test_missing_helius_api_key_handled_for_execute_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    pipeline = EvidencePipeline(candidate_registry=_registry(tmp_path / "registry.jsonl", 1))
    targets = pipeline.plan_targets(pipeline.select_candidates(), ["mint"])
    summary = pipeline.run_backfill_targets(
        targets,
        EvidenceRunConfig("run-1", dry_run=False),
        execute=True,
    )
    assert "missing_helius_api_key" in summary.warning_flags


def test_offline_rebuild_calls_local_components_without_network(tmp_path: Path) -> None:
    pipeline = EvidencePipeline(
        raw_transaction_store=RawTransactionStore(tmp_path / "raw.jsonl"),
        normalized_event_store=NormalizedEventStore(tmp_path / "events.jsonl"),
        feature_snapshot_store=FeatureSnapshotStore(tmp_path / "features.jsonl"),
        outcome_label_store=OutcomeLabelStore(tmp_path / "outcomes.jsonl"),
        research_dataset_store=ResearchDatasetStore(tmp_path / "dataset.jsonl"),
    )
    summary = pipeline.run_offline_rebuild(EvidenceRunConfig("run-1", dry_run=False))
    assert "offline_rebuild_no_network_calls" in summary.warning_flags
    assert summary.metadata_json["parse"]["processed"] == 0
