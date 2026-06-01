"""Bounded Pump.fun first-two-hour raw lifecycle collector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest, HeliusTransactionRecord
from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    load_census_rows,
)
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord, RawTransactionStore


PACIFIC = ZoneInfo("America/Los_Angeles")
REGIME_WEEKDAYS = {0, 1, 2}
REGIME_WINDOWS = [(6 * 3600, 12 * 3600), (17 * 3600, 22 * 3600)]
MAX_LIFECYCLE_SECONDS = 7200


def select_lifecycle_rows(
    rows: list[PumpFunCreationCensusRow],
    *,
    lane: str,
    limit: int,
) -> list[PumpFunCreationCensusRow]:
    accepted = [
        row for row in rows
        if row.accepted and row.mint and row.block_time is not None and row.bonding_curve
    ]
    if lane == "regime":
        accepted = [row for row in accepted if _in_launch_regime(int(row.block_time or 0))]
    elif lane != "existing":
        raise ValueError("lane must be 'existing' or 'regime'")
    deduped = _dedupe_by_mint(accepted)
    return deduped[:limit]


def collect_pumpfun_lifecycle(
    *,
    census_path: Path | str = "data/normalized/pumpfun_creation_census.jsonl",
    raw_path: Path | str = "data/raw/helius_transactions.jsonl",
    lane: str = "existing",
    target_launches: int = 1500,
    signatures_per_page: int = 1000,
    max_signature_pages_per_launch: int = 1,
    max_transactions_per_launch: int = 100,
    collection_method: str = "signature_hydrate",
    address_window_workers: int = 1,
    execute: bool = False,
    adapter: HeliusHistoricalAdapter | None = None,
) -> dict[str, Any]:
    rows = load_census_rows(census_path)
    selected = select_lifecycle_rows(rows, lane=lane, limit=target_launches)
    base_summary = {
        "lane": lane,
        "census_rows": len(rows),
        "selected_launches": len(selected),
        "target_launches": target_launches,
        "max_lifecycle_seconds": MAX_LIFECYCLE_SECONDS,
        "signatures_per_page": signatures_per_page,
        "max_signature_pages_per_launch": max_signature_pages_per_launch,
        "max_transactions_per_launch": max_transactions_per_launch,
        "collection_method": collection_method,
        "address_window_workers": max(1, address_window_workers),
        "estimated_signature_requests": len(selected) * max_signature_pages_per_launch,
        "estimated_transaction_requests_up_to": len(selected) * max_transactions_per_launch,
    }
    if not execute:
        return {
            **base_summary,
            "network_calls": 0,
            "launches_processed": 0,
            "signatures_seen": 0,
            "signatures_in_window": 0,
            "transactions_fetched": 0,
            "raw_inserted": 0,
            "raw_updated": 0,
            "warning_flags": [],
        }

    adapter = adapter or HeliusHistoricalAdapter.from_env()
    store = RawTransactionStore(raw_path)
    existing_signatures = {record.signature for record in store.load_all()}
    totals = {
        "network_calls": 0,
        "launches_processed": 0,
        "signatures_seen": 0,
        "signatures_in_window": 0,
        "transactions_fetched": 0,
        "raw_inserted": 0,
        "raw_updated": 0,
    }
    warnings: list[str] = []

    if collection_method == "address_window" and address_window_workers > 1:
        window_totals = _collect_address_window_parallel(
            selected,
            adapter=adapter,
            store=store,
            existing_signatures=existing_signatures,
            lane=lane,
            max_transactions_per_launch=max_transactions_per_launch,
            workers=address_window_workers,
        )
        for key, value in window_totals.items():
            totals[key] += value
        return {**base_summary, **totals, "warning_flags": warnings}

    for row in selected:
        if collection_method == "address_window":
            window_totals = _collect_launch_with_address_window(
                row,
                adapter=adapter,
                store=store,
                existing_signatures=existing_signatures,
                lane=lane,
                max_transactions_per_launch=max_transactions_per_launch,
            )
            for key, value in window_totals.items():
                totals[key] += value
            continue
        if collection_method != "signature_hydrate":
            raise ValueError("collection_method must be 'signature_hydrate' or 'address_window'")
        launch_records, signature_requests = _collect_launch_signature_records(
            row,
            adapter=adapter,
            signatures_per_page=signatures_per_page,
            max_signature_pages=max_signature_pages_per_launch,
        )
        totals["network_calls"] += signature_requests
        totals["launches_processed"] += 1
        totals["signatures_seen"] += sum(1 for _ in launch_records["seen_records"])
        in_window_records = launch_records["in_window_records"][:max_transactions_per_launch]
        new_records = [record for record in in_window_records if record.signature not in existing_signatures]
        totals["signatures_in_window"] += len(in_window_records)
        if not new_records:
            continue
        bodies = adapter.fetch_transactions([record.signature for record in new_records])
        totals["network_calls"] += len(new_records)
        raw_records = [
            _raw_record_from_body(signature_record, body, row, lane)
            for signature_record, body in zip(new_records, bodies, strict=False)
            if body
        ]
        counts = store.append_new_many(raw_records)
        existing_signatures.update(record.signature for record in raw_records)
        totals["transactions_fetched"] += len(raw_records)
        totals["raw_inserted"] += counts["inserted"]
        totals["raw_updated"] += counts["updated"]

    return {**base_summary, **totals, "warning_flags": warnings}


def _collect_address_window_parallel(
    rows: list[PumpFunCreationCensusRow],
    *,
    adapter: HeliusHistoricalAdapter,
    store: RawTransactionStore,
    existing_signatures: set[str],
    lane: str,
    max_transactions_per_launch: int,
    workers: int,
) -> dict[str, int]:
    totals = {
        "network_calls": 0,
        "launches_processed": 0,
        "signatures_seen": 0,
        "signatures_in_window": 0,
        "transactions_fetched": 0,
        "raw_inserted": 0,
        "raw_updated": 0,
    }
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        results = list(
            executor.map(
                lambda row: _fetch_launch_with_address_window(
                    row,
                    adapter=adapter,
                    max_transactions_per_launch=max_transactions_per_launch,
                ),
                rows,
            )
        )
    raw_records: list[RawTransactionRecord] = []
    for row, transactions in zip(rows, results, strict=False):
        totals["network_calls"] += 1
        totals["launches_processed"] += 1
        totals["signatures_seen"] += len(transactions)
        totals["signatures_in_window"] += len(transactions)
        for body in transactions:
            signature = _signature_from_body(body)
            if not signature or signature in existing_signatures:
                continue
            record = _raw_record_from_gtfa_body(signature, body, row, lane)
            raw_records.append(record)
            existing_signatures.add(signature)
    counts = store.append_new_many(raw_records)
    totals["transactions_fetched"] += len(raw_records)
    totals["raw_inserted"] += counts["inserted"]
    totals["raw_updated"] += counts["updated"]
    return totals


def _collect_launch_with_address_window(
    row: PumpFunCreationCensusRow,
    *,
    adapter: HeliusHistoricalAdapter,
    store: RawTransactionStore,
    existing_signatures: set[str],
    lane: str,
    max_transactions_per_launch: int,
) -> dict[str, int]:
    transactions = _fetch_launch_with_address_window(
        row,
        adapter=adapter,
        max_transactions_per_launch=max_transactions_per_launch,
    )
    raw_records = []
    for body in transactions:
        signature = _signature_from_body(body)
        if not signature or signature in existing_signatures:
            continue
        raw_records.append(_raw_record_from_gtfa_body(signature, body, row, lane))
    counts = store.append_new_many(raw_records)
    existing_signatures.update(record.signature for record in raw_records)
    return {
        "network_calls": 1,
        "launches_processed": 1,
        "signatures_seen": len(transactions),
        "signatures_in_window": len(transactions),
        "transactions_fetched": len(raw_records),
        "raw_inserted": counts["inserted"],
        "raw_updated": counts["updated"],
    }


def _fetch_launch_with_address_window(
    row: PumpFunCreationCensusRow,
    *,
    adapter: HeliusHistoricalAdapter,
    max_transactions_per_launch: int,
) -> list[dict[str, Any]]:
    launch_ts = int(row.block_time or 0)
    result = adapter.fetch_transactions_for_address_window(
        row.bonding_curve or "",
        start_time=launch_ts,
        end_time=launch_ts + MAX_LIFECYCLE_SECONDS,
        limit=max_transactions_per_launch,
    )
    return result["transactions"][:max_transactions_per_launch]


def _collect_launch_signature_records(
    row: PumpFunCreationCensusRow,
    *,
    adapter: HeliusHistoricalAdapter,
    signatures_per_page: int,
    max_signature_pages: int,
) -> tuple[dict[str, list[HeliusTransactionRecord]], int]:
    launch_ts = int(row.block_time or 0)
    end_ts = launch_ts + MAX_LIFECYCLE_SECONDS
    before = None
    seen_records: list[HeliusTransactionRecord] = []
    in_window_records: list[HeliusTransactionRecord] = []
    requests = 0
    for _ in range(max_signature_pages):
        result = adapter.fetch_signatures_for_address(
            HeliusBackfillRequest(
                address=row.bonding_curve or "",
                token_mint=row.mint,
                role="pumpfun_bonding_curve_lifecycle_2h",
                limit=signatures_per_page,
                before=before,
            )
        )
        requests += 1
        if not result.records:
            break
        seen_records.extend(result.records)
        for record in result.records:
            if record.block_time is None:
                continue
            if launch_ts <= record.block_time <= end_ts:
                in_window_records.append(record)
        if any(record.block_time is not None and record.block_time < launch_ts for record in result.records):
            break
        before = result.next_before
        if not before:
            break
    return {"seen_records": seen_records, "in_window_records": in_window_records}, requests


def _raw_record_from_body(
    signature_record: HeliusTransactionRecord,
    body: dict[str, Any],
    row: PumpFunCreationCensusRow,
    lane: str,
) -> RawTransactionRecord:
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return RawTransactionRecord(
        signature=signature_record.signature,
        slot=body.get("slot", signature_record.slot),
        block_time=body.get("blockTime", signature_record.block_time),
        success=(meta.get("err") is None if meta else signature_record.success),
        address=row.bonding_curve,
        role="pumpfun_bonding_curve_lifecycle_2h",
        token_mint=row.mint,
        fetched_at=datetime.now(timezone.utc),
        raw_json=body,
        metadata_json={
            "source": "pumpfun_lifecycle_collector",
            "lane": lane,
            "creation_signature": row.creation_signature,
            "launch_ts": row.block_time,
            "max_lifecycle_seconds": MAX_LIFECYCLE_SECONDS,
        },
    )


def _raw_record_from_gtfa_body(
    signature: str,
    body: dict[str, Any],
    row: PumpFunCreationCensusRow,
    lane: str,
) -> RawTransactionRecord:
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return RawTransactionRecord(
        signature=signature,
        slot=body.get("slot"),
        block_time=body.get("blockTime"),
        success=(meta.get("err") is None if meta else None),
        address=row.bonding_curve,
        role="pumpfun_bonding_curve_lifecycle_2h",
        token_mint=row.mint,
        fetched_at=datetime.now(timezone.utc),
        raw_json=body,
        metadata_json={
            "source": "pumpfun_lifecycle_collector",
            "collection_method": "address_window",
            "lane": lane,
            "creation_signature": row.creation_signature,
            "launch_ts": row.block_time,
            "max_lifecycle_seconds": MAX_LIFECYCLE_SECONDS,
        },
    )


def _signature_from_body(body: dict[str, Any]) -> str | None:
    signature = body.get("signature")
    if isinstance(signature, str) and signature:
        return signature
    signatures = body.get("transaction", {}).get("signatures", [])
    if isinstance(signatures, list) and signatures and isinstance(signatures[0], str):
        return signatures[0]
    return None


def _dedupe_by_mint(rows: list[PumpFunCreationCensusRow]) -> list[PumpFunCreationCensusRow]:
    by_mint: dict[str, PumpFunCreationCensusRow] = {}
    for row in sorted(rows, key=lambda item: (item.block_time or 0, item.creation_signature)):
        if row.mint:
            by_mint.setdefault(row.mint, row)
    return list(by_mint.values())


def _in_launch_regime(block_time: int) -> bool:
    local = datetime.fromtimestamp(block_time, tz=PACIFIC)
    seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
    return local.weekday() in REGIME_WEEKDAYS and any(
        start <= seconds_since_midnight <= end for start, end in REGIME_WINDOWS
    )
