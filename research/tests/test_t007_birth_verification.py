from research.mtp_research.validation.t007_birth_verification import verify_birth_candidate


def test_strict_birth_requires_curve_and_associated_curve_identity():
    result = verify_birth_candidate({"mint": "Mint111", "creator": "Creator111", "signature": "sig1", "quote_asset": "SOL"})
    assert result.verified is False
    assert "missing_bonding_curve" in result.reasons
    assert "missing_associated_bonding_curve" in result.reasons


def test_strict_birth_rejects_pda_mismatch():
    result = verify_birth_candidate({
        "mint": "Mint111",
        "creator": "Creator111",
        "bonding_curve": "CurveA",
        "associated_bonding_curve": "AtaA",
        "expected_bonding_curve": "CurveB",
        "quote_asset": "SOL",
        "signature": "sig1",
    })
    assert result.verified is False
    assert "bonding_curve_pda_mismatch" in result.reasons
