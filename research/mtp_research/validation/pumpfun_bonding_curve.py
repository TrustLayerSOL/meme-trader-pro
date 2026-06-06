"""Pump.fun bonding-curve constants, PDA helpers, and account-state math."""

from __future__ import annotations

from typing import Any
import hashlib

from research.mtp_research.validation.bonding_curve_account_state import (
    BondingCurveAccountStateProbe,
    BondingCurveState,
    FDVProbeResult,
    PDA_MARKER,
    bonding_curve_pda,
    bonding_curve_resolution_audit,
    compute_fdv_from_bonding_curve_state,
    decode_pump_bonding_curve_account,
    write_bonding_curve_first_fdv_probe_summary,
    _base58_decode,
    _base58_encode,
    _ed25519_compressed_point_on_curve,
)
from research.mtp_research.validation.forward_efficient_mover_observer import PUMP_FUN_PROGRAM_ID


PUMP_FUN_CREATE_DISCRIMINATOR_HEX = hashlib.sha256(b"global:create").digest()[:8].hex()
PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX = hashlib.sha256(b"global:create_v2").digest()[:8].hex()


def pumpfun_instruction_discriminator(instruction_name: str) -> str:
    normalized = str(instruction_name or "").strip()
    return hashlib.sha256(f"global:{normalized}".encode("utf-8")).digest()[:8].hex()


def is_pumpfun_create_discriminator(data: bytes | str | None) -> str | None:
    if isinstance(data, bytes):
        prefix = data[:8].hex()
    else:
        prefix = str(data or "")[:16].lower()
    if prefix == PUMP_FUN_CREATE_DISCRIMINATOR_HEX:
        return "create"
    if prefix == PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX:
        return "create_v2"
    return None


def mint_authority_pda(*, program_id: str = PUMP_FUN_PROGRAM_ID) -> str | None:
    return program_address_pda([b"mint-authority"], program_id=program_id)


def program_address_pda(seeds: list[bytes], *, program_id: str = PUMP_FUN_PROGRAM_ID) -> str | None:
    program_bytes = _base58_decode(str(program_id or ""))
    if program_bytes is None or len(program_bytes) != 32:
        return None
    for bump in range(255, -1, -1):
        candidate = hashlib.sha256(b"".join(seeds) + bytes([bump]) + program_bytes + PDA_MARKER).digest()
        if not _ed25519_compressed_point_on_curve(candidate):
            return _base58_encode(candidate)
    return None


__all__ = [
    "BondingCurveAccountStateProbe",
    "BondingCurveState",
    "FDVProbeResult",
    "PUMP_FUN_CREATE_DISCRIMINATOR_HEX",
    "PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX",
    "PUMP_FUN_PROGRAM_ID",
    "bonding_curve_pda",
    "bonding_curve_resolution_audit",
    "compute_fdv_from_bonding_curve_state",
    "decode_pump_bonding_curve_account",
    "is_pumpfun_create_discriminator",
    "mint_authority_pda",
    "program_address_pda",
    "pumpfun_instruction_discriminator",
    "write_bonding_curve_first_fdv_probe_summary",
]
