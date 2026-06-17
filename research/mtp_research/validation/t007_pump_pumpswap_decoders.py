from __future__ import annotations

import base64
import binascii
import struct
import time
from typing import Any

from research.mtp_research.validation.t007_protocol_idl_registry import (
    PUMP_FUN_PROGRAM_ID,
    PUMPSWAP_PROGRAM_ID,
    load_protocol_idl_registry,
)


SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode_pubkey(raw: bytes) -> str:
    value = int.from_bytes(raw, "big")
    encoded = ""
    while value:
        value, rem = divmod(value, 58)
        encoded = _B58_ALPHABET[rem] + encoded
    leading = 0
    for byte in raw:
        if byte == 0:
            leading += 1
        else:
            break
    return ("1" * leading) + (encoded or "1")


def decode_protocol_instruction_event(
    *,
    program_id: str,
    instruction: dict[str, Any],
    signature: str,
    slot: int | None,
    instruction_index: int | None = None,
    parent_instruction_index: int | None = None,
    event_index: int | None = None,
    observed_at: float | None = None,
) -> dict[str, Any] | None:
    registry = load_protocol_idl_registry()
    program = _program_for_id(program_id)
    if program is None:
        return None
    data = _instruction_data(instruction.get("data"))
    if len(data) < 8:
        return None
    try:
        meta = registry.classify_instruction(program, data[:8])
    except KeyError:
        return None
    accounts = _account_map(meta.account_names, instruction.get("accounts") or [])
    observed = float(observed_at if observed_at is not None else time.time())
    common = {
        "signature": signature,
        "slot": slot,
        "instruction_index": instruction_index,
        "parent_instruction_index": parent_instruction_index,
        "event_index": event_index,
        "program_id": program_id,
        "instruction_name": meta.name,
        "instruction_discriminator": data[:8].hex(),
        "observed_at": observed,
        "raw_instruction_account_count": len(instruction.get("accounts") or []),
    }
    if program == "pump_amm" and meta.name == "create_pool":
        return _level_a_migration_row(
            common,
            accounts,
            source_lane="pumpswap_create_pool_lane",
            detection_method="pumpswap_create_pool_instruction",
            mint_key="base_mint",
        )
    if program == "pump" and meta.name in {"migrate", "migrate_v2"}:
        mint_key = "base_mint" if meta.name == "migrate_v2" else "mint"
        return _level_a_migration_row(
            common,
            accounts,
            source_lane="pumpfun_migration_lane",
            detection_method=f"pumpfun_{meta.name}_instruction",
            mint_key=mint_key,
        )
    if program == "pump_amm" and meta.name in {"buy", "buy_exact_quote_in", "sell", "deposit", "withdraw"}:
        row = dict(common)
        row.update(
            {
                "event_family": "post_migration_swap_context" if meta.name in {"buy", "buy_exact_quote_in", "sell"} else "post_migration_pool_context",
                "source_lane": "pumpswap_swap_lane",
                "migration_evidence_level": "NONE",
                "migration_confirmed": False,
                "trade_data_eligible": False,
                "pool_or_pair_address": accounts.get("pool"),
                "mint": accounts.get("base_mint"),
            }
        )
        return row
    return None


def decode_pool_account_snapshot(
    pool_pubkey: str,
    account_data: bytes,
    *,
    slot: int | None = None,
    observed_at: float | None = None,
) -> dict[str, Any]:
    registry = load_protocol_idl_registry()
    observed = float(observed_at if observed_at is not None else time.time())
    pool_meta = registry.account_by_name("pump_amm", "Pool")
    if len(account_data) < 8 or account_data[:8] != pool_meta.discriminator:
        return {
            "pool_or_pair_address": pool_pubkey,
            "slot": slot,
            "observed_at": observed,
            "pool_account_decode_status": "not_pumpswap_pool",
        }
    offset = 8
    pool_bump = account_data[offset]
    offset += 1
    index = struct.unpack_from("<H", account_data, offset)[0]
    offset += 2
    creator = account_data[offset : offset + 32]
    offset += 32
    base_mint = account_data[offset : offset + 32]
    offset += 32
    quote_mint = account_data[offset : offset + 32]
    offset += 32
    lp_mint = account_data[offset : offset + 32]
    offset += 32
    base_vault = account_data[offset : offset + 32]
    offset += 32
    quote_vault = account_data[offset : offset + 32]
    offset += 32
    lp_supply = struct.unpack_from("<Q", account_data, offset)[0]
    offset += 8
    coin_creator = account_data[offset : offset + 32]
    offset += 32
    is_mayhem = bool(account_data[offset]) if offset < len(account_data) else False
    offset += 1
    is_cashback = bool(account_data[offset]) if offset < len(account_data) else False
    quote_mint_str = b58encode_pubkey(quote_mint)
    return {
        "pool_or_pair_address": pool_pubkey,
        "slot": slot,
        "observed_at": observed,
        "pool_account_decode_status": "decoded",
        "pool_decode_route": "official_pump_amm_idl_pool_account_v2",
        "pool_bump": pool_bump,
        "pool_index": index,
        "creator": b58encode_pubkey(creator),
        "base_mint": b58encode_pubkey(base_mint),
        "quote_mint": quote_mint_str,
        "quote_asset": _quote_asset(quote_mint_str),
        "lp_mint": b58encode_pubkey(lp_mint),
        "pool_base_token_account": b58encode_pubkey(base_vault),
        "pool_quote_token_account": b58encode_pubkey(quote_vault),
        "lp_supply": lp_supply,
        "coin_creator": b58encode_pubkey(coin_creator),
        "is_mayhem_mode": is_mayhem,
        "is_cashback_coin": is_cashback,
    }


def _level_a_migration_row(
    common: dict[str, Any],
    accounts: dict[str, str],
    *,
    source_lane: str,
    detection_method: str,
    mint_key: str,
) -> dict[str, Any]:
    mint = accounts.get(mint_key) or accounts.get("base_mint") or accounts.get("mint")
    quote_mint = accounts.get("quote_mint") or (SOL_MINT if detection_method == "pumpfun_migrate_instruction" else None)
    row = dict(common)
    row.update(
        {
            "event_family": "migration",
            "source_lane": source_lane,
            "source_route": source_lane,
            "lifecycle_state": "MIGRATION_CONFIRMED_LEVEL_A",
            "migration_evidence_level": "LEVEL_A",
            "migration_confirmed": True,
            "confidence": "confirmed",
            "detection_method": detection_method,
            "mint": mint,
            "base_mint": accounts.get("base_mint") or accounts.get("mint") or mint,
            "quote_mint": quote_mint,
            "quote_asset": _quote_asset(quote_mint),
            "pool_or_pair_address": accounts.get("pool"),
            "pool_address": accounts.get("pool"),
            "pool_base_token_account": accounts.get("pool_base_token_account"),
            "pool_quote_token_account": accounts.get("pool_quote_token_account"),
            "creator": accounts.get("creator") or accounts.get("user"),
            "trade_data_eligible": False,
        }
    )
    return row


def _program_for_id(program_id: str) -> str | None:
    if program_id == PUMP_FUN_PROGRAM_ID:
        return "pump"
    if program_id == PUMPSWAP_PROGRAM_ID:
        return "pump_amm"
    return None


def _account_map(account_names: tuple[str, ...], accounts: list[Any]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for index, name in enumerate(account_names):
        if index >= len(accounts):
            continue
        value = accounts[index]
        if isinstance(value, dict):
            value = value.get("pubkey") or value.get("account") or value.get("address")
        if value not in (None, ""):
            mapped[str(name)] = str(value)
    return mapped


def _instruction_data(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        return b""
    raw = value.strip()
    if not raw:
        return b""
    try:
        return base64.b64decode(raw, validate=True)
    except binascii.Error:
        pass
    try:
        return bytes.fromhex(raw)
    except ValueError:
        return _b58decode(raw)


def _b58decode(raw: str) -> bytes:
    value = 0
    for char in raw:
        value *= 58
        if char not in _B58_ALPHABET:
            return b""
        value += _B58_ALPHABET.index(char)
    output = value.to_bytes((value.bit_length() + 7) // 8, "big") if value else b""
    leading = len(raw) - len(raw.lstrip("1"))
    return (b"\x00" * leading) + output


def _quote_asset(quote_mint: str | None) -> str:
    if quote_mint == SOL_MINT:
        return "SOL"
    if quote_mint == USDC_MINT:
        return "USDC"
    return "UNKNOWN"

