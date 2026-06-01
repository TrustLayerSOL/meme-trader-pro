from dataclasses import dataclass

from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillRequest,
    HeliusBackfillResult,
    HeliusTransactionRecord,
)
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


@dataclass
class FakeAdapter:
    batches: list[list[str]]
    transactions_by_signature: dict[str, dict]

    def __post_init__(self) -> None:
        self.signature_calls = 0
        self.transaction_calls = 0
        self.requests: list[HeliusBackfillRequest] = []

    def fetch_signatures_for_address(self, request: HeliusBackfillRequest) -> HeliusBackfillResult:
        self.requests.append(request)
        index = self.signature_calls
        self.signature_calls += 1
        signatures = self.batches[index] if index < len(self.batches) else []
        return HeliusBackfillResult(
            request=request,
            records=[
                HeliusTransactionRecord(
                    signature=signature,
                    slot=index,
                    block_time=1_780_000_000 + index,
                    success=True,
                    raw_json={"signature": signature},
                )
                for signature in signatures
            ],
            next_before=signatures[-1] if signatures else None,
        )

    def fetch_transactions(self, signatures: list[str]) -> list[dict]:
        self.transaction_calls += len(signatures)
        return [self.transactions_by_signature.get(signature, {}) for signature in signatures]


def _create_tx(signature: str, account_count: int = 14) -> dict:
    accounts = [
        f"mint-{signature}",
        "mint-authority",
        f"bonding-{signature}",
        f"assoc-bonding-{signature}",
        "global",
        "metadata-program",
        "metadata-account",
        f"creator-{signature}",
        "system-program",
        "token-program",
        "associated-token-program",
        "rent",
        "event-authority",
        PUMP_FUN_PROGRAM_ID,
    ][:account_count]
    return {
        "slot": 100,
        "blockTime": 1_780_000_000,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [{"pubkey": f"creator-{signature}", "signer": True}],
                "instructions": [{"programId": PUMP_FUN_PROGRAM_ID, "accounts": accounts}],
            },
        },
    }


def test_dry_run_performs_no_network() -> None:
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=False)

    assert report.executed is False
    assert report.signatures_seen_total == 0
    assert adapter.signature_calls == 0


def test_known_create_fixture_extracts_fields_and_stops_after_target() -> None:
    adapter = FakeAdapter(
        batches=[["sig-1", "sig-2"]],
        transactions_by_signature={"sig-1": _create_tx("sig-1"), "sig-2": _create_tx("sig-2")},
    )
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, target_create_candidates=1, max_batches=5, signatures_per_batch=25)

    assert report.create_candidate_count == 1
    assert report.candidates[0].token_mint == "mint-sig-1"
    assert report.verified_create_candidates[0].token_mint == "mint-sig-1"
    assert report.candidates[0].bonding_curve == "bonding-sig-1"
    assert report.candidates[0].creator_wallet == "creator-sig-1"
    assert report.candidates[0].extraction_confidence == "medium"
    assert adapter.signature_calls == 1


def test_non_create_ten_account_instruction_is_not_classified_as_create() -> None:
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": _create_tx("sig-1", account_count=10)})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=25)

    assert report.direct_pumpfun_instruction_count == 1
    assert report.create_candidate_count == 0
    assert len(report.unknown_pumpfun_instructions) == 1
    assert report.viability == "not_yet_proven"


def test_low_confidence_placeholder_accounts_are_not_create_candidates() -> None:
    tx = _create_tx("sig-1", account_count=12)
    tx["transaction"]["message"]["instructions"][0]["accounts"][2] = "So11111111111111111111111111111111111111112"
    tx["transaction"]["message"]["instructions"][0]["accounts"][7] = "11111111111111111111111111111111"
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1)

    assert report.direct_pumpfun_instruction_count == 1
    assert report.create_candidate_count == 0
    assert len(report.rejected_create_like_candidates) == 1
    assert report.viability == "maybe_viable"


def test_unknown_discriminator_is_not_classified_as_create_by_default() -> None:
    tx = _create_tx("sig-1")
    tx["transaction"]["message"]["instructions"][0]["data"] = "unknownDiscriminatorPayload"
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1)

    assert report.create_candidate_count == 0
    assert len(report.unknown_pumpfun_instructions) == 1
    assert report.unknown_pumpfun_instructions[0].rejection_reasons == ["unknown_discriminator"]


def test_include_low_confidence_keeps_diagnostics_out_of_verified_count() -> None:
    tx = _create_tx("sig-1", account_count=12)
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1, include_low_confidence=True, min_confidence="medium")

    assert report.create_candidate_count == 0
    assert len(report.candidates) == 1
    assert len(report.verified_create_candidates) == 0
    assert report.candidates[0].extraction_confidence == "low"


def test_same_token_repeated_candidates_are_not_counted_multiple_times() -> None:
    tx = _create_tx("sig-1")
    instruction = tx["transaction"]["message"]["instructions"][0]
    tx["transaction"]["message"]["instructions"] = [instruction, dict(instruction)]
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1)

    assert report.direct_pumpfun_instruction_count == 2
    assert report.create_candidate_count == 1


def test_scanner_respects_max_batches() -> None:
    adapter = FakeAdapter(
        batches=[["sig-1"], ["sig-2"], ["sig-3"]],
        transactions_by_signature={"sig-1": {}, "sig-2": {}, "sig-3": {}},
    )
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=2, signatures_per_batch=1)

    assert len(report.batches) == 2
    assert adapter.signature_calls == 2


def test_scanner_respects_max_signatures_total() -> None:
    adapter = FakeAdapter(
        batches=[["sig-1", "sig-2", "sig-3"], ["sig-4"]],
        transactions_by_signature={signature: {} for signature in ["sig-1", "sig-2", "sig-3", "sig-4"]},
    )
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=5, signatures_per_batch=3, max_signatures_total=3)

    assert report.signatures_seen_total == 3
    assert adapter.signature_calls == 1
