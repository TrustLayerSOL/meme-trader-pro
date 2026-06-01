from research.mtp_research.ingestion.pumpfun_create_fixture_review import review_known_create_transaction
from research.tests.test_pumpfun_create_scanner import _create_tx


def test_known_create_fixture_review_accepts_matching_verified_layout() -> None:
    result = review_known_create_transaction(
        _create_tx("sig-1"),
        expected_mint="mint-sig-1",
        expected_creator="creator-sig-1",
        expected_bonding_curve="bonding-sig-1",
    )

    assert result["accepted"] is True
    assert result["parser_confidence"] == "medium"
    assert result["rejection_reason"] is None


def test_known_create_fixture_review_fails_closed_on_mismatch() -> None:
    result = review_known_create_transaction(
        _create_tx("sig-1"),
        expected_mint="wrong-mint",
        expected_creator="creator-sig-1",
        expected_bonding_curve="bonding-sig-1",
    )

    assert result["accepted"] is False
    assert "mint_mismatch" in result["rejection_reason"]


def test_known_create_fixture_review_fails_closed_on_unknown_discriminator() -> None:
    tx = _create_tx("sig-1")
    tx["transaction"]["message"]["instructions"][0]["data"] = "unknownDiscriminatorPayload"

    result = review_known_create_transaction(
        tx,
        expected_mint="mint-sig-1",
        expected_creator="creator-sig-1",
        expected_bonding_curve="bonding-sig-1",
    )

    assert result["accepted"] is False
    assert result["rejection_reason"] == "no_verified_create_candidate"
