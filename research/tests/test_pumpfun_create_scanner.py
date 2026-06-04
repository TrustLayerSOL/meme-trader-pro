from dataclasses import dataclass

from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillRequest,
    HeliusBackfillResult,
    HeliusTransactionRecord,
)
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


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


def _base58_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    leading_zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeroes + (encoded or "1")


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


def test_create_v2_fixture_extracts_fixture_confirmed_layout() -> None:
    tx = _create_tx("sig-1", account_count=14)
    accounts = tx["transaction"]["message"]["instructions"][0]["accounts"]
    accounts[5] = "creator-sig-1"
    accounts.extend(["wrapped-sol", "extra-a"])
    tx["transaction"]["message"]["instructions"][0]["data"] = _base58_encode(bytes.fromhex("d6904cec5f8b31b4") + b"fixture")
    tx["transaction"]["message"]["accountKeys"] = [{"pubkey": "creator-sig-1", "signer": True}]
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1, min_confidence="high")

    assert report.create_candidate_count == 1
    candidate = report.verified_create_candidates[0]
    assert candidate.instruction_discriminator == "d6904cec5f8b31b4"
    assert candidate.extraction_confidence == "high"
    assert candidate.token_mint == "mint-sig-1"
    assert candidate.bonding_curve == "bonding-sig-1"
    assert candidate.associated_bonding_curve == "assoc-bonding-sig-1"
    assert candidate.creator_wallet == "creator-sig-1"
    assert candidate.metadata_json["instruction_type"] == "create_v2"


def test_recent_pumpfun_create_layout_extracts_live_confirmed_fields() -> None:
    tx = _create_tx("sig-1", account_count=14)
    accounts = [
        "global",
        "mint_authority",
        "recent-mint-pump",
        "recent-bonding-curve",
        "recent-associated-bonding-curve",
        "metadata-account",
        "recent-creator",
        "11111111111111111111111111111111",
        "token-2022-program",
        "metadata-program",
        "event-authority",
        PUMP_FUN_PROGRAM_ID,
        "fee-config",
        "fee-program",
        "extra-a",
        "extra-b",
    ]
    tx["transaction"]["message"]["instructions"][0]["accounts"] = accounts
    tx["transaction"]["message"]["instructions"][0]["data"] = _base58_encode(bytes.fromhex("33e685a4017f83ad") + b"fixture")
    tx["transaction"]["message"]["accountKeys"] = [{"pubkey": "recent-creator", "signer": True}]
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1, min_confidence="high")

    assert report.create_candidate_count == 1
    candidate = report.verified_create_candidates[0]
    assert candidate.instruction_discriminator == "33e685a4017f83ad"
    assert candidate.extraction_confidence == "high"
    assert candidate.token_mint == "recent-mint-pump"
    assert candidate.bonding_curve == "recent-bonding-curve"
    assert candidate.associated_bonding_curve == "recent-associated-bonding-curve"
    assert candidate.creator_wallet == "recent-creator"
    assert candidate.metadata_json["instruction_type"] == "create_live_v3"


def test_recent_pumpfun_create_v4_layout_extracts_live_confirmed_fields() -> None:
    tx = _create_tx("sig-1", account_count=14)
    accounts = [
        "global",
        "mint_authority",
        "recent-mint-pump",
        "recent-bonding-curve",
        "recent-associated-bonding-curve",
        "metadata-account",
        "recent-creator",
        "11111111111111111111111111111111",
        "token-2022-program",
        "metadata-program",
        "event-authority",
        PUMP_FUN_PROGRAM_ID,
        "extra-a",
        "extra-b",
        "fee-config",
        "fee-program",
        "extra-c",
        "extra-d",
    ]
    tx["transaction"]["message"]["instructions"][0]["accounts"] = accounts
    tx["transaction"]["message"]["instructions"][0]["data"] = _base58_encode(bytes.fromhex("66063d1201daebea") + b"fixture")
    tx["transaction"]["message"]["accountKeys"] = [{"pubkey": "recent-creator", "signer": True}]
    adapter = FakeAdapter(batches=[["sig-1"]], transactions_by_signature={"sig-1": tx})
    scanner = PumpFunCreateScanner(adapter=adapter)

    report = scanner.scan(execute=True, max_batches=1, signatures_per_batch=1, min_confidence="high")

    assert report.create_candidate_count == 1
    candidate = report.verified_create_candidates[0]
    assert candidate.instruction_discriminator == "66063d1201daebea"
    assert candidate.extraction_confidence == "high"
    assert candidate.token_mint == "recent-mint-pump"
    assert candidate.bonding_curve == "recent-bonding-curve"
    assert candidate.associated_bonding_curve == "recent-associated-bonding-curve"
    assert candidate.creator_wallet == "recent-creator"
    assert candidate.metadata_json["instruction_type"] == "create_live_v4"


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
