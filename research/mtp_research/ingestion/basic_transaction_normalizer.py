"""Basic raw-transaction normalizer for early v3 replay tests."""

from __future__ import annotations

from research.mtp_research.ingestion.normalization_models import (
    NormalizedEvent,
    make_event_id,
)
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.ingestion.transaction_parser_models import TransactionSummary


def raw_transaction_to_observed_event(record: RawTransactionRecord) -> NormalizedEvent:
    """Convert a raw transaction into a generic observed transaction event."""

    event_type = "transaction_observed"
    return NormalizedEvent(
        event_id=make_event_id(record.signature, event_type),
        signature=record.signature,
        slot=record.slot,
        block_time=record.block_time,
        event_type=event_type,
        token_mint=record.token_mint,
        source="raw_transaction_store",
        metadata_json={
            "raw_source": record.source,
            "address": record.address,
            "role": record.role,
            "success": record.success,
        },
    )


def transaction_summary_to_observed_event(summary: TransactionSummary) -> NormalizedEvent:
    """Convert a parsed transaction summary into an observed transaction event."""

    event_type = "transaction_observed"
    venue = summary.venue_classification.venue if summary.venue_classification else None
    venue_confidence = (
        summary.venue_classification.confidence if summary.venue_classification else None
    )
    venue_reasons = summary.venue_classification.reasons if summary.venue_classification else []
    program_ids = [program.program_id for program in summary.programs]
    token_mint = None
    if summary.token_balance_deltas:
        token_mint = summary.token_balance_deltas[0].mint

    return NormalizedEvent(
        event_id=make_event_id(summary.signature, event_type),
        signature=summary.signature,
        slot=summary.slot,
        block_time=summary.block_time,
        event_type=event_type,
        token_mint=token_mint,
        venue=venue,
        source="raw_transaction_store",
        metadata_json={
            "fee_lamports": summary.fee_lamports,
            "program_ids": program_ids,
            "token_balance_delta_count": len(summary.token_balance_deltas),
            "venue_confidence": venue_confidence,
            "venue_reasons": venue_reasons,
        },
    )
