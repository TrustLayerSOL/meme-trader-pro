"""Bounded Pump.fun create-instruction scanner."""

from __future__ import annotations

import time
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.ingestion.pumpfun_create_scanner_models import (
    PumpFunCreateCandidate,
    PumpFunInstructionDiagnostic,
    PumpFunCreateScanBatch,
    PumpFunCreateScanReport,
    make_pumpfun_create_scan_report_id,
    utc_now_iso,
)
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


SOL_MINT = "So11111111111111111111111111111111111111112"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
PUMPFUN_CREATE_DISCRIMINATORS: dict[str, str] = {}


class PumpFunCreateScanner:
    def __init__(
        self,
        adapter: HeliusHistoricalAdapter | None = None,
        program_id: str = PUMP_FUN_PROGRAM_ID,
    ):
        self.adapter = adapter
        self.program_id = program_id

    def scan(
        self,
        *,
        execute: bool = False,
        max_batches: int = 5,
        signatures_per_batch: int = 25,
        hydrate_limit_per_batch: int = 25,
        target_create_candidates: int = 5,
        max_signatures_total: int = 250,
        cursor_before: str | None = None,
        include_low_confidence: bool = False,
        emit_rejected_examples: bool = False,
        min_confidence: str = "medium",
    ) -> PumpFunCreateScanReport:
        report = PumpFunCreateScanReport(
            report_id="pumpfun_create_scan_plan" if not execute else make_pumpfun_create_scan_report_id(),
            created_at=utc_now_iso(),
            program_id=self.program_id,
            executed=execute,
            max_batches=max_batches,
            signatures_per_batch=signatures_per_batch,
            hydrate_limit_per_batch=hydrate_limit_per_batch,
            warning_flags=["bounded_discovery_probe_not_launch_dataset"],
            metadata_json={
                "include_low_confidence": include_low_confidence,
                "emit_rejected_examples": emit_rejected_examples,
                "min_confidence": min_confidence,
                "pumpfun_create_discriminator": "unknown_pending_fixture",
            },
        )
        if not execute:
            report.viability = "unknown"
            report.recommended_next_action = "review dry-run limits before execute"
            report.metadata_json["network_calls"] = 0
            return report

        adapter = self.adapter or HeliusHistoricalAdapter.from_env()
        before = cursor_before
        seen = 0
        for batch_index in range(max_batches):
            if seen >= max_signatures_total or report.create_candidate_count >= target_create_candidates:
                break
            started = time.monotonic()
            limit = min(signatures_per_batch, max_signatures_total - seen)
            request = HeliusBackfillRequest(
                address=self.program_id,
                limit=limit,
                before=before,
                role="pumpfun_create_scan",
            )
            signature_result = adapter.fetch_signatures_for_address(request)
            signatures = [record.signature for record in signature_result.records]
            if not signatures:
                report.batches.append(
                    PumpFunCreateScanBatch(
                        batch_index=batch_index,
                        cursor_before=before,
                        elapsed_seconds=round(time.monotonic() - started, 6),
                        warning_flags=["no_signatures_returned"],
                    )
                )
                break

            hydrate_signatures = signatures[:hydrate_limit_per_batch]
            transactions = adapter.fetch_transactions(hydrate_signatures)
            candidates, rejected, unknown, direct_count = self._extract_candidates(
                transactions,
                target_create_candidates - report.create_candidate_count,
                include_low_confidence=include_low_confidence,
                min_confidence=min_confidence,
            )
            batch = PumpFunCreateScanBatch(
                batch_index=batch_index,
                signatures_seen=len(signatures),
                transactions_hydrated=len([tx for tx in transactions if tx]),
                direct_pumpfun_instruction_count=direct_count,
                create_candidate_count=len([candidate for candidate in candidates if _is_verified_candidate(candidate, min_confidence)]),
                rejected_create_like_count=len(rejected),
                unknown_pumpfun_instruction_count=len(unknown),
                cursor_before=before,
                next_cursor_before=signature_result.next_before,
                elapsed_seconds=round(time.monotonic() - started, 6),
            )
            report.batches.append(batch)
            report.candidates.extend(candidates)
            report.rejected_create_like_candidates.extend(rejected)
            report.unknown_pumpfun_instructions.extend(unknown)
            report.verified_create_candidates = _dedupe_candidates(
                [*report.verified_create_candidates, *[candidate for candidate in candidates if _is_verified_candidate(candidate, min_confidence)]]
            )
            report.signatures_seen_total += len(signatures)
            report.transactions_hydrated_total += batch.transactions_hydrated
            report.direct_pumpfun_instruction_count += direct_count
            report.create_candidate_count = len(report.verified_create_candidates)
            seen += len(signatures)
            before = signature_result.next_before
            if not before:
                break

        report.viability = _viability(report)
        report.recommended_next_action = _recommended_next_action(report.viability)
        if not emit_rejected_examples:
            report.rejected_create_like_candidates = report.rejected_create_like_candidates[:25]
            report.unknown_pumpfun_instructions = report.unknown_pumpfun_instructions[:25]
        report.candidates = _dedupe_candidates(report.candidates)
        report.metadata_json["network_calls_estimate"] = len(report.batches) + report.transactions_hydrated_total
        return report

    def _extract_candidates(
        self,
        transactions: list[dict[str, Any]],
        remaining_target: int,
        *,
        include_low_confidence: bool,
        min_confidence: str,
    ) -> tuple[list[PumpFunCreateCandidate], list[PumpFunInstructionDiagnostic], list[PumpFunInstructionDiagnostic], int]:
        candidates: list[PumpFunCreateCandidate] = []
        rejected: list[PumpFunInstructionDiagnostic] = []
        unknown: list[PumpFunInstructionDiagnostic] = []
        direct_count = 0
        for tx in transactions:
            if not tx:
                continue
            signature = _signature(tx)
            message = tx.get("transaction", {}).get("message", {})
            instructions = message.get("instructions", [])
            for index, instruction in enumerate(instructions):
                if instruction.get("programId") != self.program_id:
                    continue
                direct_count += 1
                candidate, diagnostic = _candidate_from_instruction(tx, instruction, signature, index, self.program_id)
                if candidate:
                    if include_low_confidence or _is_verified_candidate(candidate, min_confidence):
                        candidates.append(candidate)
                    else:
                        rejected.append(_diagnostic_from_candidate(candidate, ["below_min_confidence"]))
                    if len([item for item in candidates if _is_verified_candidate(item, min_confidence)]) >= remaining_target:
                        return candidates, rejected, unknown, direct_count
                elif diagnostic:
                    if diagnostic.instruction_classification == "rejected_create_like":
                        rejected.append(diagnostic)
                    else:
                        unknown.append(diagnostic)
        return candidates, rejected, unknown, direct_count


def _candidate_from_instruction(
    tx: dict[str, Any],
    instruction: dict[str, Any],
    signature: str | None,
    instruction_index: int,
    program_id: str,
) -> tuple[PumpFunCreateCandidate | None, PumpFunInstructionDiagnostic | None]:
    parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
    accounts = [str(account) for account in instruction.get("accounts", [])]
    parsed_type = str(parsed.get("type", "")).lower()
    warning_flags: list[str] = []
    discriminator = _instruction_discriminator(instruction)
    confidence = "unknown"
    is_create = False
    is_create_like = False

    if discriminator and discriminator in PUMPFUN_CREATE_DISCRIMINATORS:
        is_create = True
        confidence = PUMPFUN_CREATE_DISCRIMINATORS[discriminator]
    elif discriminator:
        return None, _instruction_diagnostic(
            signature,
            instruction_index,
            accounts,
            discriminator,
            "unknown_pumpfun_instruction",
            ["unknown_discriminator"],
        )
    elif parsed_type in {"create", "create_v1", "create_event", "initialize"}:
        is_create = True
        confidence = "high"
    elif program_id == PUMP_FUN_PROGRAM_ID and len(accounts) == 14:
        is_create = True
        confidence = "medium"
        warning_flags.append("heuristic_create_detection")
    elif program_id == PUMP_FUN_PROGRAM_ID and len(accounts) >= 12:
        is_create = True
        confidence = "low"
        warning_flags.append("low_confidence_heuristic_create_detection")
    if not is_create:
        return None, _instruction_diagnostic(
            signature,
            instruction_index,
            accounts,
            discriminator,
            "rejected_create_like" if is_create_like else "unknown_pumpfun_instruction",
            ["layout_not_verified_create"] if is_create_like else ["not_create_layout"],
        )

    token_mint = accounts[0] if len(accounts) > 0 else None
    bonding_curve = accounts[2] if len(accounts) > 2 else None
    associated_bonding_curve = accounts[3] if len(accounts) > 3 else None
    creator_wallet = accounts[7] if len(accounts) > 7 else None
    missing = [
        name
        for name, value in {
            "token_mint": token_mint,
            "bonding_curve": bonding_curve,
            "creator_wallet": creator_wallet,
            "block_time": tx.get("blockTime"),
        }.items()
        if value is None
    ]
    if missing:
        warning_flags.append("missing_" + "_".join(missing))
    if token_mint in {SOL_MINT, SYSTEM_PROGRAM}:
        warning_flags.append("invalid_token_mint")
    if bonding_curve in {SOL_MINT, SYSTEM_PROGRAM}:
        warning_flags.append("invalid_bonding_curve")
    if creator_wallet in {SYSTEM_PROGRAM, SOL_MINT}:
        warning_flags.append("invalid_creator_wallet")
    distinct_values = [value for value in [token_mint, bonding_curve, associated_bonding_curve, creator_wallet] if value]
    if len(set(distinct_values)) != len(distinct_values):
        warning_flags.append("non_distinct_create_accounts")
    if creator_wallet and not _is_signer_or_fee_payer(tx, creator_wallet):
        warning_flags.append("creator_wallet_not_signer_or_fee_payer")

    candidate = PumpFunCreateCandidate(
        signature=signature or "",
        slot=tx.get("slot"),
        block_time=tx.get("blockTime") if isinstance(tx.get("blockTime"), int) else None,
        token_mint=token_mint,
        bonding_curve=bonding_curve,
        associated_bonding_curve=associated_bonding_curve,
        creator_wallet=creator_wallet,
        instruction_index=instruction_index,
        account_count=len(accounts),
        instruction_discriminator=discriminator,
        extraction_confidence=confidence,
        warning_flags=warning_flags,
        metadata_json={"instruction_type": parsed_type or "program_instruction", "accounts": accounts[:16]},
    )
    if _sanity_rejection_reasons(candidate):
        return None, _diagnostic_from_candidate(candidate, _sanity_rejection_reasons(candidate))
    return candidate, None


def _instruction_discriminator(instruction: dict[str, Any]) -> str | None:
    data = instruction.get("data")
    if isinstance(data, str) and data:
        return data[:16]
    return None


def _instruction_diagnostic(
    signature: str | None,
    instruction_index: int,
    accounts: list[str],
    discriminator: str | None,
    classification: str,
    reasons: list[str],
) -> PumpFunInstructionDiagnostic:
    return PumpFunInstructionDiagnostic(
        signature=signature or "",
        instruction_index=instruction_index,
        account_count=len(accounts),
        instruction_discriminator=discriminator,
        instruction_classification=classification,
        rejection_reasons=reasons,
        metadata_json={"accounts": accounts[:16]},
    )


def _diagnostic_from_candidate(
    candidate: PumpFunCreateCandidate,
    reasons: list[str],
) -> PumpFunInstructionDiagnostic:
    return PumpFunInstructionDiagnostic(
        signature=candidate.signature,
        instruction_index=candidate.instruction_index,
        account_count=candidate.account_count,
        instruction_discriminator=candidate.instruction_discriminator,
        instruction_classification="rejected_create_like",
        rejection_reasons=reasons,
        metadata_json=candidate.metadata_json,
    )


def _signature(tx: dict[str, Any]) -> str | None:
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        return signatures[0]
    return tx.get("signature")


def _viability(report: PumpFunCreateScanReport) -> str:
    if len(report.verified_create_candidates) >= 3:
        return "viable"
    if report.verified_create_candidates or report.rejected_create_like_candidates:
        return "maybe_viable"
    if report.signatures_seen_total < 250:
        return "not_yet_proven"
    return "not_viable"


def _recommended_next_action(viability: str) -> str:
    if viability == "viable":
        return "build bounded launch candidate importer from create scanner"
    if viability == "maybe_viable":
        return "improve parser using saved examples"
    if viability == "not_yet_proven":
        return "run one larger bounded scan after review"
    return "try PumpSwap/Raydium source probe"


def _has_complete_create_fields(candidate: PumpFunCreateCandidate) -> bool:
    return bool(
        candidate.token_mint
        and candidate.bonding_curve
        and candidate.creator_wallet
        and candidate.block_time
        and candidate.extraction_confidence in {"high", "medium"}
        and not _sanity_rejection_reasons(candidate)
    )


def _sanity_rejection_reasons(candidate: PumpFunCreateCandidate) -> list[str]:
    return [
        flag for flag in candidate.warning_flags
        if flag.startswith("invalid_")
        or flag == "non_distinct_create_accounts"
        or flag == "creator_wallet_not_signer_or_fee_payer"
        or flag.startswith("missing_")
    ]


def _is_verified_candidate(candidate: PumpFunCreateCandidate, min_confidence: str) -> bool:
    return _has_complete_create_fields(candidate) and CONFIDENCE_RANK.get(candidate.extraction_confidence, 0) >= CONFIDENCE_RANK[min_confidence]


def _dedupe_candidates(candidates: list[PumpFunCreateCandidate]) -> list[PumpFunCreateCandidate]:
    output: list[PumpFunCreateCandidate] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()
    for candidate in candidates:
        key = (candidate.token_mint, candidate.block_time, candidate.bonding_curve)
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def _is_signer_or_fee_payer(tx: dict[str, Any], wallet: str) -> bool:
    account_keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
    if not account_keys:
        return True
    for index, account in enumerate(account_keys):
        if isinstance(account, dict):
            pubkey = account.get("pubkey")
            if pubkey == wallet and (account.get("signer") or index == 0):
                return True
        elif account == wallet and index == 0:
            return True
    return False
