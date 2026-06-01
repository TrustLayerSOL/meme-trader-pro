"""Fast Pump.fun regime census collection using Helius getTransactionsForAddress."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    load_census_rows,
    write_creation_census,
    write_creation_census_csv,
)
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


PACIFIC = ZoneInfo("America/Los_Angeles")
REGIME_WEEKDAYS = {0, 1, 2}
REGIME_TIME_BLOCKS = [(time(6, 0), time(12, 0)), (time(17, 0), time(22, 0))]


def regime_windows(*, start_date: date, end_date: date) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    current = start_date
    while current <= end_date:
        if current.weekday() in REGIME_WEEKDAYS:
            for start_time, end_time in REGIME_TIME_BLOCKS:
                windows.append(
                    (
                        datetime.combine(current, start_time, tzinfo=PACIFIC),
                        datetime.combine(current, end_time, tzinfo=PACIFIC),
                    )
                )
        current = date.fromordinal(current.toordinal() + 1)
    return windows


def collect_pumpfun_regime_census_with_gtfa(
    *,
    output_path: Path | str = "data/normalized/pumpfun_creation_census.jsonl",
    csv_output_path: Path | str = "data/normalized/pumpfun_creation_census.csv",
    checkpoint_path: Path | str = "data/backtests/diagnostics/reports/pumpfun_gtfa_regime_census_checkpoint.json",
    start_date: date,
    end_date: date,
    target_regime_launches: int = 1500,
    page_limit: int = 1000,
    max_pages_per_window: int = 100,
    execute: bool = False,
    adapter: HeliusHistoricalAdapter | None = None,
    program_id: str = PUMP_FUN_PROGRAM_ID,
) -> dict[str, Any]:
    windows = regime_windows(start_date=start_date, end_date=end_date)
    existing_rows = load_census_rows(output_path)
    rows_by_mint = {row.mint: row for row in existing_rows if row.accepted and row.mint}
    summary: dict[str, Any] = {
        "method": "helius_getTransactionsForAddress",
        "program_id": program_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "window_count": len(windows),
        "target_regime_launches": target_regime_launches,
        "accepted_launches_existing": len(rows_by_mint),
        "accepted_regime_launches_existing": _regime_launch_count(rows_by_mint.values()),
        "page_limit": page_limit,
        "max_pages_per_window": max_pages_per_window,
        "estimated_request_cap": len(windows) * max_pages_per_window,
        "network_calls": 0,
        "transactions_seen": 0,
        "accepted_regime_launches": _regime_launch_count(rows_by_mint.values()),
        "output_path": str(output_path),
        "csv_output_path": str(csv_output_path),
        "checkpoint_path": str(checkpoint_path),
        "warning_flags": [],
    }
    if not execute:
        return summary

    adapter = adapter or HeliusHistoricalAdapter.from_env()
    scanner = PumpFunCreateScanner(adapter=adapter, program_id=program_id)
    checkpoint = _load_checkpoint(checkpoint_path)
    completed_windows = set(checkpoint.get("completed_windows", []))
    window_summaries = []

    for window_start, window_end in windows:
        window_key = f"{window_start.isoformat()}_{window_end.isoformat()}"
        if window_key in completed_windows:
            continue
        pagination_token = None
        pages = 0
        window_seen = 0
        window_added = 0
        while pages < max_pages_per_window:
            result = adapter.fetch_transactions_for_address_window(
                program_id,
                start_time=int(window_start.timestamp()),
                end_time=int(window_end.timestamp()),
                limit=page_limit,
                pagination_token=pagination_token,
            )
            summary["network_calls"] += 1
            pages += 1
            transactions = result["transactions"]
            window_seen += len(transactions)
            summary["transactions_seen"] += len(transactions)
            candidates, _rejected, _unknown, _direct = scanner._extract_candidates(
                transactions,
                target_regime_launches - _regime_launch_count(rows_by_mint.values()),
                include_low_confidence=False,
                min_confidence="high",
            )
            for candidate in candidates:
                if candidate.token_mint and candidate.token_mint not in rows_by_mint:
                    rows_by_mint[candidate.token_mint] = PumpFunCreationCensusRow(
                        mint=candidate.token_mint,
                        creator_deployer=candidate.creator_wallet,
                        creation_signature=candidate.signature,
                        slot=candidate.slot,
                        block_time=candidate.block_time,
                        parser_confidence=candidate.extraction_confidence,
                        instruction_type=candidate.metadata_json.get("instruction_type", "create_v2"),
                        source_method="pumpfun_gtfa_regime_census_collection",
                        accepted=True,
                        bonding_curve=candidate.bonding_curve,
                        associated_bonding_curve=candidate.associated_bonding_curve,
                        instruction_index=candidate.instruction_index,
                        instruction_discriminator=candidate.instruction_discriminator,
                        metadata_json={"warning_flags": candidate.warning_flags},
                    )
                    window_added += 1
            _write_outputs(rows_by_mint.values(), output_path, csv_output_path)
            summary["accepted_regime_launches"] = _regime_launch_count(rows_by_mint.values())
            pagination_token = result.get("pagination_token")
            if summary["accepted_regime_launches"] >= target_regime_launches:
                break
            if not pagination_token or not transactions:
                break
        completed_windows.add(window_key)
        window_summaries.append(
            {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "pages": pages,
                "transactions_seen": window_seen,
                "accepted_added": window_added,
                "accepted_regime_launches": summary["accepted_regime_launches"],
            }
        )
        _write_checkpoint(
            checkpoint_path,
            {
                **summary,
                "completed_windows": sorted(completed_windows),
                "window_summaries": window_summaries,
            },
        )
        print(
            "window_progress "
            f"window_start={window_start.isoformat()} pages={pages} "
            f"transactions_seen={window_seen} accepted_added={window_added} "
            f"accepted_regime_launches={summary['accepted_regime_launches']}",
            flush=True,
        )
        if summary["accepted_regime_launches"] >= target_regime_launches:
            break

    summary["accepted_launches_total"] = len(rows_by_mint)
    return summary


def _write_outputs(
    rows: Iterable[PumpFunCreationCensusRow],
    output_path: Path | str,
    csv_output_path: Path | str,
) -> None:
    sorted_rows = sorted(rows, key=lambda row: (row.block_time or 0, row.creation_signature))
    write_creation_census(sorted_rows, output_path)
    write_creation_census_csv(sorted_rows, csv_output_path)


def _regime_launch_count(rows: Iterable[PumpFunCreationCensusRow]) -> int:
    return len({row.mint for row in rows if row.accepted and row.mint and row.block_time and _in_regime(row.block_time)})


def _in_regime(block_time: int) -> bool:
    local = datetime.fromtimestamp(block_time, tz=PACIFIC)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    return local.weekday() in REGIME_WEEKDAYS and any(
        start.hour * 3600 + start.minute * 60 <= seconds <= end.hour * 3600 + end.minute * 60
        for start, end in REGIME_TIME_BLOCKS
    )


def _load_checkpoint(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
