import json
from pathlib import Path

from research.mtp_research.ingestion.pumpfun_create_scanner_models import (
    PumpFunCreateCandidate,
    PumpFunCreateScanBatch,
    PumpFunCreateScanReport,
)
from research.mtp_research.validation.forward_efficient_mover_observer import (
    ForwardObserverConfig,
    PumpFunCreateScannerCandidateSource,
    build_birth_watch_candidate_from_create_candidate,
    read_jsonl,
    run_observe,
)


class FakeCreateScanner:
    def __init__(self, reports: list[PumpFunCreateScanReport]) -> None:
        self.reports = reports
        self.calls: list[dict] = []

    def scan(self, **kwargs) -> PumpFunCreateScanReport:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.reports) - 1)
        return self.reports[index]


def test_build_birth_watch_candidate_from_verified_create() -> None:
    candidate = build_birth_watch_candidate_from_create_candidate(_create_candidate("mint-a"))

    assert candidate["mint"] == "mint-a"
    assert candidate["event_type"] == "pumpfun_create"
    assert candidate["fdv_proxy"] is None
    assert candidate["freshness_lane"] == "birth_watch"
    assert candidate["candidate_classification"] == "pumpfun_birth_candidate_observed"
    assert candidate["status"] == "watching_pre_trigger"
    assert candidate["pool_address"] == "bonding-mint-a"
    assert candidate["launch_time"] == 1_780_000_000
    assert candidate["parse_confidence"] == "high"


def test_create_scanner_source_fetches_birth_candidates_and_writes_scan_report(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpfun-create-scanner",
        enable_birth_watch_candidates=True,
        max_helius_credits=10,
        birth_scan_max_batches=1,
        birth_scan_signatures_per_batch=2,
        birth_scan_hydrate_limit_per_batch=2,
        birth_scan_target_create_candidates=1,
        birth_scan_max_signatures_total=2,
    )
    scanner = FakeCreateScanner([_scan_report([_create_candidate("mint-a")])])
    source = PumpFunCreateScannerCandidateSource(config=config, scanner=scanner)

    candidates = source.fetch_candidates()

    assert len(candidates) == 1
    assert candidates[0]["mint"] == "mint-a"
    assert source.requests_used == 3
    assert scanner.calls[0]["cursor_before"] is None
    assert source.cursor_before == "cursor-next"
    reports = sorted((config.report_root / "birth_watch_create_scanner").glob("*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["create_candidate_count"] == 1


def test_create_scanner_source_carries_cursor_between_fetches(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpfun-create-scanner",
        enable_birth_watch_candidates=True,
        max_helius_credits=10,
        birth_scan_max_batches=1,
        birth_scan_signatures_per_batch=2,
        birth_scan_hydrate_limit_per_batch=2,
        birth_scan_target_create_candidates=1,
        birth_scan_max_signatures_total=2,
    )
    scanner = FakeCreateScanner(
        [
            _scan_report([_create_candidate("mint-a")], cursor="cursor-a"),
            _scan_report([_create_candidate("mint-b")], cursor="cursor-b"),
        ]
    )
    source = PumpFunCreateScannerCandidateSource(config=config, scanner=scanner)

    assert source.fetch_candidates()[0]["mint"] == "mint-a"
    assert source.fetch_candidates()[0]["mint"] == "mint-b"

    assert scanner.calls[0]["cursor_before"] is None
    assert scanner.calls[1]["cursor_before"] == "cursor-a"
    assert source.cursor_before == "cursor-b"


def test_create_scanner_source_blocks_when_projected_requests_exceed_cap(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpfun-create-scanner",
        enable_birth_watch_candidates=True,
        max_helius_credits=10,
        birth_scan_max_batches=2,
        birth_scan_signatures_per_batch=10,
        birth_scan_hydrate_limit_per_batch=10,
        birth_scan_max_signatures_total=20,
    )
    source = PumpFunCreateScannerCandidateSource(config=config, scanner=FakeCreateScanner([]))

    availability = source.availability()

    assert availability["available"] is False
    assert availability["missing_reason"] == "projected_birth_scan_requests_exceed_helius_credit_cap"
    assert availability["projected_requests"] == 22


def test_run_observe_writes_create_scanner_birth_watch_rows(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpfun-create-scanner",
        target_candidates=1,
        max_observe_iterations=1,
        max_helius_credits=10,
        enable_birth_watch_candidates=True,
        birth_scan_max_batches=1,
        birth_scan_signatures_per_batch=2,
        birth_scan_hydrate_limit_per_batch=2,
        birth_scan_target_create_candidates=1,
        birth_scan_max_signatures_total=2,
    )
    scanner = FakeCreateScanner([_scan_report([_create_candidate("mint-a")])])
    source = PumpFunCreateScannerCandidateSource(config=config, scanner=scanner)

    result = run_observe(config, source=source)
    candidates = read_jsonl(config.observation_root / "candidates.jsonl")
    paths = read_jsonl(config.observation_root / "candidate_paths.jsonl")

    assert result["total_candidates_observed"] == 1
    assert result["helius_requests_used"] == 3
    assert candidates[0]["candidate_classification"] == "pumpfun_birth_candidate_observed"
    assert candidates[0]["trigger_timestamp"] is None
    assert paths[0]["fdv_proxy"] is None
    assert paths[0]["freshness_lane"] == "birth_watch"
    assert paths[0]["event_type"] == "pumpfun_create"


def test_run_observe_requires_birth_watch_enable_for_scanner_birth_rows(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpfun-create-scanner",
        target_candidates=1,
        max_observe_iterations=1,
        max_helius_credits=10,
        enable_birth_watch_candidates=False,
        birth_scan_max_batches=1,
        birth_scan_signatures_per_batch=2,
        birth_scan_hydrate_limit_per_batch=2,
        birth_scan_target_create_candidates=1,
        birth_scan_max_signatures_total=2,
    )
    scanner = FakeCreateScanner([_scan_report([_create_candidate("mint-a")])])
    source = PumpFunCreateScannerCandidateSource(config=config, scanner=scanner)

    result = run_observe(config, source=source)

    assert result["total_candidates_observed"] == 0
    assert not (config.observation_root / "candidates.jsonl").exists()


def _create_candidate(mint: str) -> PumpFunCreateCandidate:
    return PumpFunCreateCandidate(
        signature=f"sig-{mint}",
        slot=123,
        block_time=1_780_000_000,
        token_mint=mint,
        bonding_curve=f"bonding-{mint}",
        associated_bonding_curve=f"associated-{mint}",
        creator_wallet=f"creator-{mint}",
        instruction_index=2,
        account_count=16,
        instruction_discriminator="d6904cec5f8b31b4",
        extraction_confidence="high",
        metadata_json={"instruction_type": "create_v2"},
    )


def _scan_report(candidates: list[PumpFunCreateCandidate], *, cursor: str = "cursor-next") -> PumpFunCreateScanReport:
    report = PumpFunCreateScanReport(
        report_id=f"scan-{len(candidates)}-{cursor}",
        created_at="2026-06-03T00:00:00+00:00",
        program_id="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
        executed=True,
        max_batches=1,
        signatures_per_batch=2,
        hydrate_limit_per_batch=2,
        signatures_seen_total=2,
        transactions_hydrated_total=2,
        direct_pumpfun_instruction_count=2,
        create_candidate_count=len(candidates),
        candidates=candidates,
        verified_create_candidates=candidates,
        batches=[
            PumpFunCreateScanBatch(
                batch_index=0,
                signatures_seen=2,
                transactions_hydrated=2,
                direct_pumpfun_instruction_count=2,
                create_candidate_count=len(candidates),
                next_cursor_before=cursor,
            )
        ],
        viability="maybe_viable",
        recommended_next_action="bridge_verified_creates_to_birth_watch",
        metadata_json={"network_calls_estimate": 3},
    )
    return report
