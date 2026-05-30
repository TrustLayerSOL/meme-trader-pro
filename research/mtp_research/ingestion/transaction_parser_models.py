"""Parser models for Solana jsonParsed transaction summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransactionAccountSummary:
    pubkey: str
    signer: bool = False
    writable: bool = False
    source: str | None = None


@dataclass
class ProgramInvocation:
    program_id: str
    program: str | None = None
    instruction_type: str | None = None
    index: int | None = None
    inner_index: int | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenBalanceDelta:
    owner: str | None
    account: str | None
    mint: str
    pre_amount: float | None
    post_amount: float | None
    delta: float | None
    decimals: int | None
    ui_amount_string_pre: str | None = None
    ui_amount_string_post: str | None = None


@dataclass
class VenueClassification:
    venue: str
    confidence: float
    matched_program_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class TransactionSummary:
    signature: str
    slot: int | None
    block_time: int | None
    success: bool | None
    fee_lamports: int | None
    accounts: list[TransactionAccountSummary]
    programs: list[ProgramInvocation]
    token_balance_deltas: list[TokenBalanceDelta]
    venue_classification: VenueClassification | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
