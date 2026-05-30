from research.mtp_research.ingestion.transaction_parser_models import (
    ProgramInvocation,
    TokenBalanceDelta,
    TransactionSummary,
)
from research.mtp_research.ingestion.venue_classifier import classify_venue


def _summary(
    programs: list[ProgramInvocation] | None = None,
    deltas: list[TokenBalanceDelta] | None = None,
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
