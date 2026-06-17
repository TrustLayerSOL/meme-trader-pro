"""T007AU offline PumpSwap swap replay reconstruction.

This module is deliberately offline-first. It reconstructs PumpSwap swap replay rows
only when archived candidate/context records contain same-pool before and after
reserve state plus observed input/output deltas. Optional RPC lookup is disabled
by default and must be explicitly enabled with a bounded signature cap.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_T007AT_CANDIDATES = Path(
    "/Users/dianeposs/Projects/meme-trader-pro/outputs/theses/"
    "t007at_fee_formula_confirmation/swap_replay_candidates.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    "/Users/dianeposs/Projects/meme-trader-pro/outputs/theses/"
    "t007au_offline_swap_replay_reconstruction"
)
RPC_SIGNATURE_CAP = 100

GUARDRAILS = {
    "read_only": True,
    "offline_first": True,
    "rpc_disabled_by_default": True,
    "wallet_paths_allowed": False,
    "private_key_paths_allowed": False,
    "trading_paths_allowed": False,
    "signing_paths_allowed": False,
    "valuation_ladder_suppressed": True,
    "mayhem_logic_touched": False,
}

CONTEXT_FILE_NEEDLES = (
    "transaction",
    "swap",
    "reserve",
    "quote",
    "migration",
    "route",
    "trade_flow",
    "pool",
)

FEE_MODEL_CANDIDATES = (
    ("no_fee", 0.0),
    ("fee_25_bps", 25.0),
    ("fee_30_bps", 30.0),
    ("fee_100_bps", 100.0),
    ("fee_125_bps", 125.0),
)

CSV_FIELD_LIMIT = 1024 * 1024 * 32
csv.field_size_limit(CSV_FIELD_LIMIT)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return stripped not in {"", "null", "None", "nan", "NaN"}
    return True


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if _is_present(value):
            return value
    return None


def _to_float(value: Any) -> float | None:
    if not _is_present(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_key = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten(child, child_key))
    elif isinstance(value, list):
        flat[prefix] = json.dumps(value, sort_keys=True, default=str)
    else:
        flat[prefix] = value
    return flat


def _contains_key(flat: Mapping[str, Any], *needles: str) -> bool:
    lowered = [key.lower() for key in flat]
    return any(any(needle in key for key in lowered) for needle in needles)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _candidate_signature(row: Mapping[str, Any]) -> str | None:
    value = _pick(row, "signature", "tx_signature", "transaction_signature", "transaction.signatures.0")
    return str(value) if _is_present(value) else None


def _candidate_pool(row: Mapping[str, Any]) -> str | None:
    value = _pick(
        row,
        "pool",
        "pool_address",
        "pool_or_pair_address",
        "pumpswap_pool",
        "amm_pool",
        "pair_address",
        "poolAddress",
        "pool_state",
    )
    return str(value) if _is_present(value) else None


def _candidate_mint(row: Mapping[str, Any]) -> str | None:
    value = _pick(row, "mint", "base_mint", "token_mint", "token", "input_mint", "output_mint")
    return str(value) if _is_present(value) else None


def _normalize_direction(row: Mapping[str, Any]) -> str | None:
    raw = _pick(row, "swap_direction", "direction", "side", "trade_side")
    if not _is_present(raw):
        return None
    value = str(raw).lower()
    if value in {"quote_to_base", "base_to_quote"}:
        return value
    if value in {"buy", "entry", "entry_quote_to_token", "quote_to_token", "quote_to_base"}:
        return "quote_to_base"
    if value in {"sell", "exit", "exit_token_to_quote", "token_to_quote", "base_to_quote"}:
        return "base_to_quote"
    if "quote" in value and ("token" in value or "base" in value) and "entry" in value:
        return "quote_to_base"
    if ("token" in value or "base" in value) and "quote" in value and "exit" in value:
        return "base_to_quote"
    return None


def _reserve_base_before(row: Mapping[str, Any]) -> float | None:
    return _to_float(
        _pick(
            row,
            "reserve_base_before",
            "base_reserve_before",
            "before_base_reserve",
            "pre_base_reserve",
            "pool_base_reserve_before",
            "before.base_reserve",
            "pre.base_reserve",
            "before.reserve_base",
            "pre.reserve_base",
        )
    )


def _reserve_quote_before(row: Mapping[str, Any]) -> float | None:
    return _to_float(
        _pick(
            row,
            "reserve_quote_before",
            "quote_reserve_before",
            "before_quote_reserve",
            "pre_quote_reserve",
            "pool_quote_reserve_before",
            "before.quote_reserve",
            "pre.quote_reserve",
            "before.reserve_quote",
            "pre.reserve_quote",
        )
    )


def _reserve_base_after(row: Mapping[str, Any]) -> float | None:
    return _to_float(
        _pick(
            row,
            "reserve_base_after",
            "base_reserve_after",
            "after_base_reserve",
            "post_base_reserve",
            "pool_base_reserve_after",
            "after.base_reserve",
            "post.base_reserve",
            "after.reserve_base",
            "post.reserve_base",
        )
    )


def _reserve_quote_after(row: Mapping[str, Any]) -> float | None:
    return _to_float(
        _pick(
            row,
            "reserve_quote_after",
            "quote_reserve_after",
            "after_quote_reserve",
            "post_quote_reserve",
            "pool_quote_reserve_after",
            "after.quote_reserve",
            "post.quote_reserve",
            "after.reserve_quote",
            "post.reserve_quote",
        )
    )


def _input_amount(row: Mapping[str, Any]) -> float | None:
    return _to_float(_pick(row, "input_amount", "amount_in", "swap_input_amount", "in_amount"))


def _output_amount(row: Mapping[str, Any]) -> float | None:
    return _to_float(_pick(row, "output_amount", "amount_out", "swap_output_amount", "out_amount"))


def _slot(row: Mapping[str, Any]) -> Any:
    return _pick(row, "slot", "context.slot", "transaction.slot")


def _block_time(row: Mapping[str, Any]) -> Any:
    return _pick(row, "block_time", "blockTime", "timestamp", "time", "received_at")


def build_replay_row(
    candidate: Mapping[str, Any], context: Mapping[str, Any] | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Build one replay row, rejecting anything without same-pool full reserve state."""

    context = context or {}
    merged = dict(candidate)
    for key, value in context.items():
        if _is_present(value):
            merged[key] = value

    signature = _candidate_signature(merged) or _candidate_signature(candidate)
    candidate_pool = _candidate_pool(candidate)
    context_pool = _candidate_pool(context)
    pool = candidate_pool or context_pool or _candidate_pool(merged)

    if candidate_pool and context_pool and candidate_pool != context_pool:
        return None, _failure(candidate, context, "wrong_pool")
    if not pool:
        return None, _failure(candidate, context, "missing_pool_address")

    reserve_base_before = _reserve_base_before(merged)
    reserve_quote_before = _reserve_quote_before(merged)
    reserve_base_after = _reserve_base_after(merged)
    reserve_quote_after = _reserve_quote_after(merged)
    if reserve_base_before is None:
        return None, _failure(candidate, context, "missing_before_base_reserve")
    if reserve_quote_before is None:
        return None, _failure(candidate, context, "missing_before_quote_reserve")
    if reserve_base_after is None:
        return None, _failure(candidate, context, "missing_after_base_reserve")
    if reserve_quote_after is None:
        return None, _failure(candidate, context, "missing_after_quote_reserve")

    input_amount = _input_amount(merged)
    output_amount = _output_amount(merged)
    if input_amount is None:
        return None, _failure(candidate, context, "missing_input_amount")
    if output_amount is None:
        return None, _failure(candidate, context, "missing_output_amount")

    direction = _normalize_direction(merged)
    if direction is None:
        return None, _failure(candidate, context, "missing_swap_direction")

    return {
        "signature": signature or "",
        "slot": _slot(merged) or "",
        "block_time": _block_time(merged) or "",
        "pool": pool,
        "mint": _candidate_mint(merged) or "",
        "quote_asset": _pick(merged, "quote_asset", "quote_mint", "quote") or "",
        "swap_direction": direction,
        "input_amount": input_amount,
        "output_amount": output_amount,
        "reserve_base_before": reserve_base_before,
        "reserve_quote_before": reserve_quote_before,
        "reserve_base_after": reserve_base_after,
        "reserve_quote_after": reserve_quote_after,
        "reserve_base_delta": reserve_base_after - reserve_base_before,
        "reserve_quote_delta": reserve_quote_after - reserve_quote_before,
        "context_source": _pick(merged, "context_source", "source_artifact") or "",
        "fee_bps_observed": _pick(merged, "fee_bps", "pool_fee_bps", "fee_basis_points") or "",
    }, None


def _failure(
    candidate: Mapping[str, Any], context: Mapping[str, Any] | None, reason: str
) -> dict[str, Any]:
    context = context or {}
    return {
        "signature": _candidate_signature(candidate) or _candidate_signature(context) or "",
        "slot": _slot(candidate) or _slot(context) or "",
        "pool": _candidate_pool(candidate) or _candidate_pool(context) or "",
        "mint": _candidate_mint(candidate) or _candidate_mint(context) or "",
        "failure_reason": reason,
        "candidate_status": candidate.get("candidate_status", ""),
        "source_artifact": candidate.get("source_artifact", ""),
        "context_source": context.get("context_source", ""),
    }


def validate_rpc_reconstruction_options(enable_rpc: bool, max_signatures: int) -> dict[str, Any]:
    """Validate bounded read-only RPC reconstruction options."""

    if not enable_rpc:
        if max_signatures:
            raise ValueError("RPC reconstruction max_signatures requires explicit enable_rpc flag")
        return {"enabled": False, "max_signatures": 0, "cap": RPC_SIGNATURE_CAP}
    if max_signatures <= 0:
        raise ValueError("RPC reconstruction requires max_signatures between 1 and cap")
    if max_signatures > RPC_SIGNATURE_CAP:
        raise ValueError(f"RPC reconstruction max_signatures exceeds cap {RPC_SIGNATURE_CAP}")
    return {"enabled": True, "max_signatures": max_signatures, "cap": RPC_SIGNATURE_CAP}


def fetch_read_only_rpc_transaction_contexts(
    signatures: Iterable[str],
    *,
    enable_rpc: bool,
    max_signatures: int,
    rpc_url: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Optionally fetch read-only transaction metadata for a bounded signature set."""

    options = validate_rpc_reconstruction_options(enable_rpc, max_signatures)
    if not options["enabled"]:
        return {}, {
            "rpc_transactions_requested": 0,
            "rpc_transactions_returned": 0,
            "rpc_transactions_with_pre_post_token_balances": 0,
            "rpc_transactions_with_pumpfun_program": 0,
            "rpc_transactions_with_pumpswap_program": 0,
            "rpc_transactions_with_full_reserves": 0,
            "rpc_errors": 0,
        }
    if not rpc_url:
        raise ValueError("RPC reconstruction requires rpc_url when enable_rpc is true")

    contexts: dict[str, dict[str, Any]] = {}
    stats = Counter()
    for index, signature in enumerate(signatures):
        if index >= max_signatures:
            break
        stats["rpc_transactions_requested"] += 1
        payload = {
            "jsonrpc": "2.0",
            "id": f"t007au-{index}",
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
        }
        request = urllib.request.Request(
            rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310 - user supplied read-only RPC endpoint
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception:
            stats["rpc_errors"] += 1
            continue
        result = decoded.get("result") or {}
        if not result:
            continue
        stats["rpc_transactions_returned"] += 1
        meta = result.get("meta") or {}
        tx = result.get("transaction") or {}
        message = tx.get("message") or {}
        program_ids = []
        for instruction in message.get("instructions") or []:
            if isinstance(instruction, Mapping):
                program_id = instruction.get("programId")
                if program_id:
                    program_ids.append(program_id)
        for inner in meta.get("innerInstructions") or []:
            if not isinstance(inner, Mapping):
                continue
            for instruction in inner.get("instructions") or []:
                if isinstance(instruction, Mapping):
                    program_id = instruction.get("programId")
                    if program_id:
                        program_ids.append(program_id)
        pre_token_balances = meta.get("preTokenBalances", [])
        post_token_balances = meta.get("postTokenBalances", [])
        if pre_token_balances and post_token_balances:
            stats["rpc_transactions_with_pre_post_token_balances"] += 1
        if "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" in program_ids:
            stats["rpc_transactions_with_pumpfun_program"] += 1
        if "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA" in program_ids:
            stats["rpc_transactions_with_pumpswap_program"] += 1
        contexts[signature] = {
            "signature": signature,
            "slot": result.get("slot", ""),
            "block_time": result.get("blockTime", ""),
            "pre_token_balances": json.dumps(pre_token_balances, sort_keys=True),
            "post_token_balances": json.dumps(post_token_balances, sort_keys=True),
            "log_messages": json.dumps(meta.get("logMessages", []), sort_keys=True),
            "rpc_program_ids": ";".join(sorted(set(program_ids))),
            "context_source": "read_only_rpc_getTransaction",
        }
    stats.setdefault("rpc_transactions_requested", 0)
    stats.setdefault("rpc_transactions_returned", 0)
    stats.setdefault("rpc_transactions_with_pre_post_token_balances", 0)
    stats.setdefault("rpc_transactions_with_pumpfun_program", 0)
    stats.setdefault("rpc_transactions_with_pumpswap_program", 0)
    stats.setdefault("rpc_transactions_with_full_reserves", 0)
    stats.setdefault("rpc_errors", 0)
    return contexts, dict(stats)


def _candidate_inventory_row(index: int, candidate: Mapping[str, Any]) -> dict[str, Any]:
    flat = _flatten(candidate)
    return {
        "candidate_index": index,
        "archive_root": candidate.get("archive_root", ""),
        "source_artifact": candidate.get("source_artifact", ""),
        "candidate_status": candidate.get("candidate_status", ""),
        "signature": _candidate_signature(candidate) or "",
        "slot": _slot(candidate) or "",
        "block_time": _block_time(candidate) or "",
        "pool": _candidate_pool(candidate) or "",
        "mint": _candidate_mint(candidate) or "",
        "quote_asset": candidate.get("quote_asset", ""),
        "has_signature": bool(_candidate_signature(candidate)),
        "has_slot_or_block_time": bool(_slot(candidate) or _block_time(candidate)),
        "has_pool_address": bool(_candidate_pool(candidate)),
        "has_mint": bool(_candidate_mint(candidate)),
        "has_base_vault": bool(_pick(candidate, "base_vault", "baseVault", "token_vault")),
        "has_quote_vault": bool(_pick(candidate, "quote_vault", "quoteVault", "sol_vault", "usdc_vault")),
        "has_token_account_changes": _contains_key(flat, "token_account_change", "tokenaccountchange"),
        "has_pre_post_token_balances": _contains_key(flat, "pretok", "posttok", "pre_token", "post_token"),
        "has_instruction_indexes": _contains_key(flat, "instruction_index", "account_index"),
        "has_before_reserve_context": _reserve_base_before(flat) is not None and _reserve_quote_before(flat) is not None,
        "has_after_reserve_context": _reserve_base_after(flat) is not None and _reserve_quote_after(flat) is not None,
        "has_input_output_amounts": _input_amount(flat) is not None and _output_amount(flat) is not None,
        "has_local_context": False,
        "local_context_source": "",
        "reconstruction_status": "not_attempted",
        "failure_reason": "",
    }


def _context_record_from_mapping(record: Mapping[str, Any], source_path: Path) -> dict[str, Any]:
    flat = _flatten(record)
    context: dict[str, Any] = dict(flat)
    context["signature"] = _candidate_signature(flat) or _candidate_signature(record) or ""
    context["pool"] = _candidate_pool(flat) or _candidate_pool(record) or ""
    context["mint"] = _candidate_mint(flat) or _candidate_mint(record) or ""
    context["slot"] = _slot(flat) or _slot(record) or ""
    context["block_time"] = _block_time(flat) or _block_time(record) or ""
    context["context_source"] = str(source_path)
    for canonical, getter in (
        ("reserve_base_before", _reserve_base_before),
        ("reserve_quote_before", _reserve_quote_before),
        ("reserve_base_after", _reserve_base_after),
        ("reserve_quote_after", _reserve_quote_after),
    ):
        value = getter(flat)
        if value is not None:
            context[canonical] = value
    if _input_amount(flat) is not None:
        context["input_amount"] = _input_amount(flat)
    if _output_amount(flat) is not None:
        context["output_amount"] = _output_amount(flat)
    direction = _normalize_direction(flat)
    if direction:
        context["direction"] = direction
    context["has_pre_post_token_balances"] = _contains_key(flat, "pretok", "posttok", "pre_token", "post_token")
    return context


def _iter_context_files(archive_roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in archive_roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = list(root.rglob("*"))
        for path in candidates:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            name = path.name
            if name.startswith("._"):
                continue
            lower = name.lower()
            if path.suffix.lower() not in {".jsonl", ".json", ".csv"}:
                continue
            if any(needle in lower for needle in CONTEXT_FILE_NEEDLES):
                yield path


def _iter_records(path: Path) -> Iterable[Mapping[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        value = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, Mapping):
                        yield value
        elif path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        yield item
            elif isinstance(value, Mapping):
                for key in ("rows", "events", "records", "items", "candidates"):
                    child = value.get(key)
                    if isinstance(child, list):
                        for item in child:
                            if isinstance(item, Mapping):
                                yield item
                        return
                yield value
        elif path.suffix.lower() == ".csv":
            with path.open("r", newline="", encoding="utf-8", errors="ignore") as handle:
                for row in csv.DictReader(handle):
                    yield dict(row)
    except (OSError, json.JSONDecodeError, csv.Error, UnicodeError):
        return


def collect_local_contexts(archive_roots: Iterable[Path]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    contexts_by_signature: dict[str, dict[str, Any]] = {}
    stats: dict[str, Any] = {
        "context_files_scanned": 0,
        "context_records_scanned": 0,
        "context_records_with_signature": 0,
        "context_records_with_pre_post_balances": 0,
        "context_records_with_full_reserves": 0,
        "context_sources": Counter(),
    }
    for path in _iter_context_files(archive_roots):
        stats["context_files_scanned"] += 1
        for record in _iter_records(path):
            stats["context_records_scanned"] += 1
            context = _context_record_from_mapping(record, path)
            signature = context.get("signature")
            if context.get("has_pre_post_token_balances"):
                stats["context_records_with_pre_post_balances"] += 1
            if all(
                _to_float(context.get(field)) is not None
                for field in (
                    "reserve_base_before",
                    "reserve_quote_before",
                    "reserve_base_after",
                    "reserve_quote_after",
                )
            ):
                stats["context_records_with_full_reserves"] += 1
            if not signature:
                continue
            stats["context_records_with_signature"] += 1
            existing = contexts_by_signature.setdefault(signature, {})
            for key, value in context.items():
                if _is_present(value) and not _is_present(existing.get(key)):
                    existing[key] = value
            source_list = existing.setdefault("context_sources", [])
            if str(path) not in source_list:
                source_list.append(str(path))
            stats["context_sources"][str(path.name)] += 1
    stats["context_sources"] = dict(stats["context_sources"].most_common(25))
    return contexts_by_signature, stats


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _predict_constant_product_output(row: Mapping[str, Any], fee_bps: float) -> float | None:
    direction = row.get("swap_direction")
    input_amount = _to_float(row.get("input_amount"))
    base_before = _to_float(row.get("reserve_base_before"))
    quote_before = _to_float(row.get("reserve_quote_before"))
    if input_amount is None or base_before is None or quote_before is None:
        return None
    adjusted_input = input_amount * (1.0 - (fee_bps / 10000.0))
    if adjusted_input <= 0:
        return None
    invariant = base_before * quote_before
    if direction == "quote_to_base":
        new_quote = quote_before + adjusted_input
        if new_quote <= 0:
            return None
        return base_before - (invariant / new_quote)
    if direction == "base_to_quote":
        new_base = base_before + adjusted_input
        if new_base <= 0:
            return None
        return quote_before - (invariant / new_base)
    return None


def build_fee_model_comparison(replay_rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
    if not replay_rows:
        return [
            {
                "fee_model": "no_replay_rows",
                "fee_bps": "",
                "rows_tested": 0,
                "median_abs_relative_error": "",
                "p90_abs_relative_error": "",
                "max_abs_relative_error": "",
            }
        ], "unknown", "low"

    comparison: list[dict[str, Any]] = []
    best_median: float | None = None
    for name, fee_bps in FEE_MODEL_CANDIDATES:
        errors: list[float] = []
        for row in replay_rows:
            observed = _to_float(row.get("output_amount"))
            predicted = _predict_constant_product_output(row, fee_bps)
            if observed is None or observed == 0 or predicted is None:
                continue
            errors.append(abs(predicted - observed) / abs(observed))
        median = _percentile(errors, 0.5)
        if median is not None and (best_median is None or median < best_median):
            best_median = median
        comparison.append(
            {
                "fee_model": name,
                "fee_bps": fee_bps,
                "rows_tested": len(errors),
                "median_abs_relative_error": median if median is not None else "",
                "p90_abs_relative_error": _percentile(errors, 0.9) if errors else "",
                "max_abs_relative_error": max(errors) if errors else "",
            }
        )

    if best_median is not None and best_median <= 0.001:
        return comparison, "high", "high"
    if best_median is not None and best_median <= 0.01:
        return comparison, "medium", "medium"
    return comparison, "unknown", "low"


def build_readiness_gate_after_t007au(
    *,
    reconstructed_replay_rows: int,
    fee_model_status: str,
    quote_confidence: str,
) -> dict[str, Any]:
    formula_ready = reconstructed_replay_rows > 0 and fee_model_status in {"medium", "high"}
    quote_ready = quote_confidence in {"medium", "high"}
    full_allowed = formula_ready and quote_ready
    return {
        "task": "T007AU",
        "read_only_offline_reconstruction": True,
        "valuation_ladder_suppressed": True,
        "wallet_private_key_trading_signing_paths_allowed": False,
        "reconstructed_replay_rows": reconstructed_replay_rows,
        "fee_model_status": fee_model_status,
        "quote_confidence": quote_confidence,
        "full_post_migration_exit_thesis_allowed": full_allowed,
        "full_thesis_scans_remain_blocked": not full_allowed,
        "partial_post_migration_depth_60m_still_requires_user_approval": True,
        "partial_post_migration_depth_60m_required_if_continuing": not full_allowed,
        "decision": (
            "T007AU_REPLAY_RECONSTRUCTED_FEE_MODEL_READY"
            if full_allowed
            else "T007AU_REPLAY_CONTEXT_STILL_INSUFFICIENT"
        ),
    }


def reconstruct_from_candidates(
    candidate_rows: list[dict[str, Any]],
    contexts_by_signature: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    stats = Counter()

    for index, candidate in enumerate(candidate_rows):
        inv = _candidate_inventory_row(index, candidate)
        signature = inv["signature"]
        context = dict(contexts_by_signature.get(signature, {})) if signature else {}
        if context:
            inv["has_local_context"] = True
            sources = context.get("context_sources") or [context.get("context_source", "")]
            inv["local_context_source"] = ";".join(str(source) for source in sources if source)
        merged_context = dict(candidate)
        merged_context.update(context)
        if context:
            merged_context["context_source"] = inv["local_context_source"]
        row, failure = build_replay_row(candidate, merged_context)
        if row:
            inv["reconstruction_status"] = "reconstructed"
            replay_rows.append(row)
            stats["reconstructed"] += 1
        elif failure:
            inv["reconstruction_status"] = "failed"
            inv["failure_reason"] = failure["failure_reason"]
            failures.append(failure)
            stats[failure["failure_reason"]] += 1
        inventory.append(inv)

    stats_payload = {
        "candidates_inspected": len(candidate_rows),
        "candidates_with_signatures": sum(1 for row in inventory if row["has_signature"]),
        "candidates_with_pool_address": sum(1 for row in inventory if row["has_pool_address"]),
        "candidates_with_local_context": sum(1 for row in inventory if row["has_local_context"]),
        "candidates_with_candidate_pre_post_context": sum(
            1 for row in inventory if row["has_pre_post_token_balances"]
        ),
        "candidates_with_candidate_before_reserves": sum(
            1 for row in inventory if row["has_before_reserve_context"]
        ),
        "candidates_with_candidate_after_reserves": sum(
            1 for row in inventory if row["has_after_reserve_context"]
        ),
        "reconstructed_replay_rows": len(replay_rows),
        "top_reconstruction_failure_reasons": dict(stats.most_common(10)),
    }
    return inventory, replay_rows, failures, stats_payload


def _summary_markdown(status: Mapping[str, Any], output_dir: Path) -> str:
    failure_reasons = status.get("top_reconstruction_failure_reasons", {})
    reason_lines = "\n".join(f"- {key}: {value}" for key, value in failure_reasons.items()) or "- none"
    return f"""# T007AU Offline PumpSwap Swap Replay Reconstruction

## Scope

Offline-only reconstruction from T007AT swap replay candidates and existing local artifacts. No live scan was run. Optional read-only RPC reconstruction remains disabled unless explicitly requested with a bounded signature cap.

## Guardrails

- no trading: true
- no paper trading: true
- no wallet/private-key/signing/execution paths: true
- valuation ladder suppressed: true
- Mayhem logic touched: false

## Results

- candidates inspected: {status.get('candidates_inspected', 0)}
- candidates with signatures: {status.get('candidates_with_signatures', 0)}
- candidates with local context: {status.get('candidates_with_local_context', 0)}
- candidates with candidate before reserves: {status.get('candidates_with_candidate_before_reserves', 0)}
- candidates with candidate after reserves: {status.get('candidates_with_candidate_after_reserves', 0)}
- local context records with pre/post balances: {status.get('context_records_with_pre_post_balances', 0)}
- local context records with full reserves: {status.get('context_records_with_full_reserves', 0)}
- rpc reconstruction enabled: {status.get('rpc_reconstruction_enabled', False)}
- rpc max signatures: {status.get('rpc_max_signatures', 0)}
- rpc transactions requested: {status.get('rpc_transactions_requested', 0)}
- rpc transactions returned: {status.get('rpc_transactions_returned', 0)}
- rpc transactions with pre/post token balances: {status.get('rpc_transactions_with_pre_post_token_balances', 0)}
- rpc transactions with Pump.fun program: {status.get('rpc_transactions_with_pumpfun_program', 0)}
- rpc transactions with PumpSwap program: {status.get('rpc_transactions_with_pumpswap_program', 0)}
- reconstructed replay rows: {status.get('reconstructed_replay_rows', 0)}
- fee model status: {status.get('fee_model_status', 'unknown')}
- quote confidence: {status.get('quote_confidence', 'low')}

## Top reconstruction failure reasons

{reason_lines}

## Missing context if zero replay rows

A replayable row requires same-pool before base reserve, before quote reserve, after base reserve, after quote reserve, observed input amount, observed output amount, direction, and slot/time. If reconstructed rows remain zero, the local archives did not contain complete same-pool transaction-level reserve deltas for the T007AT signatures.

## Outputs

- `{output_dir / 'candidate_context_inventory.csv'}`
- `{output_dir / 'reconstructed_replay_rows.csv'}`
- `{output_dir / 'reconstruction_failures.csv'}`
- `{output_dir / 'fee_model_comparison.csv'}`
- `{output_dir / 'reconstruction_status.json'}`
- `{output_dir / 'readiness_gate_after_t007au.json'}`
"""


def write_t007au_offline_swap_replay_reconstruction_report(
    *,
    candidate_csv: Path = DEFAULT_T007AT_CANDIDATES,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    archive_roots: list[Path] | None = None,
    enable_rpc: bool = False,
    max_rpc_signatures: int = 0,
    rpc_url: str | None = None,
) -> dict[str, Any]:
    validate_rpc_reconstruction_options(enable_rpc, max_rpc_signatures)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = _read_csv(candidate_csv)
    roots = archive_roots or sorted(
        {Path(row["archive_root"]) for row in candidate_rows if _is_present(row.get("archive_root"))}
    )
    contexts_by_signature, context_stats = collect_local_contexts(roots)
    rpc_stats: dict[str, Any] = {
        "rpc_transactions_requested": 0,
        "rpc_transactions_returned": 0,
        "rpc_transactions_with_pre_post_token_balances": 0,
        "rpc_transactions_with_pumpfun_program": 0,
        "rpc_transactions_with_pumpswap_program": 0,
        "rpc_transactions_with_full_reserves": 0,
        "rpc_errors": 0,
    }

    if enable_rpc:
        signatures = [row.get("signature", "") for row in candidate_rows if row.get("signature")]
        rpc_contexts, rpc_stats = fetch_read_only_rpc_transaction_contexts(
            signatures,
            enable_rpc=enable_rpc,
            max_signatures=max_rpc_signatures,
            rpc_url=rpc_url,
        )
        for signature, context in rpc_contexts.items():
            existing = contexts_by_signature.setdefault(signature, {})
            for key, value in context.items():
                if _is_present(value) and not _is_present(existing.get(key)):
                    existing[key] = value

    inventory, replay_rows, failures, reconstruction_stats = reconstruct_from_candidates(
        candidate_rows, contexts_by_signature
    )
    fee_comparison, fee_model_status, quote_confidence = build_fee_model_comparison(replay_rows)
    gate = build_readiness_gate_after_t007au(
        reconstructed_replay_rows=len(replay_rows),
        fee_model_status=fee_model_status,
        quote_confidence=quote_confidence,
    )

    status: dict[str, Any] = {
        "task": "T007AU_Offline_PumpSwap_Swap_Replay_Reconstruction",
        "generated_at_epoch": time.time(),
        "candidate_csv": str(candidate_csv),
        "output_dir": str(output_dir),
        "archive_roots": [str(root) for root in roots],
        "rpc_reconstruction_enabled": enable_rpc,
        "rpc_max_signatures": max_rpc_signatures if enable_rpc else 0,
        "guardrails": GUARDRAILS,
        **context_stats,
        **rpc_stats,
        **reconstruction_stats,
        "fee_model_status": fee_model_status,
        "quote_confidence": quote_confidence,
        "full_post_migration_exit_thesis_allowed": gate["full_post_migration_exit_thesis_allowed"],
        "partial_post_migration_depth_60m_required_if_continuing": gate[
            "partial_post_migration_depth_60m_required_if_continuing"
        ],
        "missing_if_zero_rows": (
            "complete same-pool before/after reserve context for swap signatures"
            if not replay_rows
            else ""
        ),
    }

    _write_csv(
        output_dir / "candidate_context_inventory.csv",
        inventory,
        [
            "candidate_index",
            "archive_root",
            "source_artifact",
            "candidate_status",
            "signature",
            "slot",
            "block_time",
            "pool",
            "mint",
            "quote_asset",
            "has_signature",
            "has_slot_or_block_time",
            "has_pool_address",
            "has_mint",
            "has_base_vault",
            "has_quote_vault",
            "has_token_account_changes",
            "has_pre_post_token_balances",
            "has_instruction_indexes",
            "has_before_reserve_context",
            "has_after_reserve_context",
            "has_input_output_amounts",
            "has_local_context",
            "local_context_source",
            "reconstruction_status",
            "failure_reason",
        ],
    )
    _write_csv(
        output_dir / "reconstructed_replay_rows.csv",
        replay_rows,
        [
            "signature",
            "slot",
            "block_time",
            "pool",
            "mint",
            "quote_asset",
            "swap_direction",
            "input_amount",
            "output_amount",
            "reserve_base_before",
            "reserve_quote_before",
            "reserve_base_after",
            "reserve_quote_after",
            "reserve_base_delta",
            "reserve_quote_delta",
            "fee_bps_observed",
            "context_source",
        ],
    )
    _write_csv(
        output_dir / "reconstruction_failures.csv",
        failures,
        [
            "signature",
            "slot",
            "pool",
            "mint",
            "failure_reason",
            "candidate_status",
            "source_artifact",
            "context_source",
        ],
    )
    _write_csv(
        output_dir / "fee_model_comparison.csv",
        fee_comparison,
        [
            "fee_model",
            "fee_bps",
            "rows_tested",
            "median_abs_relative_error",
            "p90_abs_relative_error",
            "max_abs_relative_error",
        ],
    )
    _write_json(output_dir / "reconstruction_status.json", status)
    _write_json(output_dir / "readiness_gate_after_t007au.json", gate)
    (output_dir / "summary.md").write_text(_summary_markdown(status, output_dir), encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-csv", type=Path, default=DEFAULT_T007AT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive-root", action="append", type=Path, default=None)
    parser.add_argument("--enable-rpc-reconstruction", action="store_true")
    parser.add_argument("--max-rpc-signatures", type=int, default=0)
    parser.add_argument("--rpc-url", default=None)
    args = parser.parse_args(argv)
    status = write_t007au_offline_swap_replay_reconstruction_report(
        candidate_csv=args.candidate_csv,
        output_dir=args.output_dir,
        archive_roots=args.archive_root,
        enable_rpc=args.enable_rpc_reconstruction,
        max_rpc_signatures=args.max_rpc_signatures,
        rpc_url=args.rpc_url,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
