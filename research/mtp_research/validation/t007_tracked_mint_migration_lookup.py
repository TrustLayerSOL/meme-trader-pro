from __future__ import annotations

import json
import time
import base64
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.mtp_research.validation.t007_lifecycle_event_store import T007LifecycleEventStore
from research.mtp_research.validation.t007_protocol_idl_registry import (
    PUMP_FUN_PROGRAM_ID,
    PUMPSWAP_PROGRAM_ID,
)
from research.mtp_research.validation.t007_pump_pumpswap_decoders import decode_protocol_instruction_event
from research.mtp_research.validation.t007_pump_pumpswap_decoders import decode_pool_account_snapshot


@dataclass(frozen=True)
class TrackedMintRecord:
    mint: str
    birth_signature: str = ""
    birth_slot: int | None = None
    bonding_curve: str = ""
    associated_bonding_curve: str = ""
    creator: str = ""
    first_seen_at: float | None = None
    graduation_candidate: bool = True
    lookup_slot_gte: int | None = None
    lookup_slot_lte: int | None = None
    candidate_progress_pct: float | None = None
    candidate_threshold_pct: float | None = None

    @property
    def lookup_addresses(self) -> tuple[str, ...]:
        addresses: list[str] = []
        for value in (self.mint, self.bonding_curve, self.associated_bonding_curve, self.creator):
            if value and value not in addresses:
                addresses.append(value)
        return tuple(addresses)


class TrackedMintMigrationLookupClient:
    def __init__(self, rpc_url: str | None = None, *, timeout_seconds: int = 20) -> None:
        self.rpc_url = rpc_url
        self.timeout_seconds = timeout_seconds

    def _resolved_rpc_url(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        return resolve_helius_rpc_url()

    def fetch_transactions_for_address(
        self,
        address: str,
        *,
        limit: int,
        slot_gte: int | None = None,
        slot_lte: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read-only Helius Developer lookup for one tracked mint/curve/pool address."""

        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        remaining = max(1, min(int(limit), 1000))
        rows: list[dict[str, Any]] = []
        pagination_token: str | None = None
        while remaining > 0:
            page_limit = min(remaining, 1000)
            filters: dict[str, Any] = {"status": "succeeded", "tokenAccounts": "all"}
            slot_filter: dict[str, int] = {}
            if slot_gte is not None:
                slot_filter["gte"] = int(slot_gte)
            if slot_lte is not None:
                slot_filter["lte"] = int(slot_lte)
            if slot_filter:
                filters["slot"] = slot_filter
            options: dict[str, Any] = {
                "limit": page_limit,
                "commitment": "confirmed",
                "transactionDetails": "full",
                "sortOrder": "asc",
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "filters": filters,
            }
            if pagination_token:
                options["paginationToken"] = pagination_token
            response = _post_json_rpc(
                self._resolved_rpc_url(),
                {
                    "jsonrpc": "2.0",
                    "id": "mtp-t007-tracked-mint-getTransactionsForAddress",
                    "method": "getTransactionsForAddress",
                    "params": [address, options],
                },
                self.timeout_seconds,
            )
            if isinstance(response, dict) and response.get("error"):
                raise RuntimeError(f"getTransactionsForAddress RPC error: {response.get('error')}")
            result = response.get("result") if isinstance(response, dict) else []
            if isinstance(result, dict):
                data = result.get("data")
                page = [dict(row) for row in data] if isinstance(data, list) else []
                pagination_token = str(result.get("paginationToken") or "") or None
            else:
                page = [dict(row) for row in result] if isinstance(result, list) else []
                pagination_token = None
            rows.extend(page)
            remaining -= len(page)
            if not page or not pagination_token:
                break
        return rows

    def fetch_account_info(self, address: str) -> bytes | None:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        response = _post_json_rpc(
            self._resolved_rpc_url(),
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-tracked-mint-getAccountInfo",
                "method": "getAccountInfo",
                "params": [address, {"encoding": "base64", "commitment": "confirmed"}],
            },
            self.timeout_seconds,
        )
        if isinstance(response, dict) and response.get("error"):
            raise RuntimeError(f"getAccountInfo RPC error: {response.get('error')}")
        value = (((response.get("result") or {}).get("value")) or {}) if isinstance(response, dict) else {}
        data = value.get("data") if isinstance(value, dict) else None
        encoded = data[0] if isinstance(data, list) and data else data if isinstance(data, str) else None
        if not encoded:
            return None
        return base64.b64decode(str(encoded))


def run_tracked_mint_migration_lookup(
    output_root: str | Path,
    *,
    client: TrackedMintMigrationLookupClient | None = None,
    explicit_read_only_rpc_flag: bool,
    max_transactions_per_address: int = 100,
    slot_window_margin: int = 20000,
) -> dict[str, Any]:
    if not explicit_read_only_rpc_flag:
        raise ValueError("tracked mint migration lookup requires explicit read-only RPC flag")
    if max_transactions_per_address < 1 or max_transactions_per_address > 1000:
        raise ValueError("max_transactions_per_address must be between 1 and 1000")
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    tracked_mints = _load_tracked_mints(root, slot_window_margin=int(slot_window_margin))
    rpc = client or TrackedMintMigrationLookupClient()
    store = T007LifecycleEventStore(root)
    summary: dict[str, Any] = {
        "tracked_mint_migration_lookup_enabled": True,
        "tracked_mint_lookup_version": "t007_tracked_mint_migration_lookup_v1",
        "mode": "tracked_mint_migration_lookup",
        "read_only_rpc": True,
        "wallet_signing_disabled": True,
        "trading_disabled": True,
        "paper_trading_disabled": True,
        "valuation_ladder_suppressed": True,
        "global_pumpswap_completeness_required": False,
        "max_transactions_per_address": int(max_transactions_per_address),
        "targeted_slot_window_enabled": True,
        "migration_lookup_slot_window_margin": int(slot_window_margin),
        "tracked_mints_total": len(tracked_mints),
        "graduation_candidates_total": sum(1 for mint in tracked_mints if mint.graduation_candidate),
        "lookup_addresses_total": sum(len(mint.lookup_addresses) for mint in tracked_mints),
        "transactions_fetched": 0,
        "transaction_fetch_failures": 0,
        "decoded_instruction_rows": 0,
        "raw_observation_rows": 0,
        "level_a_migrations_resolved": 0,
        "level_b_migrations_inferred": 0,
        "pool_account_snapshots_fetched": 0,
        "pool_account_snapshot_failures": 0,
        "pool_binding_ambiguous_count": 0,
        "lookup_cap_exhausted_count": 0,
        "unknown_required_decoder_instruction_count": 0,
        "lookup_started_at": time.time(),
    }
    results: list[dict[str, Any]] = []
    for tracked in tracked_mints:
        if not tracked.graduation_candidate:
            result = _result_row(tracked, "NOT_GRADUATION_CANDIDATE", None)
            _append_jsonl(root / "migration_lookup_results.jsonl", result)
            results.append(result)
            continue
        result = _lookup_one_tracked_mint(
            root,
            rpc,
            store,
            tracked,
            max_transactions_per_address=int(max_transactions_per_address),
            summary=summary,
        )
        results.append(result)
    status_counts = Counter(str(row.get("lookup_status") or "UNKNOWN") for row in results)
    terminal_count = sum(
        count
        for status, count in status_counts.items()
        if status
        in {
            "LEVEL_A_CONFIRMED",
            "LEVEL_B_INFERRED",
            "NOT_MIGRATED_WITHIN_WINDOW",
            "NOT_GRADUATION_CANDIDATE",
            "LOOKUP_FAILED",
            "LOOKUP_CAP_EXHAUSTED",
            "POOL_BINDING_AMBIGUOUS",
        }
    )
    failed_count = status_counts.get("LOOKUP_FAILED", 0)
    cap_count = status_counts.get("LOOKUP_CAP_EXHAUSTED", 0)
    ambiguous_count = status_counts.get("POOL_BINDING_AMBIGUOUS", 0)
    total = len(results)
    completion_rate = float(terminal_count) / float(total) if total else 0.0
    failed_rate = float(failed_count) / float(total) if total else 0.0
    blocking: list[str] = []
    if total == 0:
        blocking.append("tracked_mints_total_zero")
    if completion_rate < 0.95:
        blocking.append("tracked_mint_lookup_completion_rate_below_0_95")
    if failed_rate > 0.05:
        blocking.append("tracked_mint_lookup_failed_rate_above_0_05")
    if cap_count:
        blocking.append("tracked_mint_lookup_cap_exhausted")
    if ambiguous_count:
        blocking.append("tracked_pool_binding_ambiguous")
    summary.update(
        {
            "lookup_finished_at": time.time(),
            "migration_lookup_terminal_count": terminal_count,
            "migration_lookup_completion_rate": completion_rate,
            "migration_lookup_failed_count": failed_count,
            "migration_lookup_failed_rate": failed_rate,
            "migration_lookup_cap_exhausted_count": cap_count,
            "pool_binding_ambiguous_count": ambiguous_count,
            "tracked_mint_lookup_status_counts": dict(status_counts),
            "tracked_mint_lookup_gate_passed": not blocking,
            "tracked_mint_lookup_blocking_reasons": blocking,
            "edge_claim_allowed": False,
        }
    )
    _write_json(root / "tracked_mint_migration_lookup_summary.json", summary)
    return summary


def _lookup_one_tracked_mint(
    root: Path,
    rpc: TrackedMintMigrationLookupClient,
    store: T007LifecycleEventStore,
    tracked: TrackedMintRecord,
    *,
    max_transactions_per_address: int,
    summary: dict[str, Any],
) -> dict[str, Any]:
    level_a_rows: list[dict[str, Any]] = []
    level_b_rows: list[dict[str, Any]] = []
    fetch_failed = False
    cap_exhausted = False
    for address in tracked.lookup_addresses:
        attempt = {
            "mint": tracked.mint,
            "lookup_address": address,
            "lookup_route": _lookup_route_for_address(tracked, address),
            "max_transactions_per_address": max_transactions_per_address,
            "lookup_slot_gte": tracked.lookup_slot_gte,
            "lookup_slot_lte": tracked.lookup_slot_lte,
            "candidate_progress_pct": tracked.candidate_progress_pct,
            "candidate_threshold_pct": tracked.candidate_threshold_pct,
            "read_only_rpc": True,
            "attempted_at": time.time(),
        }
        _append_jsonl(root / "migration_lookup_attempts.jsonl", attempt)
        try:
            transactions = rpc.fetch_transactions_for_address(
                address,
                limit=max_transactions_per_address,
                slot_gte=tracked.lookup_slot_gte,
                slot_lte=tracked.lookup_slot_lte,
            )
        except Exception as exc:
            fetch_failed = True
            summary["transaction_fetch_failures"] += 1
            _append_jsonl(
                root / "migration_lookup_results.jsonl",
                {
                    **attempt,
                    "lookup_status": "LOOKUP_FAILED",
                    "failure_reason": type(exc).__name__,
                },
            )
            continue
        summary["transactions_fetched"] += len(transactions)
        if len(transactions) >= max_transactions_per_address:
            cap_exhausted = True
        for tx in transactions:
            raw = _raw_observation_row(tracked, address, tx)
            _append_jsonl(root / "raw_observations.jsonl", raw)
            summary["raw_observation_rows"] += 1
            for decoded in _decode_transaction(tx):
                summary["decoded_instruction_rows"] += 1
                if _row_matches_mint(decoded, tracked.mint):
                    if decoded.get("migration_evidence_level") == "LEVEL_A":
                        decoded["tracked_mint_lookup"] = True
                        decoded["raw_observation_id"] = raw["raw_observation_id"]
                        level_a_rows.append(decoded)
                    elif decoded.get("event_family") == "post_migration_swap_context":
                        inferred = dict(decoded)
                        inferred.update(
                            {
                                "migration_evidence_level": "LEVEL_B",
                                "migration_confirmed": False,
                                "lifecycle_state": "MIGRATION_INFERRED_LEVEL_B",
                                "confidence": "inferred",
                                "detection_method": "first_pumpswap_swap_for_tracked_mint",
                                "tracked_mint_lookup": True,
                                "raw_observation_id": raw["raw_observation_id"],
                            }
                        )
                        level_b_rows.append(inferred)
    pools = {
        str(row.get("pool_or_pair_address") or row.get("pool_address") or "")
        for row in level_a_rows
        if row.get("pool_or_pair_address") or row.get("pool_address")
    }
    if len(pools) > 1:
        result = _result_row(tracked, "POOL_BINDING_AMBIGUOUS", level_a_rows[0] if level_a_rows else None)
        result["pool_candidates"] = sorted(pools)
        _append_jsonl(root / "pool_binding_results.jsonl", result)
        _append_jsonl(root / "migration_lookup_results.jsonl", result)
        return result
    if level_a_rows:
        chosen = _earliest_row(level_a_rows)
        store.write_migration_event(chosen)
        binding = _pool_binding_row(tracked, chosen)
        _append_jsonl(root / "pool_binding_results.jsonl", binding)
        pool_snapshot = _fetch_pool_snapshot(rpc, chosen)
        if pool_snapshot:
            store.write_pool_state_snapshot(pool_snapshot)
            summary["pool_account_snapshots_fetched"] += 1
        elif chosen.get("pool_or_pair_address") or chosen.get("pool_address"):
            summary["pool_account_snapshot_failures"] += 1
        result = _result_row(tracked, "LEVEL_A_CONFIRMED", chosen)
        _append_jsonl(root / "migration_lookup_results.jsonl", result)
        summary["level_a_migrations_resolved"] += 1
        return result
    if cap_exhausted:
        result = _result_row(tracked, "LOOKUP_CAP_EXHAUSTED", None)
        _append_jsonl(root / "migration_lookup_results.jsonl", result)
        return result
    if fetch_failed:
        result = _result_row(tracked, "LOOKUP_FAILED", None)
        _append_jsonl(root / "migration_lookup_results.jsonl", result)
        return result
    if level_b_rows:
        chosen = _earliest_row(level_b_rows)
        _append_jsonl(root / "level_b_inferences.jsonl", chosen)
        result = _result_row(tracked, "LEVEL_B_INFERRED", chosen)
        _append_jsonl(root / "migration_lookup_results.jsonl", result)
        summary["level_b_migrations_inferred"] += 1
        return result
    result = _result_row(tracked, "NOT_MIGRATED_WITHIN_WINDOW", None)
    _append_jsonl(root / "migration_lookup_results.jsonl", result)
    return result


def _fetch_pool_snapshot(
    rpc: TrackedMintMigrationLookupClient,
    migration_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    pool = str(migration_row.get("pool_or_pair_address") or migration_row.get("pool_address") or "")
    if not pool:
        return None
    try:
        raw = rpc.fetch_account_info(pool)
    except Exception:
        return None
    if not raw:
        return None
    snapshot = decode_pool_account_snapshot(pool, raw, slot=_int_or_none(migration_row.get("slot")), observed_at=time.time())
    if snapshot.get("pool_account_decode_status") != "decoded":
        return None
    snapshot.setdefault("mint", snapshot.get("base_mint") or migration_row.get("mint"))
    snapshot.setdefault("migration_signature", migration_row.get("signature"))
    snapshot.setdefault("depth_status", "available")
    return snapshot


def _decode_transaction(tx: Mapping[str, Any]) -> list[dict[str, Any]]:
    signature = _tx_signature(tx)
    slot = _int_or_none(tx.get("slot"))
    observed_at = float(tx.get("blockTime") or tx.get("block_time") or time.time())
    message = ((tx.get("transaction") or {}).get("message") or tx.get("message") or {}) if isinstance(tx, Mapping) else {}
    meta = tx.get("meta") if isinstance(tx, Mapping) else {}
    rows: list[dict[str, Any]] = []
    for index, instruction in enumerate(_instructions(message, meta if isinstance(meta, Mapping) else {})):
        program_id = str(instruction.get("programId") or instruction.get("program_id") or "")
        if program_id not in {PUMP_FUN_PROGRAM_ID, PUMPSWAP_PROGRAM_ID}:
            continue
        row = decode_protocol_instruction_event(
            program_id=program_id,
            instruction=instruction,
            signature=signature,
            slot=slot,
            instruction_index=index,
            observed_at=observed_at,
        )
        if row is not None:
            rows.append(row)
    return rows


def _instructions(message: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw = message.get("instructions") if isinstance(message, Mapping) else []
    if isinstance(raw, list):
        out.extend(dict(item) for item in raw if isinstance(item, dict))
    inner = meta.get("innerInstructions") if isinstance(meta, Mapping) else []
    if isinstance(inner, list):
        for group in inner:
            nested = group.get("instructions") if isinstance(group, dict) else []
            if isinstance(nested, list):
                out.extend(dict(item) for item in nested if isinstance(item, dict))
    return out


def _load_tracked_mints(root: Path, *, slot_window_margin: int) -> list[TrackedMintRecord]:
    source_rows = list(_read_jsonl(root / "tracked_mint_registry.jsonl"))
    if not source_rows:
        source_rows = list(_read_jsonl(root / "birth_audit.jsonl"))
    candidate_windows = _candidate_windows_by_mint(root, slot_window_margin=slot_window_margin)
    candidate_mints = set(candidate_windows)
    out: list[TrackedMintRecord] = []
    seen: set[str] = set()
    for row in source_rows:
        mint = _first(row, "mint", "base_mint", "token_mint", "ca", "address")
        if not mint or mint in seen:
            continue
        seen.add(mint)
        out.append(
            TrackedMintRecord(
                mint=mint,
                birth_signature=_first(row, "birth_signature", "signature", "tx_signature"),
                birth_slot=_int_or_none(row.get("birth_slot") or row.get("slot")),
                bonding_curve=_first(row, "bonding_curve", "bonding_curve_address", "bonding_curve_pda", "curve_account"),
                associated_bonding_curve=_first(row, "associated_bonding_curve", "associated_bonding_curve_address", "associated_curve"),
                creator=_first(row, "creator", "creator_wallet", "deployer", "user"),
                first_seen_at=_float_or_none(row.get("first_seen_at") or row.get("source_timestamp") or row.get("observed_at")),
                graduation_candidate=_graduation_candidate(row, mint, candidate_mints),
                lookup_slot_gte=(candidate_windows.get(mint) or {}).get("lookup_slot_gte"),
                lookup_slot_lte=(candidate_windows.get(mint) or {}).get("lookup_slot_lte"),
                candidate_progress_pct=(candidate_windows.get(mint) or {}).get("candidate_progress_pct"),
                candidate_threshold_pct=(candidate_windows.get(mint) or {}).get("candidate_threshold_pct"),
            )
        )
    return out


def _pool_binding_row(tracked: TrackedMintRecord, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mint": tracked.mint,
        "lookup_status": "POOL_BOUND_LEVEL_A",
        "pool_binding_confidence": "confirmed",
        "migration_signature": row.get("signature"),
        "migration_instruction_index": row.get("instruction_index"),
        "pool_or_pair_address": row.get("pool_or_pair_address") or row.get("pool_address"),
        "pool_address": row.get("pool_or_pair_address") or row.get("pool_address"),
        "base_mint": row.get("base_mint") or row.get("mint"),
        "quote_mint": row.get("quote_mint"),
        "quote_asset": row.get("quote_asset"),
        "pool_base_token_account": row.get("pool_base_token_account"),
        "pool_quote_token_account": row.get("pool_quote_token_account"),
        "evidence_level": "LEVEL_A",
        "raw_observation_id": row.get("raw_observation_id"),
    }


def _result_row(tracked: TrackedMintRecord, status: str, evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "mint": tracked.mint,
        "lookup_status": status,
        "graduation_candidate": tracked.graduation_candidate,
        "birth_signature": tracked.birth_signature,
        "birth_slot": tracked.birth_slot,
        "bonding_curve": tracked.bonding_curve,
        "associated_bonding_curve": tracked.associated_bonding_curve,
        "creator": tracked.creator,
        "terminal": True,
        "result_written_at": time.time(),
    }
    if evidence:
        row.update(
            {
                "evidence_level": evidence.get("migration_evidence_level"),
                "detection_method": evidence.get("detection_method"),
                "migration_signature": evidence.get("signature"),
                "migration_slot": evidence.get("slot"),
                "pool_or_pair_address": evidence.get("pool_or_pair_address") or evidence.get("pool_address"),
                "quote_mint": evidence.get("quote_mint"),
                "quote_asset": evidence.get("quote_asset"),
                "raw_observation_id": evidence.get("raw_observation_id"),
            }
        )
    return row


def _raw_observation_row(tracked: TrackedMintRecord, address: str, tx: Mapping[str, Any]) -> dict[str, Any]:
    signature = _tx_signature(tx)
    slot = tx.get("slot")
    return {
        "raw_observation_id": f"{signature}:{slot}:{address}",
        "source": "tracked_mint_read_only_rpc",
        "mint": tracked.mint,
        "lookup_address": address,
        "signature": signature,
        "slot": slot,
        "block_time": tx.get("blockTime") or tx.get("block_time"),
        "received_at": time.time(),
        "payload": dict(tx),
    }


def _lookup_route_for_address(tracked: TrackedMintRecord, address: str) -> str:
    if address == tracked.mint:
        return "mint"
    if address == tracked.bonding_curve:
        return "bonding_curve"
    if address == tracked.associated_bonding_curve:
        return "associated_bonding_curve"
    if address == tracked.creator:
        return "creator"
    return "unknown"


def _row_matches_mint(row: Mapping[str, Any], mint: str) -> bool:
    return mint in {
        str(row.get("mint") or ""),
        str(row.get("base_mint") or ""),
    }


def _earliest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(rows, key=lambda row: (_int_or_none(row.get("slot")) or 0, _int_or_none(row.get("instruction_index")) or 0))[0]


def _tx_signature(tx: Mapping[str, Any]) -> str:
    signatures = ((tx.get("transaction") or {}).get("signatures") or tx.get("signatures") or []) if isinstance(tx, Mapping) else []
    if isinstance(signatures, list) and signatures:
        return str(signatures[0])
    return str(tx.get("signature") or "")


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _first(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _graduation_candidate(row: Mapping[str, Any], mint: str, candidate_mints: set[str]) -> bool:
    if row.get("graduation_candidate") is not None:
        return str(row.get("graduation_candidate")).strip().lower() in {"1", "true", "yes", "y"}
    return (not candidate_mints) or mint in candidate_mints


def _candidate_windows_by_mint(root: Path, *, slot_window_margin: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in (root / "migration_candidates.jsonl",):
        for row in _read_jsonl(path):
            _add_candidate_window(out, row, slot_window_margin=slot_window_margin, force_candidate=True)
    for path in (root / "true_curve_threshold_crossings.jsonl", root / "threshold_crossings.jsonl"):
        for row in _read_jsonl(path):
            _add_candidate_window(out, row, slot_window_margin=slot_window_margin, force_candidate=False)
    return out


def _add_candidate_window(
    out: dict[str, dict[str, Any]],
    row: Mapping[str, Any],
    *,
    slot_window_margin: int,
    force_candidate: bool,
) -> None:
    mint = _first(row, "mint", "base_mint", "token_mint", "ca", "address")
    if not mint:
        return
    threshold_pct = _float_or_none(row.get("threshold_pct") or row.get("threshold") or row.get("progress_threshold"))
    progress_pct = _float_or_none(row.get("crossing_progress_pct") or row.get("progress_pct") or row.get("highest_progress_pct"))
    is_candidate = force_candidate or _boolish(row.get("complete_already_seen") or row.get("complete") or row.get("migration_seen_before_crossing"))
    if threshold_pct is not None and threshold_pct >= 95.0:
        is_candidate = True
    if progress_pct is not None and progress_pct >= 95.0:
        is_candidate = True
    if not is_candidate:
        return
    slot = _int_or_none(row.get("crossing_slot") or row.get("slot") or row.get("candidate_slot") or row.get("migration_slot"))
    current = out.setdefault(
        mint,
        {
            "lookup_slot_gte": None,
            "lookup_slot_lte": None,
            "candidate_progress_pct": progress_pct,
            "candidate_threshold_pct": threshold_pct,
        },
    )
    if progress_pct is not None:
        current["candidate_progress_pct"] = max(_float_or_none(current.get("candidate_progress_pct")) or 0.0, progress_pct)
    if threshold_pct is not None:
        current["candidate_threshold_pct"] = max(_float_or_none(current.get("candidate_threshold_pct")) or 0.0, threshold_pct)
    if slot is None:
        return
    gte = max(0, int(slot) - int(slot_window_margin))
    lte = int(slot) + int(slot_window_margin)
    current["lookup_slot_gte"] = gte if current.get("lookup_slot_gte") is None else min(int(current["lookup_slot_gte"]), gte)
    current["lookup_slot_lte"] = lte if current.get("lookup_slot_lte") is None else max(int(current["lookup_slot_lte"]), lte)


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
