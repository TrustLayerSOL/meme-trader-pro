from research.mtp_research.validation.t007_protocol_codecs import (
    PUMP_BONDING_CURVE_ACCOUNT_LEN,
    PUMP_BONDING_CURVE_DISCRIMINATOR,
    PUMPSWAP_LEGACY_EXTENDED_ACCOUNT_LEN,
    PUMPSWAP_POOL_ACCOUNT_LEN,
    PUMPSWAP_POOL_DISCRIMINATOR,
    decode_pump_bonding_curve_account,
    decode_pumpswap_pool_account,
)


def test_pump_curve_decode_requires_verified_discriminator_and_owner():
    data = bytearray(PUMP_BONDING_CURVE_ACCOUNT_LEN)
    data[:8] = PUMP_BONDING_CURVE_DISCRIMINATOR
    result = decode_pump_bonding_curve_account(bytes(data), owner="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
    assert result.status == "decoded"
    assert result.layout_verified is True
    rejected = decode_pump_bonding_curve_account(bytes(data), owner="wrong")
    assert rejected.status == "rejected"
    assert rejected.reason == "wrong_owner"


def test_pumpswap_301_layout_is_not_verified_without_fixture_flag():
    data = bytearray(PUMPSWAP_LEGACY_EXTENDED_ACCOUNT_LEN)
    data[:8] = PUMPSWAP_POOL_DISCRIMINATOR
    result = decode_pumpswap_pool_account(bytes(data), owner="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
    assert result.status == "rejected"
    assert result.layout_verified is False
    pending = decode_pumpswap_pool_account(bytes(data), owner="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", allow_legacy_extended=True)
    assert pending.status == "pending_fixture"
    assert pending.layout_verified is False


def test_pumpswap_245_layout_decodes_as_verified_pool():
    data = bytearray(PUMPSWAP_POOL_ACCOUNT_LEN)
    data[:8] = PUMPSWAP_POOL_DISCRIMINATOR
    result = decode_pumpswap_pool_account(bytes(data), owner="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
    assert result.status == "decoded"
    assert result.layout_verified is True
