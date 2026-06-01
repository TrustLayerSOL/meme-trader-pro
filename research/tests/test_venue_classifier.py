from research.mtp_research.ingestion.transaction_parser_models import (
    ProgramInvocation,
    TokenBalanceDelta,
    TransactionSummary,
)
from research.mtp_research.ingestion.venue_classifier import classify_venue

PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def _summary(
    programs: list[ProgramInvocation] | None = None,
    deltas: list[TokenBalanceDelta] | None = None,
    raw_record_role: str | None = None,
    raw_record_source: str | None = None,
    logs: list[str] | None = None,
) -> TransactionSummary:
    return TransactionSummary(
        signature="sig-1",
        slot=1,
        block_time=100,
        success=True,
        fee_lamports=5000,
        accounts=[],
        programs=programs or [],
        token_balance_deltas=deltas or [],
        raw_record_role=raw_record_role,
        raw_record_source=raw_record_source,
        raw_json={"meta": {"logMessages": logs or []}},
    )


def test_venue_classifier_returns_unknown_without_match_or_deltas() -> None:
    result = classify_venue(_summary())

    assert result.venue == "unknown"
    assert result.confidence == 0.0


def test_venue_classifier_returns_unknown_swap_candidate_for_token_deltas() -> None:
    delta = TokenBalanceDelta(
        owner="wallet-1",
        account="token-account-1",
        mint="mint-1",
        pre_amount=1.0,
        post_amount=2.0,
        delta=1.0,
        decimals=6,
    )

    result = classify_venue(_summary(deltas=[delta]))

    assert result.venue == "unknown_token_swap_candidate"
    assert result.confidence == 0.3
    assert result.reasons == ["token_balance_deltas_present_without_known_venue"]


def test_venue_classifier_uses_pumpfun_buy_program_and_log() -> None:
    result = classify_venue(
        _summary(
            programs=[ProgramInvocation(program_id=PUMPFUN_PROGRAM_ID)],
            raw_record_role="pumpfun_bonding_curve_lifecycle_2h",
            raw_record_source="helius_rpc",
            logs=["Program log: Instruction: Buy"],
        )
    )

    assert result.venue == "pumpfun_buy"
    assert result.confidence == 0.95
    assert result.reasons == ["matched_pumpfun_program_id_and_buy_instruction_log"]


def test_venue_classifier_uses_pumpfun_sell_program_and_log() -> None:
    result = classify_venue(
        _summary(
            programs=[ProgramInvocation(program_id=PUMPFUN_PROGRAM_ID)],
            raw_record_role="pumpfun_bonding_curve_lifecycle_2h",
            raw_record_source="helius_rpc",
            logs=["Program log: Instruction: SellV2"],
        )
    )

    assert result.venue == "pumpfun_sell"
    assert result.confidence == 0.95


def test_venue_classifier_uses_pumpfun_create_program_and_log() -> None:
    result = classify_venue(
        _summary(
            programs=[ProgramInvocation(program_id=PUMPFUN_PROGRAM_ID)],
            raw_record_role="pumpfun_bonding_curve_lifecycle_2h",
            raw_record_source="helius_rpc",
            logs=["Program log: Instruction: CreateV2"],
        )
    )

    assert result.venue == "pumpfun_create"
    assert result.confidence == 0.95


def test_venue_classifier_keeps_unknown_for_unknown_pumpfun_instruction() -> None:
    delta = TokenBalanceDelta(
        owner="wallet-1",
        account="token-account-1",
        mint="mint-1",
        pre_amount=1.0,
        post_amount=2.0,
        delta=1.0,
        decimals=6,
    )
    result = classify_venue(
        _summary(
            programs=[ProgramInvocation(program_id=PUMPFUN_PROGRAM_ID)],
            deltas=[delta],
            raw_record_role="pumpfun_bonding_curve_lifecycle_2h",
            logs=["Program log: Instruction: UnknownNewInstruction"],
        )
    )

    assert result.venue == "unknown_token_swap_candidate"
    assert result.reasons == ["pumpfun_program_seen_without_supported_instruction_log"]


def test_venue_classifier_does_not_invent_pumpfun_without_program_id() -> None:
    result = classify_venue(
        _summary(
            raw_record_role="pumpfun_bonding_curve_lifecycle_2h",
            logs=["Program log: Instruction: Buy"],
        )
    )

    assert result.venue != "pumpfun_buy"
