"""T007 production protocol codecs and account-resolution helpers.

This module is intentionally dependency-light and read-only. It contains the
fixed protocol constants/layouts used by the lifecycle recorder, readiness
checks, and offline tests. It does not import collector runtime state and never
performs RPC, trading, signing, or wallet operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import struct
from typing import Any, Mapping

PUMP_PUBLIC_DOCS_COMMIT = "1b822158844a60ca577df6ca122211b595a1a578"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

PUMP_BONDING_CURVE_ACCOUNT_LEN = 81
PUMPSWAP_POOL_ACCOUNT_LEN = 245
PUMPSWAP_LEGACY_EXTENDED_ACCOUNT_LEN = 301

# Anchor discriminators from the public Pump IDL at the pinned docs commit.
PUMP_BONDING_CURVE_DISCRIMINATOR = bytes([23, 183, 248, 55, 96, 216, 172, 96])
PUMPSWAP_POOL_DISCRIMINATOR = bytes([241, 154, 109, 4, 17, 177, 109, 188])

PUMP_CREATE_INSTRUCTION_NAMES = {"create", "createEvent", "Create", "CreateEvent"}
PUMP_TRADE_INSTRUCTION_NAMES = {"buy", "sell", "Buy", "Sell"}
PUMP_MIGRATION_INSTRUCTION_NAMES = {"migrate", "Migrate", "complete", "Complete"}

class ProtocolDecodeError(ValueError):
    """Raised when account bytes are not a verified supported protocol layout."""

@dataclass(frozen=True)
class DecodeResult:
    status: str
    layout: str
    layout_verified: bool
    fields: dict[str, Any]
    reason: str | None = None


def _pubkey(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_mint(value: Any) -> str | None:
    return _pubkey(value)


def quote_asset_from_mint(quote_mint: Any) -> str | None:
    mint = normalize_mint(quote_mint)
    if mint == SOL_MINT:
        return "SOL"
    if mint == USDC_MINT:
        return "USDC"
    return None


def decode_account_payload(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return base64.b64decode(value)
    if isinstance(value, (list, tuple)) and value:
        return decode_account_payload(value[0])
    raise ProtocolDecodeError(f"unsupported account payload type: {type(value).__name__}")


def _u64(data: bytes, offset: int) -> int:
    if offset + 8 > len(data):
        raise ProtocolDecodeError("account too short for u64 field")
    return struct.unpack_from("<Q", data, offset)[0]


def _bool(data: bytes, offset: int) -> bool:
    if offset + 1 > len(data):
        raise ProtocolDecodeError("account too short for bool field")
    return data[offset] != 0


def derive_bonding_curve_pda(mint: str) -> str:
    """Derive Pump.fun bonding-curve PDA from mint.

    Uses solders when available. The function is deterministic and read-only;
    callers must verify owner/layout on-chain before treating the PDA as usable.
    """
    try:
        from solders.pubkey import Pubkey  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("solders is required for PDA derivation") from exc
    address, _bump = Pubkey.find_program_address(
        [b"bonding-curve", bytes(Pubkey.from_string(mint))],
        Pubkey.from_string(PUMP_PROGRAM_ID),
    )
    return str(address)


def derive_associated_bonding_curve_token_account(bonding_curve: str, mint: str) -> str:
    """Derive associated bonding-curve token account for a curve PDA and mint."""
    try:
        from solders.pubkey import Pubkey  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("solders is required for ATA derivation") from exc
    owner = Pubkey.from_string(bonding_curve)
    mint_pk = Pubkey.from_string(mint)
    token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)
    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    address, _bump = Pubkey.find_program_address(
        [bytes(owner), bytes(token_program), bytes(mint_pk)],
        ata_program,
    )
    return str(address)


def decode_pump_bonding_curve_account(value: Any, *, owner: str | None = None) -> DecodeResult:
    data = decode_account_payload(value)
    if owner and owner != PUMP_PROGRAM_ID:
        return DecodeResult("rejected", "pump_bonding_curve_v1", False, {}, "wrong_owner")
    if len(data) < PUMP_BONDING_CURVE_ACCOUNT_LEN:
        return DecodeResult("rejected", "pump_bonding_curve_v1", False, {}, "short_account")
    if data[:8] != PUMP_BONDING_CURVE_DISCRIMINATOR:
        return DecodeResult("rejected", "pump_bonding_curve_v1", False, {}, "discriminator_mismatch")
    fields = {
        "virtual_token_reserves": _u64(data, 8),
        "virtual_sol_reserves": _u64(data, 16),
        "real_token_reserves": _u64(data, 24),
        "real_sol_reserves": _u64(data, 32),
        "token_total_supply": _u64(data, 40),
        "complete": _bool(data, 48),
    }
    return DecodeResult("decoded", "pump_bonding_curve_v1", True, fields)


def decode_pumpswap_pool_account(
    value: Any,
    *,
    owner: str | None = None,
    allow_legacy_extended: bool = False,
) -> DecodeResult:
    data = decode_account_payload(value)
    if owner and owner != PUMPSWAP_PROGRAM_ID:
        return DecodeResult("rejected", "pumpswap_pool_v1", False, {}, "wrong_owner")
    if len(data) == PUMPSWAP_LEGACY_EXTENDED_ACCOUNT_LEN and allow_legacy_extended:
        return DecodeResult(
            "pending_fixture",
            "legacy_observed_layout_pending_fixture",
            False,
            {"account_length": len(data)},
            "legacy_301_layout_requires_fixture",
        )
    if len(data) != PUMPSWAP_POOL_ACCOUNT_LEN:
        return DecodeResult("rejected", "pumpswap_pool_v1", False, {"account_length": len(data)}, "unsupported_account_length")
    if data[:8] != PUMPSWAP_POOL_DISCRIMINATOR:
        return DecodeResult("rejected", "pumpswap_pool_v1", False, {}, "discriminator_mismatch")
    fields = {
        "pool_bump": data[8],
        "index": struct.unpack_from("<H", data, 9)[0],
        "creator": data[11:43].hex(),
        "base_mint": data[43:75].hex(),
        "quote_mint": data[75:107].hex(),
        "lp_mint": data[107:139].hex(),
        "pool_base_token_account": data[139:171].hex(),
        "pool_quote_token_account": data[171:203].hex(),
        "account_length": len(data),
    }
    fields["quote_asset"] = quote_asset_from_mint(fields["quote_mint"])
    return DecodeResult("decoded", "pumpswap_pool_v1", True, fields)


def event_hash(payload: Mapping[str, Any]) -> str:
    pieces = [
        str(payload.get("collector_run_id") or payload.get("run_id") or ""),
        str(payload.get("event_type") or payload.get("canonical_event_type") or ""),
        str(payload.get("mint") or ""),
        str(payload.get("signature") or payload.get("source_signature") or ""),
        str(payload.get("feature_observed_at") or payload.get("source_received_at") or ""),
    ]
    return hashlib.sha256("|".join(pieces).encode("utf-8")).hexdigest()
