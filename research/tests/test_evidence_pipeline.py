from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillResult,
    HeliusTransactionRecord,
)
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.evidence_models import EvidenceRunConfig
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline


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
    assert raw_store.get_by_signature("sig-1") is not None


def test_missing_helius_api_key_handled_for_execute_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
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
    )
    summary = pipeline.run_offline_rebuild(EvidenceRunConfig("run-1", dry_run=False))
    assert "offline_rebuild_no_network_calls" in summary.warning_flags
    assert summary.metadata_json["parse"]["processed"] == 0
