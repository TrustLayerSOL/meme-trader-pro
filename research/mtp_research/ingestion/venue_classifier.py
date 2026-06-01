"""Conservative venue classification for parsed Solana transactions."""

from __future__ import annotations

from research.mtp_research.ingestion.transaction_parser_models import (
    TransactionSummary,
    VenueClassification,
)


# TODO: Replace these partial placeholder sets with verified program-id constants.
PARSER_PROGRAM_IDS: dict[str, set[str]] = {
    "raydium": set(),
    "pump": {"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"},
    "pumpswap": set(),
    "jupiter": set(),
}


def classify_venue(summary: TransactionSummary) -> VenueClassification:
    program_ids = {program.program_id for program in summary.programs}
    instruction_logs = _instruction_logs(summary)

    pumpfun_matches = sorted(program_ids & PARSER_PROGRAM_IDS["pump"])
    if pumpfun_matches:
        if not _has_valid_pumpfun_account_layout(summary):
            return VenueClassification(
                venue="unknown",
                confidence=0.0,
                matched_program_ids=pumpfun_matches,
                reasons=["pumpfun_program_seen_with_invalid_account_layout"],
            )
        pumpfun_classification = _classify_pumpfun_instruction(instruction_logs)
        if pumpfun_classification:
            return VenueClassification(
                venue=pumpfun_classification,
                confidence=0.95,
                matched_program_ids=pumpfun_matches,
                reasons=[f"matched_pumpfun_program_id_and_{_pumpfun_reason_name(pumpfun_classification)}_instruction_log"],
            )
        if summary.token_balance_deltas:
            return VenueClassification(
                venue="unknown_token_swap_candidate",
                confidence=0.35,
                matched_program_ids=pumpfun_matches,
                reasons=["pumpfun_program_seen_without_supported_instruction_log"],
            )

    raydium_matches = sorted(program_ids & PARSER_PROGRAM_IDS["raydium"])
    if raydium_matches:
        return VenueClassification(
            venue="raydium",
            confidence=0.7,
            matched_program_ids=raydium_matches,
            reasons=["matched_raydium_program_id"],
        )

    pump_matches = sorted(program_ids & PARSER_PROGRAM_IDS["pumpswap"])
    if pump_matches:
        return VenueClassification(
            venue="pumpswap_trade",
            confidence=0.7,
            matched_program_ids=pump_matches,
            reasons=["matched_pumpswap_program_id"],
        )

    jupiter_matches = sorted(program_ids & PARSER_PROGRAM_IDS["jupiter"])
    if jupiter_matches:
        return VenueClassification(
            venue="jupiter_route",
            confidence=0.7,
            matched_program_ids=jupiter_matches,
            reasons=["matched_jupiter_program_id"],
        )

    if summary.token_balance_deltas:
        return VenueClassification(
            venue="unknown_token_swap_candidate",
            confidence=0.3,
            matched_program_ids=[],
            reasons=["token_balance_deltas_present_without_known_venue"],
        )

    return VenueClassification(
        venue="unknown",
        confidence=0.0,
        matched_program_ids=[],
        reasons=["no_known_venue_program_or_token_deltas"],
    )


def _instruction_logs(summary: TransactionSummary) -> list[str]:
    raw_logs = (summary.raw_json.get("meta") or {}).get("logMessages") or []
    if not isinstance(raw_logs, list):
        return []
    output = []
    for item in raw_logs:
        if isinstance(item, str) and "Instruction:" in item:
            output.append(item)
    return output


def _classify_pumpfun_instruction(instruction_logs: list[str]) -> str | None:
    for log in instruction_logs:
        instruction = log.split("Instruction:", 1)[1].strip().lower()
        if instruction in {"buy", "buyv2", "buyexactsolin", "buyexactquoteinv2"}:
            return "pumpfun_buy"
        if instruction in {"sell", "sellv2"}:
            return "pumpfun_sell"
        if instruction in {"create", "createv2"}:
            return "pumpfun_create"
        if instruction in {"migrate", "migratev2"}:
            return "pumpfun_migrate"
    return None


def _pumpfun_reason_name(classification: str) -> str:
    return classification.removeprefix("pumpfun_")


def _has_valid_pumpfun_account_layout(summary: TransactionSummary) -> bool:
    for program in summary.programs:
        if program.program_id not in PARSER_PROGRAM_IDS["pump"]:
            continue
        accounts = program.raw_json.get("accounts") if isinstance(program.raw_json, dict) else None
        if isinstance(accounts, list) and len(accounts) >= 4:
            return True
    return False
