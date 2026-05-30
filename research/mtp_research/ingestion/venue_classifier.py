"""Conservative venue classification for parsed Solana transactions."""

from __future__ import annotations

from research.mtp_research.ingestion.transaction_parser_models import (
    TransactionSummary,
    VenueClassification,
)


# TODO: Replace these partial placeholder sets with verified program-id constants.
PARSER_PROGRAM_IDS: dict[str, set[str]] = {
    "raydium": set(),
    "pump": set(),
    "pumpswap": set(),
    "jupiter": set(),
}


def classify_venue(summary: TransactionSummary) -> VenueClassification:
    program_ids = {program.program_id for program in summary.programs}

    raydium_matches = sorted(program_ids & PARSER_PROGRAM_IDS["raydium"])
    if raydium_matches:
        return VenueClassification(
            venue="raydium",
            confidence=0.7,
            matched_program_ids=raydium_matches,
            reasons=["matched_raydium_program_id"],
        )

    pump_matches = sorted(
        program_ids & (PARSER_PROGRAM_IDS["pump"] | PARSER_PROGRAM_IDS["pumpswap"])
    )
    if pump_matches:
        return VenueClassification(
            venue="pump_or_pumpswap",
            confidence=0.7,
            matched_program_ids=pump_matches,
            reasons=["matched_pump_or_pumpswap_program_id"],
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
