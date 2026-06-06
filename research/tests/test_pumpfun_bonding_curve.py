from __future__ import annotations

from pathlib import Path

from research.mtp_research.validation.pumpfun_bonding_curve import (
    PUMP_FUN_CREATE_DISCRIMINATOR_HEX,
    PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX,
    PUMP_FUN_PROGRAM_ID,
    bonding_curve_pda,
    compute_fdv_from_bonding_curve_state,
    decode_pump_bonding_curve_account,
    is_pumpfun_create_discriminator,
    mint_authority_pda,
    pumpfun_instruction_discriminator,
)


def _classic_curve_bytes(
    *,
    virtual_token_reserves: int = 1_000_000_000,
    virtual_sol_reserves: int = 30_000_000_000,
    real_token_reserves: int = 900_000_000,
    real_sol_reserves: int = 10_000_000_000,
    token_total_supply: int = 1_000_000_000,
    complete: bool = False,
) -> bytes:
    return (
        b"pumpacct"
        + virtual_token_reserves.to_bytes(8, "little")
        + virtual_sol_reserves.to_bytes(8, "little")
        + real_token_reserves.to_bytes(8, "little")
        + real_sol_reserves.to_bytes(8, "little")
        + token_total_supply.to_bytes(8, "little")
        + bytes([int(complete)])
    )


def test_pumpfun_create_discriminators_match_anchor_hashes() -> None:
    assert PUMP_FUN_PROGRAM_ID == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    assert pumpfun_instruction_discriminator("create") == "181ec828051c0777"
    assert pumpfun_instruction_discriminator("create_v2") == "d6904cec5f8b31b4"
    assert PUMP_FUN_CREATE_DISCRIMINATOR_HEX == "181ec828051c0777"
    assert PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX == "d6904cec5f8b31b4"
    assert is_pumpfun_create_discriminator(bytes.fromhex("181ec828051c0777")) == "create"
    assert is_pumpfun_create_discriminator(bytes.fromhex("d6904cec5f8b31b4")) == "create_v2"
    assert is_pumpfun_create_discriminator(bytes.fromhex("0000000000000000")) is None


def test_pumpfun_pdas_are_deterministic() -> None:
    assert mint_authority_pda() == "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
    assert (
        bonding_curve_pda("2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump")
        == "3eafeBvZDXbqqNdNP4NDWdWn7kD6KSn22rtNHNeTAKVK"
    )
    assert bonding_curve_pda(None) is None


def test_bonding_curve_decoder_and_fdv_math_use_decimal_safe_reserves() -> None:
    state = decode_pump_bonding_curve_account(
        _classic_curve_bytes(
            virtual_token_reserves=1_234_567_890_123,
            virtual_sol_reserves=44_444_444_444,
            token_total_supply=1_000_000_000_000_000,
        )
    )

    result = compute_fdv_from_bonding_curve_state(state, sol_usd=150)

    assert state.decode_status == "decoded"
    assert result.probe_status == "success"
    assert result.calculation_status == "fdv_usd_available"
    assert result.token_decimals == 6
    assert result.quote_decimals == 9
    assert result.fdv_source == "bonding_curve_account_state"
    assert result.fdv_source_confidence == "high"
    assert result.fdv_sol is not None
    assert result.fdv_usd is not None


def test_no_new_paid_provider_dependency_in_bonding_curve_module() -> None:
    text = Path("research/mtp_research/validation/pumpfun_bonding_curve.py").read_text(encoding="utf-8").lower()
    for forbidden in ["laserstream", "yellowstone", "geyser", "pumpportal", "birdeye", "bitquery", "jupiter"]:
        assert forbidden not in text
