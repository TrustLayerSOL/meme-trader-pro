"""Bounded Pump.fun create-instruction scanner."""

from __future__ import annotations

import time
from typing import Any

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.ingestion.pumpfun_create_scanner_models import (
    PumpFunCreateCandidate,
    PumpFunCreateScanBatch,
    PumpFunCreateScanReport,
    make_pumpfun_create_scan_report_id,
    utc_now_iso,
)
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


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
            candidates, direct_count = self._extract_candidates(transactions, target_create_candidates - report.create_candidate_count)
            batch = PumpFunCreateScanBatch(
                batch_index=batch_index,
                signatures_seen=len(signatures),
                transactions_hydrated=len([tx for tx in transactions if tx]),
                direct_pumpfun_instruction_count=direct_count,
                create_candidate_count=len(candidates),
                cursor_before=before,
                next_cursor_before=signature_result.next_before,
                elapsed_seconds=round(time.monotonic() - started, 6),
            )
            report.batches.append(batch)
            report.candidates.extend(candidates)
            report.signatures_seen_total += len(signatures)
            report.transactions_hydrated_total += batch.transactions_hydrated
            report.direct_pumpfun_instruction_count += direct_count
            report.create_candidate_count += len(candidates)
            seen += len(signatures)
            before = signature_result.next_before
            if not before:
                break

        report.viability = _viability(report)
        report.recommended_next_action = _recommended_next_action(report.viability)
        report.metadata_json["network_calls_estimate"] = len(report.batches) + report.transactions_hydrated_total
        return report

    def _extract_candidates(
        self,
        transactions: list[dict[str, Any]],
        remaining_target: int,
    ) -> tuple[list[PumpFunCreateCandidate], int]:
        candidates: list[PumpFunCreateCandidate] = []
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
                candidate = _candidate_from_instruction(tx, instruction, signature, index, self.program_id)
                if candidate:
                    candidates.append(candidate)
                    if len(candidates) >= remaining_target:
                        return candidates, direct_count
        return candidates, direct_count


def _candidate_from_instruction(
    tx: dict[str, Any],
    instruction: dict[str, Any],
    signature: str | None,
    instruction_index: int,
    program_id: str,
) -> PumpFunCreateCandidate | None:
    parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
    accounts = [str(account) for account in instruction.get("accounts", [])]
    parsed_type = str(parsed.get("type", "")).lower()
    warning_flags: list[str] = []
    discriminator = _instruction_discriminator(instruction)
    confidence = "unknown"
    is_create = False

    if parsed_type in {"create", "create_v1", "create_event", "initialize"}:
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
        return None

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
    if bonding_curve in {"So11111111111111111111111111111111111111112", "11111111111111111111111111111111"}:
        warning_flags.append("invalid_bonding_curve")
    if creator_wallet in {"11111111111111111111111111111111", "So11111111111111111111111111111111111111112"}:
        warning_flags.append("invalid_creator_wallet")

    return PumpFunCreateCandidate(
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


def _instruction_discriminator(instruction: dict[str, Any]) -> str | None:
    data = instruction.get("data")
    if isinstance(data, str) and data:
        return data[:16]
    return None


def _signature(tx: dict[str, Any]) -> str | None:
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        return signatures[0]
    return tx.get("signature")


def _viability(report: PumpFunCreateScanReport) -> str:
    complete = [
        candidate for candidate in report.candidates
        if _has_complete_create_fields(candidate)
    ]
    if len(complete) >= 3:
        return "viable"
    if report.create_candidate_count:
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
        and "invalid_bonding_curve" not in candidate.warning_flags
        and "invalid_creator_wallet" not in candidate.warning_flags
    )
