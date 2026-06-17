from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from research.mtp_research.validation.t007_lifecycle_event_store import T007LifecycleEventStore
from research.mtp_research.validation.t007_protocol_idl_registry import PUMPSWAP_PROGRAM_ID
from research.mtp_research.validation.t007_pump_pumpswap_decoders import decode_protocol_instruction_event


class PumpSwapGapBackfillClient:
    def __init__(self, rpc_url: str | None = None, *, timeout_seconds: int = 20) -> None:
        self.rpc_url = rpc_url
        self.timeout_seconds = timeout_seconds

    def _resolved_rpc_url(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        return resolve_helius_rpc_url()

    def fetch_signatures_for_address(
        self,
        address: str,
        *,
        limit: int,
        before: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        options: dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if before:
            options["before"] = before
        if until:
            options["until"] = until
        response = _post_json_rpc(
            self._resolved_rpc_url(),
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-pumpswap-gap-backfill-signatures",
                "method": "getSignaturesForAddress",
                "params": [address, options],
            },
            self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, dict) else []
        return [dict(row) for row in result] if isinstance(result, list) else []

    def fetch_transaction(self, signature: str) -> dict[str, Any]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        response = _post_json_rpc(
            self._resolved_rpc_url(),
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-pumpswap-gap-backfill-transaction",
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                        "commitment": "confirmed",
                    },
                ],
            },
            self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, dict) else {}
        return dict(result) if isinstance(result, dict) else {}


def run_pumpswap_gap_backfill(
    output_root: str | Path,
    *,
    client: PumpSwapGapBackfillClient | None = None,
    explicit_read_only_rpc_flag: bool,
    max_signatures: int = 100,
) -> dict[str, Any]:
    if not explicit_read_only_rpc_flag:
        raise ValueError("PumpSwap gap backfill requires explicit read-only RPC flag")
    if max_signatures < 1 or max_signatures > 100:
        raise ValueError("max_signatures must be between 1 and 100")
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    rpc = client or PumpSwapGapBackfillClient()
    gap_health_before = _read_json(root / "source_gap_health.json")
    intervals = _gap_intervals(root, gap_health_before)
    signature_batches = _signature_batches(rpc, intervals, max_signatures=max_signatures)
    signatures = [row for batch in signature_batches for row in batch["signatures"]]
    store = T007LifecycleEventStore(root)
    summary: dict[str, Any] = {
        "mode": "pumpswap_gap_backfill",
        "read_only_rpc": True,
        "wallet_signing_disabled": True,
        "trading_disabled": True,
        "paper_trading_disabled": True,
        "max_signatures": int(max_signatures),
        "intervals_requested": len(intervals),
        "intervals_backfilled": 0,
        "signatures_found": len(signatures),
        "transactions_fetched": 0,
        "transaction_fetch_failures": 0,
        "decoded_instruction_rows": 0,
        "level_a_migrations_backfilled": 0,
        "cap_exhausted": any(batch.get("cap_exhausted") for batch in signature_batches),
        "backfill_started_at": time.time(),
    }
    for batch in signature_batches:
        interval = batch.get("interval")
        batch_failures_before = int(summary["transaction_fetch_failures"])
        for signature_row in batch["signatures"]:
            _process_backfill_signature(signature_row, rpc, store, summary)
        if interval is not None and int(summary["transaction_fetch_failures"]) == batch_failures_before and not batch.get("cap_exhausted"):
            interval["backfill_status"] = "succeeded"
            summary["intervals_backfilled"] += 1
        elif interval is not None:
            interval["backfill_status"] = "failed"
    if not signature_batches:
        signatures = rpc.fetch_signatures_for_address(PUMPSWAP_PROGRAM_ID, limit=max_signatures)
        summary["signatures_found"] = len(signatures)
        summary["cap_exhausted"] = len(signatures) >= int(max_signatures)
        for signature_row in signatures:
            _process_backfill_signature(signature_row, rpc, store, summary)
    summary["backfill_finished_at"] = time.time()
    backfill_succeeded = (
        summary["transaction_fetch_failures"] == 0
        and not summary["cap_exhausted"]
        and summary["transactions_fetched"] == summary["signatures_found"]
        and (not intervals or summary["intervals_backfilled"] == len(intervals))
    )
    blocking: list[str] = []
    if summary["transaction_fetch_failures"]:
        blocking.append("backfill_transaction_fetch_failures")
    if summary["cap_exhausted"]:
        blocking.append("backfill_signature_cap_exhausted")
    if intervals and summary["intervals_backfilled"] != len(intervals):
        blocking.append("backfill_intervals_not_fully_covered")
    source_gap = {
        "source_gap_gate_passed": backfill_succeeded,
        "backfill_succeeded": backfill_succeeded,
        "backfill_source": "pumpswap_read_only_getSignaturesForAddress_getTransaction",
        "source_gap_blocking_reasons": blocking,
        "source_gap_intervals": intervals,
        "unbackfilled_gap_count": 0 if backfill_succeeded else max(1, len(intervals) - int(summary["intervals_backfilled"]), int(summary["transaction_fetch_failures"] or 0)),
        "signatures_found": summary["signatures_found"],
        "transactions_fetched": summary["transactions_fetched"],
        "transaction_fetch_failures": summary["transaction_fetch_failures"],
        "level_a_migrations_backfilled": summary["level_a_migrations_backfilled"],
        "read_only_rpc": True,
        "wallet_signing_disabled": True,
        "trading_disabled": True,
        "paper_trading_disabled": True,
    }
    _write_json(root / "pumpswap_gap_backfill_summary.json", summary)
    _write_json(root / "source_gap_health.json", source_gap)
    return summary


def _process_backfill_signature(
    signature_row: dict[str, Any],
    rpc: PumpSwapGapBackfillClient,
    store: T007LifecycleEventStore,
    summary: dict[str, Any],
) -> None:
        signature = str(signature_row.get("signature") or "").strip()
        if not signature:
            return
        tx = rpc.fetch_transaction(signature)
        if not tx:
            summary["transaction_fetch_failures"] += 1
            return
        summary["transactions_fetched"] += 1
        for decoded in _decode_pumpswap_transaction(signature, tx):
            summary["decoded_instruction_rows"] += 1
            decoded["backfilled_from_read_only_rpc"] = True
            if decoded.get("migration_evidence_level") == "LEVEL_A":
                summary["level_a_migrations_backfilled"] += 1
                store.write_migration_event(decoded)


def _decode_pumpswap_transaction(signature: str, tx: dict[str, Any]) -> list[dict[str, Any]]:
    slot = tx.get("slot")
    observed_at = float(tx.get("blockTime") or tx.get("block_time") or time.time())
    message = ((tx.get("transaction") or {}).get("message") or tx.get("message") or {}) if isinstance(tx, dict) else {}
    rows: list[dict[str, Any]] = []
    for index, instruction in enumerate(_instructions(message, tx.get("meta") or {})):
        program_id = str(instruction.get("programId") or instruction.get("program_id") or "")
        if program_id != PUMPSWAP_PROGRAM_ID:
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


def _instructions(message: dict[str, Any], meta: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw = message.get("instructions") if isinstance(message, dict) else []
    if isinstance(raw, list):
        out.extend(dict(item) for item in raw if isinstance(item, dict))
    inner = meta.get("innerInstructions") if isinstance(meta, dict) else []
    if isinstance(inner, list):
        for group in inner:
            nested = group.get("instructions") if isinstance(group, dict) else []
            if isinstance(nested, list):
                out.extend(dict(item) for item in nested if isinstance(item, dict))
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _gap_intervals(root: Path, source_gap: dict[str, Any]) -> list[dict[str, Any]]:
    intervals = [dict(row) for row in source_gap.get("source_gap_intervals") or [] if isinstance(row, dict)]
    if intervals:
        return intervals
    summary = _read_json(root / "global_migration_summary.json")
    route_status = summary.get("route_status_by_route") if isinstance(summary, dict) else {}
    if not isinstance(route_status, dict):
        return []
    out: list[dict[str, Any]] = []
    for status in route_status.values():
        if not isinstance(status, dict):
            continue
        for interval in status.get("source_gap_intervals") or []:
            if isinstance(interval, dict):
                out.append(dict(interval))
    return out


def _signature_batches(
    rpc: PumpSwapGapBackfillClient,
    intervals: list[dict[str, Any]],
    *,
    max_signatures: int,
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for interval in intervals:
        before = interval.get("first_seen_signature_after_gap")
        until = interval.get("last_seen_signature_before_gap")
        if not before or not until:
            interval["backfill_status"] = "missing_signature_bounds"
            batches.append({"interval": interval, "signatures": [], "cap_exhausted": False})
            continue
        signatures = rpc.fetch_signatures_for_address(
            PUMPSWAP_PROGRAM_ID,
            limit=max_signatures,
            before=str(before),
            until=str(until),
        )
        batches.append(
            {
                "interval": interval,
                "signatures": signatures,
                "cap_exhausted": len(signatures) >= int(max_signatures),
            }
        )
    return batches
