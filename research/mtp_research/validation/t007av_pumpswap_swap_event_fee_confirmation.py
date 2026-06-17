"""T007AV PumpSwap swap event decoding and fee confirmation.

Read-only validation utilities for PumpSwap Anchor BuyEvent/SellEvent logs. This
module does not trade, build transactions, sign, simulate, or touch wallet paths.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import struct
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
OUTPUT_DIR = Path("/Users/dianeposs/Projects/meme-trader-pro/outputs/theses/t007av_pumpswap_swap_event_fee_confirmation")
SDK_PACKAGE = "@pump-fun/pump-swap-sdk"
SDK_VERSION = "1.17.0"
SDK_IDL_PATH = "src/idl/pump_amm.json"

BUY_INSTRUCTION_DISCRIMINATOR_BYTES = hashlib.sha256(b"global:buy").digest()[:8]
SELL_INSTRUCTION_DISCRIMINATOR_BYTES = hashlib.sha256(b"global:sell").digest()[:8]
BUY_EVENT_DISCRIMINATOR_BYTES = hashlib.sha256(b"event:BuyEvent").digest()[:8]
SELL_EVENT_DISCRIMINATOR_BYTES = hashlib.sha256(b"event:SellEvent").digest()[:8]
POOL_ACCOUNT_DISCRIMINATOR = [241, 154, 109, 4, 17, 177, 109, 188]
GLOBAL_CONFIG_ACCOUNT_DISCRIMINATOR = [149, 8, 156, 202, 160, 252, 176, 217]

T007AV_GUARDRAILS = {
    "read_only": True,
    "no_live_scan_by_default": True,
    "valuation_ladder_suppressed": True,
    "mayhem_files_modified": False,
    "wallet_private_key_trading_signing_execution_untouched": True,
    "simulate_transaction_allowed": False,
    "send_transaction_allowed": False,
    "paper_trading_allowed": False,
}

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

BUY_EVENT_FIELDS = [
    ("timestamp", "i64"),
    ("base_amount_out", "u64"),
    ("max_quote_amount_in", "u64"),
    ("user_base_token_reserves", "u64"),
    ("user_quote_token_reserves", "u64"),
    ("pool_base_token_reserves", "u64"),
    ("pool_quote_token_reserves", "u64"),
    ("quote_amount_in", "u64"),
    ("lp_fee_basis_points", "u64"),
    ("lp_fee", "u64"),
    ("protocol_fee_basis_points", "u64"),
    ("protocol_fee", "u64"),
    ("quote_amount_in_with_lp_fee", "u64"),
    ("user_quote_amount_in", "u64"),
    ("pool", "pubkey"),
    ("user", "pubkey"),
    ("user_base_token_account", "pubkey"),
    ("user_quote_token_account", "pubkey"),
    ("protocol_fee_recipient", "pubkey"),
    ("protocol_fee_recipient_token_account", "pubkey"),
    ("coin_creator", "pubkey"),
    ("coin_creator_fee_basis_points", "u64"),
    ("coin_creator_fee", "u64"),
    ("track_volume", "bool"),
    ("total_unclaimed_tokens", "u64"),
    ("total_claimed_tokens", "u64"),
    ("current_sol_volume", "u64"),
    ("last_update_timestamp", "i64"),
    ("min_base_amount_out", "u64"),
    ("ix_name", "string"),
    ("cashback_fee_basis_points", "u64"),
    ("cashback", "u64"),
    ("buyback_fee_basis_points", "u64"),
    ("buyback_fee", "u64"),
]

SELL_EVENT_FIELDS = [
    ("timestamp", "i64"),
    ("base_amount_in", "u64"),
    ("min_quote_amount_out", "u64"),
    ("user_base_token_reserves", "u64"),
    ("user_quote_token_reserves", "u64"),
    ("pool_base_token_reserves", "u64"),
    ("pool_quote_token_reserves", "u64"),
    ("quote_amount_out", "u64"),
    ("lp_fee_basis_points", "u64"),
    ("lp_fee", "u64"),
    ("protocol_fee_basis_points", "u64"),
    ("protocol_fee", "u64"),
    ("quote_amount_out_without_lp_fee", "u64"),
    ("user_quote_amount_out", "u64"),
    ("pool", "pubkey"),
    ("user", "pubkey"),
    ("user_base_token_account", "pubkey"),
    ("user_quote_token_account", "pubkey"),
    ("protocol_fee_recipient", "pubkey"),
    ("protocol_fee_recipient_token_account", "pubkey"),
    ("coin_creator", "pubkey"),
    ("coin_creator_fee_basis_points", "u64"),
    ("coin_creator_fee", "u64"),
    ("cashback_fee_basis_points", "u64"),
    ("cashback", "u64"),
    ("buyback_fee_basis_points", "u64"),
    ("buyback_fee", "u64"),
]

SWAP_EVENT_JSONL_FIELDS = [
    "campaign_id",
    "run_id",
    "signature",
    "slot",
    "received_at",
    "block_time",
    "event_type",
    "mint",
    "pool",
    "user",
    "quote_asset",
    "quote_mint",
    "base_mint",
    "pool_base_token_account",
    "pool_quote_token_account",
    "base_amount",
    "quote_amount",
    "user_quote_amount",
    "lp_fee_basis_points",
    "lp_fee",
    "protocol_fee_basis_points",
    "protocol_fee",
    "total_fee_basis_points_observed",
    "pool_base_token_reserves",
    "pool_quote_token_reserves",
    "event_decode_status",
    "event_decode_route",
    "event_decode_confidence",
    "decision_time_safe",
    "valuation_ladder_used",
]


def base58_encode_bytes(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = BASE58_ALPHABET[rem] + encoded
    leading_zeroes = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading_zeroes + (encoded or "")


def base58_decode_string(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + BASE58_ALPHABET.index(char)
    payload = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return (b"\x00" * leading_zeroes + payload).rjust(32, b"\x00")[-32:]


def _read_scalar(data: bytes, offset: int, kind: str) -> tuple[Any, int]:
    if kind == "u64":
        return struct.unpack_from("<Q", data, offset)[0], offset + 8
    if kind == "i64":
        return struct.unpack_from("<q", data, offset)[0], offset + 8
    if kind == "bool":
        return bool(data[offset]), offset + 1
    if kind == "pubkey":
        return base58_encode_bytes(data[offset : offset + 32]), offset + 32
    if kind == "string":
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        raw = data[offset : offset + length]
        return raw.decode("utf-8", errors="replace"), offset + length
    raise ValueError(f"Unsupported PumpSwap IDL scalar kind: {kind}")


def _decode_event_payload(data: bytes) -> dict[str, Any] | None:
    if len(data) < 8:
        return None
    discriminator = data[:8]
    if discriminator == BUY_EVENT_DISCRIMINATOR_BYTES:
        event_type = "buy"
        fields = BUY_EVENT_FIELDS
    elif discriminator == SELL_EVENT_DISCRIMINATOR_BYTES:
        event_type = "sell"
        fields = SELL_EVENT_FIELDS
    else:
        return None
    offset = 8
    decoded: dict[str, Any] = {"event_type": event_type}
    try:
        for name, kind in fields:
            decoded[name], offset = _read_scalar(data, offset, kind)
    except (struct.error, IndexError, ValueError):
        return None
    decoded["event_decode_status"] = "decoded"
    decoded["event_decode_route"] = "anchor_program_data_event"
    decoded["event_decode_confidence"] = "idl_event_discriminator"
    decoded["decision_time_safe"] = True
    decoded["valuation_ladder_used"] = False
    return decoded


def _event_bytes_from_log_line(line: str) -> bytes | None:
    text = str(line).strip()
    prefixes = ("Program data: ", "Program log: ")
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    else:
        return None
    try:
        return base64.b64decode(text, validate=True)
    except Exception:
        return None


def _quote_asset_from_mint(quote_mint: str | None) -> str:
    if quote_mint == SOL_MINT:
        return "SOL"
    if quote_mint == USDC_MINT:
        return "USDC"
    return "UNKNOWN"


def _normalise_swap_event(decoded: Mapping[str, Any], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    event_type = str(decoded.get("event_type") or "")
    if event_type == "buy":
        base_amount = decoded.get("base_amount_out")
        quote_amount = decoded.get("quote_amount_in")
        user_quote_amount = decoded.get("user_quote_amount_in")
    else:
        base_amount = decoded.get("base_amount_in")
        quote_amount = decoded.get("quote_amount_out")
        user_quote_amount = decoded.get("user_quote_amount_out")
    lp_bps = decoded.get("lp_fee_basis_points") or 0
    protocol_bps = decoded.get("protocol_fee_basis_points") or 0
    coin_creator_bps = decoded.get("coin_creator_fee_basis_points") or 0
    cashback_bps = decoded.get("cashback_fee_basis_points") or 0
    buyback_bps = decoded.get("buyback_fee_basis_points") or 0
    row = {
        "campaign_id": context.get("campaign_id", ""),
        "run_id": context.get("run_id", ""),
        "signature": context.get("signature", ""),
        "slot": context.get("slot", ""),
        "received_at": context.get("received_at", ""),
        "block_time": context.get("block_time", decoded.get("timestamp", "")),
        "event_type": event_type,
        "mint": context.get("mint", context.get("base_mint", "")),
        "pool": decoded.get("pool", context.get("pool", "")),
        "user": decoded.get("user", ""),
        "quote_asset": _quote_asset_from_mint(context.get("quote_mint")),
        "quote_mint": context.get("quote_mint", ""),
        "base_mint": context.get("base_mint", context.get("mint", "")),
        "pool_base_token_account": context.get("pool_base_token_account", ""),
        "pool_quote_token_account": context.get("pool_quote_token_account", ""),
        "base_amount": base_amount,
        "quote_amount": quote_amount,
        "user_quote_amount": user_quote_amount,
        "lp_fee_basis_points": lp_bps,
        "lp_fee": decoded.get("lp_fee", 0),
        "protocol_fee_basis_points": protocol_bps,
        "protocol_fee": decoded.get("protocol_fee", 0),
        "coin_creator_fee_basis_points": coin_creator_bps,
        "coin_creator_fee": decoded.get("coin_creator_fee", 0),
        "cashback_fee_basis_points": cashback_bps,
        "cashback": decoded.get("cashback", 0),
        "buyback_fee_basis_points": buyback_bps,
        "buyback_fee": decoded.get("buyback_fee", 0),
        "total_fee_basis_points_observed": lp_bps + protocol_bps + coin_creator_bps + cashback_bps + buyback_bps,
        "pool_base_token_reserves": decoded.get("pool_base_token_reserves"),
        "pool_quote_token_reserves": decoded.get("pool_quote_token_reserves"),
        "event_decode_status": decoded.get("event_decode_status", "decoded"),
        "event_decode_route": decoded.get("event_decode_route", "anchor_program_data_event"),
        "event_decode_confidence": decoded.get("event_decode_confidence", "idl_event_discriminator"),
        "decision_time_safe": True,
        "valuation_ladder_used": False,
    }
    for key in ("user_base_token_account", "user_quote_token_account", "protocol_fee_recipient", "protocol_fee_recipient_token_account"):
        row[key] = decoded.get(key, "")
    return row


def decode_pumpswap_swap_events_from_logs(
    logs: Iterable[str], context: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in logs or []:
        payload = _event_bytes_from_log_line(str(line))
        if payload is None:
            continue
        decoded = _decode_event_payload(payload)
        if decoded:
            rows.append(_normalise_swap_event(decoded, context))
    return rows


def classify_pumpswap_instruction_discriminator(data: bytes | str | None) -> str | None:
    if data is None:
        return None
    if isinstance(data, str):
        try:
            data = base64.b64decode(data)
        except Exception:
            data = data.encode("utf-8", errors="ignore")
    if bytes(data[:8]) == BUY_INSTRUCTION_DISCRIMINATOR_BYTES:
        return "buy"
    if bytes(data[:8]) == SELL_INSTRUCTION_DISCRIMINATOR_BYTES:
        return "sell"
    return None


def enrich_swap_event_with_pool_metadata(row: Mapping[str, Any], pool_metadata: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    output["base_mint"] = output.get("base_mint") or pool_metadata.get("base_mint") or pool_metadata.get("mint") or ""
    output["mint"] = output.get("mint") or output.get("base_mint")
    output["quote_mint"] = output.get("quote_mint") or pool_metadata.get("quote_mint") or ""
    output["quote_asset"] = output.get("quote_asset") if output.get("quote_asset") not in (None, "", "UNKNOWN") else _quote_asset_from_mint(output.get("quote_mint"))
    output["pool"] = output.get("pool") or pool_metadata.get("pool_or_pair_address") or pool_metadata.get("pool") or ""
    output["pool_base_token_account"] = output.get("pool_base_token_account") or pool_metadata.get("pool_base_token_account") or ""
    output["pool_quote_token_account"] = output.get("pool_quote_token_account") or pool_metadata.get("pool_quote_token_account") or ""
    output["valuation_ladder_used"] = False
    output["decision_time_safe"] = True
    return output


def build_pumpswap_swap_candidate_inventory(
    decoded_swap_events: Iterable[Mapping[str, Any]],
    pool_metadata_rows: Iterable[Mapping[str, Any]] | None = None,
    pumpfun_trade_rows: Iterable[Mapping[str, Any]] | None = None,
    route_audit_rows: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    del pumpfun_trade_rows  # Explicitly excluded from T007AV candidate sourcing.
    pools_by_pool = {}
    for pool in pool_metadata_rows or []:
        key = pool.get("pool") or pool.get("pool_or_pair_address")
        if key:
            pools_by_pool[str(key)] = pool
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for event in decoded_swap_events:
        if event.get("event_type") not in {"buy", "sell"}:
            continue
        pool = str(event.get("pool") or "")
        enriched = enrich_swap_event_with_pool_metadata(event, pools_by_pool.get(pool, {}))
        key = (str(enriched.get("signature") or ""), pool)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "candidate_source": "decoded_pumpswap_swap_event",
                "signature": enriched.get("signature", ""),
                "slot": enriched.get("slot", ""),
                "event_type": enriched.get("event_type", ""),
                "pool": enriched.get("pool", ""),
                "mint": enriched.get("mint", ""),
                "quote_asset": enriched.get("quote_asset", ""),
                "base_mint": enriched.get("base_mint", ""),
                "quote_mint": enriched.get("quote_mint", ""),
                "pool_base_token_account": enriched.get("pool_base_token_account", ""),
                "pool_quote_token_account": enriched.get("pool_quote_token_account", ""),
                "include_for_replay": True,
                "exclusion_reason": "",
            }
        )
    for audit in route_audit_rows or []:
        if not audit.get("includes_pumpswap_program"):
            continue
        signature = str(audit.get("signature") or "")
        if not signature:
            continue
        key = (signature, str(audit.get("pool") or audit.get("pool_or_pair_address") or ""))
        if key in seen:
            continue
        seen.add(key)
        event_type = "buy" if audit.get("contains_buy_discriminator") or audit.get("contains_buy_event_log") else "sell" if audit.get("contains_sell_discriminator") or audit.get("contains_sell_event_log") else ""
        rows.append(
            {
                "candidate_source": "pumpswap_transaction_route_audit",
                "signature": signature,
                "slot": audit.get("slot", ""),
                "event_type": event_type,
                "pool": audit.get("pool") or audit.get("pool_or_pair_address") or "",
                "mint": audit.get("mint", ""),
                "quote_asset": audit.get("quote_asset", ""),
                "base_mint": audit.get("base_mint", ""),
                "quote_mint": audit.get("quote_mint", ""),
                "pool_base_token_account": audit.get("pool_base_token_account", ""),
                "pool_quote_token_account": audit.get("pool_quote_token_account", ""),
                "include_for_replay": False,
                "exclusion_reason": "route_audit_only_missing_decoded_swap_amounts",
            }
        )
    return rows


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _additional_fee_total(event: Mapping[str, Any]) -> float:
    return sum(
        _num(event.get(key)) or 0.0
        for key in ("lp_fee", "protocol_fee", "coin_creator_fee", "cashback", "buyback_fee")
    )


def _user_quote_endpoint_fee_total(event: Mapping[str, Any]) -> float:
    return sum(
        _num(event.get(key)) or 0.0
        for key in ("lp_fee", "protocol_fee", "coin_creator_fee", "cashback")
    )


def _signed_user_quote_endpoint_fee_total(event: Mapping[str, Any], quote_amount: float, user_quote_amount: float) -> float:
    fee_total = _user_quote_endpoint_fee_total(event)
    if user_quote_amount < quote_amount:
        return -fee_total
    if user_quote_amount > quote_amount:
        return fee_total
    return 0.0


def build_fee_formula_replay_validation_row(event: Mapping[str, Any], *, tolerance_pct: float = 0.1) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    quote_amount = _num(event.get("quote_amount"))
    user_quote_amount = _num(event.get("user_quote_amount"))
    failure_reason = ""
    if event_type not in {"buy", "sell"}:
        failure_reason = "not_pumpswap_buy_sell_event"
    elif quote_amount is None:
        failure_reason = "missing_quote_amount"
    elif user_quote_amount is None:
        failure_reason = "missing_user_quote_amount"
    if failure_reason:
        predicted = None
        absolute_error = None
        relative_error_pct = None
        status = "fail"
    else:
        predicted = quote_amount + _signed_user_quote_endpoint_fee_total(event, quote_amount, user_quote_amount)
        absolute_error = abs(float(predicted) - float(user_quote_amount))
        relative_error_pct = 0.0 if user_quote_amount == 0 else (absolute_error / abs(float(user_quote_amount))) * 100.0
        status = "pass" if relative_error_pct <= tolerance_pct else "fail"
        if status == "fail":
            failure_reason = "event_fee_math_mismatch"
    return {
        "signature": event.get("signature", ""),
        "event_type": event_type,
        "pool": event.get("pool", ""),
        "mint": event.get("mint", ""),
        "quote_asset": event.get("quote_asset", ""),
        "base_amount_in_or_out": event.get("base_amount", ""),
        "quote_amount_in_or_out": event.get("quote_amount", ""),
        "user_quote_amount": event.get("user_quote_amount", ""),
        "lp_fee_basis_points": event.get("lp_fee_basis_points", ""),
        "protocol_fee_basis_points": event.get("protocol_fee_basis_points", ""),
        "lp_fee": event.get("lp_fee", ""),
        "protocol_fee": event.get("protocol_fee", ""),
        "predicted_quote_no_fee": quote_amount if quote_amount is not None else "",
        "predicted_quote_with_event_fees": predicted if predicted is not None else "",
        "absolute_error": absolute_error if absolute_error is not None else "",
        "relative_error_pct": relative_error_pct if relative_error_pct is not None else "",
        "validation_status": status,
        "failure_reason": failure_reason,
    }


def classify_fee_model_status(replay_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(replay_rows)
    tested = [row for row in rows if row.get("validation_status") in {"pass", "fail"}]
    passed = [row for row in tested if row.get("validation_status") == "pass" and (_num(row.get("relative_error_pct")) or 0.0) <= 0.1]
    if tested and len(passed) == len(tested):
        fee_model_status = "confirmed"
        quote_confidence = "high"
    elif rows:
        fee_model_status = "unknown"
        quote_confidence = "low"
    else:
        fee_model_status = "unknown"
        quote_confidence = "low"
    return {
        "fee_model_status": fee_model_status,
        "quote_confidence": quote_confidence,
        "replay_validation_rows": len(rows),
        "replay_rows_tested": len(tested),
        "replay_rows_passed": len(passed),
        "valuation_ladder_suppressed": True,
        "partial_60m_allowed": fee_model_status in {"confirmed", "assumed"},
        "full_60m_blocked": fee_model_status != "confirmed",
        "two_hour_plus_blocked": True,
    }


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _logs_from_row(row: Mapping[str, Any]) -> list[str]:
    logs = row.get("logs") or row.get("log_messages") or row.get("logs_excerpt")
    if isinstance(logs, str):
        try:
            loaded = json.loads(logs)
            if isinstance(loaded, list):
                return [str(item) for item in loaded]
        except json.JSONDecodeError:
            return [logs]
    if isinstance(logs, list):
        return [str(item) for item in logs]
    raw = row.get("raw_payload")
    if isinstance(raw, dict):
        return _logs_from_row(raw)
    return []


def _pool_rows_from_root(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("global_migration_events.jsonl", "pumpswap_route_candidates.jsonl", "post_migration_observations.jsonl"):
        rows.extend(_read_jsonl(root / name))
    return rows


def _decoded_swap_event_from_jsonl_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if row.get("event_type") not in {"buy", "sell"}:
        return None
    output = dict(row)
    output["pool"] = output.get("pool") or output.get("pool_or_pair_address") or ""
    output["mint"] = output.get("mint") or output.get("base_mint") or ""
    output["base_mint"] = output.get("base_mint") or output.get("mint") or ""
    output["quote_asset"] = output.get("quote_asset") or _quote_asset_from_mint(output.get("quote_mint"))
    output["event_decode_status"] = output.get("event_decode_status") or "available"
    if not output.get("decode_source"):
        output["decode_source"] = "anchor_event_log" if output.get("event_decode_status") in {"decoded", "available"} else "unknown"
    output["decision_time_safe"] = True
    output["valuation_ladder_used"] = False
    return output


def _swap_event_dedupe_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("signature") or ""),
        str(row.get("event_type") or ""),
        str(row.get("pool") or row.get("pool_or_pair_address") or ""),
        str(row.get("mint") or row.get("base_mint") or ""),
        str(row.get("base_amount") or ""),
        str(row.get("quote_amount") or ""),
        str(row.get("user_quote_amount") or ""),
    )


def _append_unique_swap_event(events: list[dict[str, Any]], seen: set[tuple[str, str, str, str, str, str, str]], row: Mapping[str, Any]) -> None:
    key = _swap_event_dedupe_key(row)
    if key in seen:
        return
    seen.add(key)
    events.append(dict(row))


def decode_swap_events_from_root(root: Path) -> list[dict[str, Any]]:
    pools = _pool_rows_from_root(root)
    pools_by_pool = {
        str(row.get("pool") or row.get("pool_or_pair_address") or ""): row
        for row in pools
        if row.get("pool") or row.get("pool_or_pair_address")
    }
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str, str, str]] = set()
    for source_row in _read_jsonl(root / "pumpswap_swap_events.jsonl"):
        decoded = _decoded_swap_event_from_jsonl_row(source_row)
        if decoded is None:
            continue
        pool_meta = pools_by_pool.get(str(decoded.get("pool") or ""), {})
        _append_unique_swap_event(events, seen, enrich_swap_event_with_pool_metadata(decoded, pool_meta))
    for name in ("global_migration_candidates.jsonl", "global_migration_events.jsonl", "raw_birth_source_audit.jsonl"):
        for source_row in _read_jsonl(root / name):
            context = {
                "campaign_id": source_row.get("campaign_id", ""),
                "run_id": source_row.get("run_id", ""),
                "signature": source_row.get("signature", ""),
                "slot": source_row.get("slot", ""),
                "received_at": source_row.get("received_at", ""),
                "block_time": source_row.get("block_time", ""),
                "mint": source_row.get("mint") or source_row.get("base_mint") or "",
                "base_mint": source_row.get("base_mint") or source_row.get("mint") or "",
                "quote_mint": source_row.get("quote_mint", ""),
            }
            for event in decode_pumpswap_swap_events_from_logs(_logs_from_row(source_row), context):
                pool_meta = pools_by_pool.get(str(event.get("pool") or ""), {})
                _append_unique_swap_event(events, seen, enrich_swap_event_with_pool_metadata(event, pool_meta))
    return events

def write_idl_source_inventory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# T007AV PumpSwap IDL Source Inventory",
                "",
                f"- source path: `{SDK_PACKAGE}@{SDK_VERSION}/{SDK_IDL_PATH}`",
                "- upstream package: npm `@pump-fun/pump-swap-sdk`",
                f"- upstream package version: `{SDK_VERSION}`",
                f"- PumpSwap program id: `{PUMPSWAP_PROGRAM_ID}`",
                f"- buy discriminator: `{list(BUY_INSTRUCTION_DISCRIMINATOR_BYTES)}`",
                f"- sell discriminator: `{list(SELL_INSTRUCTION_DISCRIMINATOR_BYTES)}`",
                f"- BuyEvent discriminator: `{list(BUY_EVENT_DISCRIMINATOR_BYTES)}`",
                f"- SellEvent discriminator: `{list(SELL_EVENT_DISCRIMINATOR_BYTES)}`",
                f"- Pool discriminator: `{POOL_ACCOUNT_DISCRIMINATOR}`",
                f"- GlobalConfig discriminator: `{GLOBAL_CONFIG_ACCOUNT_DISCRIMINATOR}`",
                "- Pool layout fields: `pool_bump,index,creator,base_mint,quote_mint,lp_mint,pool_base_token_account,pool_quote_token_account,lp_supply,coin_creator,is_mayhem_mode,is_cashback_coin`",
                "- GlobalConfig fee fields: `lp_fee_basis_points,protocol_fee_basis_points,coin_creator_fee_basis_points,buyback_basis_points`",
                "- production decoding trust: `trusted_for_read_only_event_decoding`; package is official Pump.fun PumpSwap SDK, but live replay confirmation is still required before full thesis scans.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_t007av_report(archive_roots: Iterable[Path], output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    roots = [Path(root) for root in archive_roots]
    events: list[dict[str, Any]] = []
    pool_rows: list[dict[str, Any]] = []
    for root in roots:
        events.extend(decode_swap_events_from_root(root))
        pool_rows.extend(_pool_rows_from_root(root))
    route_audit_rows: list[dict[str, Any]] = []
    for root in roots:
        route_audit_rows.extend(_read_jsonl(root / "pumpswap_transaction_route_audit.jsonl"))
    candidates = build_pumpswap_swap_candidate_inventory(events, pool_rows, [], route_audit_rows=route_audit_rows)
    replay_rows = [build_fee_formula_replay_validation_row(event) for event in events]
    status = classify_fee_model_status(replay_rows)
    status.update(
        {
            "task": "T007AV_PumpSwap_Swap_Event_Capture_And_Fee_Confirmation",
            "generated_at_epoch": time.time(),
            "archive_roots": [str(root) for root in roots],
            "pumpswap_swap_events_decoded": len(events),
            "buy_event_count": sum(1 for row in events if row.get("event_type") == "buy"),
            "sell_event_count": sum(1 for row in events if row.get("event_type") == "sell"),
            "fee_bps_populated_count": sum(1 for row in events if row.get("lp_fee_basis_points") not in (None, "")),
            "candidate_inventory_rows": len(candidates),
            "guardrails": T007AV_GUARDRAILS,
        }
    )
    write_idl_source_inventory(output_dir / "idl_source_inventory.md")
    _write_jsonl(output_dir / "pumpswap_swap_events.jsonl", events)
    _write_csv(output_dir / "pumpswap_swap_candidate_inventory.csv", candidates, [
        "candidate_source",
        "signature",
        "slot",
        "event_type",
        "pool",
        "mint",
        "quote_asset",
        "base_mint",
        "quote_mint",
        "pool_base_token_account",
        "pool_quote_token_account",
        "include_for_replay",
        "exclusion_reason",
    ])
    _write_csv(output_dir / "fee_formula_replay_validation.csv", replay_rows, [
        "signature",
        "event_type",
        "pool",
        "mint",
        "quote_asset",
        "base_amount_in_or_out",
        "quote_amount_in_or_out",
        "user_quote_amount",
        "lp_fee_basis_points",
        "protocol_fee_basis_points",
        "lp_fee",
        "protocol_fee",
        "predicted_quote_no_fee",
        "predicted_quote_with_event_fees",
        "absolute_error",
        "relative_error_pct",
        "validation_status",
        "failure_reason",
    ])
    (output_dir / "fee_model_status.json").write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    status = write_t007av_report(args.archive_root, args.output_dir)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
