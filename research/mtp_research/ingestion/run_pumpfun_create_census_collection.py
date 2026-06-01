"""Checkpointed Pump.fun creation-census collection.

This collects accepted create events only. It does not hydrate lifecycle
windows, run backtests, or produce validation claims.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

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
REGIME_WINDOWS = [(6 * 3600, 12 * 3600), (17 * 3600, 22 * 3600)]


def main() -> int:
    args = parse_args()
    existing_rows = load_census_rows(args.output_path)
    if not args.execute:
        print("execute=False")
        print(f"target_launches={args.target_launches}")
        print(f"target_regime_launches={args.target_regime_launches}")
        print(f"batch_size={args.batch_size}")
        print(f"checkpoint_path={args.checkpoint_path}")
        print(f"accepted_launches_existing={_accepted_launch_count(existing_rows)}")
        print(f"accepted_regime_launches_existing={_regime_launch_count(existing_rows)}")
        print("network_calls=0")
        return 0

    adapter = HeliusHistoricalAdapter.from_env()
    scanner = PumpFunCreateScanner(adapter=adapter, program_id=args.program_id)
    checkpoint = _load_checkpoint(args.checkpoint_path)
    rows = existing_rows
    rows_by_mint = {row.mint: row for row in rows if row.accepted and row.mint}
    before = checkpoint.get("cursor_before") or args.cursor_before
    total_signatures = int(checkpoint.get("signatures_seen_total", 0))
    total_hydrated = int(checkpoint.get("transactions_hydrated_total", 0))
    total_direct = int(checkpoint.get("direct_pumpfun_instruction_count", 0))
    batch_index = int(checkpoint.get("batch_index", 0))

    while not _collection_target_met(rows_by_mint, args.target_launches, args.target_regime_launches) and batch_index < args.max_batches:
        report = scanner.scan(
            execute=True,
            max_batches=1,
            signatures_per_batch=args.batch_size,
            hydrate_limit_per_batch=args.batch_size,
            target_create_candidates=args.batch_size,
            max_signatures_total=args.batch_size,
            cursor_before=before,
            min_confidence="high",
            emit_rejected_examples=False,
        )
        for candidate in report.verified_create_candidates:
            if candidate.token_mint and candidate.token_mint not in rows_by_mint:
                rows_by_mint[candidate.token_mint] = PumpFunCreationCensusRow(
                    mint=candidate.token_mint,
                    creator_deployer=candidate.creator_wallet,
                    creation_signature=candidate.signature,
                    slot=candidate.slot,
                    block_time=candidate.block_time,
                    parser_confidence=candidate.extraction_confidence,
                    instruction_type=candidate.metadata_json.get("instruction_type", "create_v2"),
                    source_method="pumpfun_create_census_collection",
                    accepted=True,
                    bonding_curve=candidate.bonding_curve,
                    associated_bonding_curve=candidate.associated_bonding_curve,
                    instruction_index=candidate.instruction_index,
                    instruction_discriminator=candidate.instruction_discriminator,
                    metadata_json={
                        "scanner_report_id": report.report_id,
                        "warning_flags": candidate.warning_flags,
                    },
                )

        batch = report.batches[-1] if report.batches else None
        before = batch.next_cursor_before if batch else None
        total_signatures += report.signatures_seen_total
        total_hydrated += report.transactions_hydrated_total
        total_direct += report.direct_pumpfun_instruction_count
        batch_index += 1
        sorted_rows = sorted(rows_by_mint.values(), key=lambda row: (row.block_time or 0, row.creation_signature))
        write_creation_census(sorted_rows, args.output_path)
        write_creation_census_csv(sorted_rows, args.csv_output_path)
        checkpoint_payload = {
            "batch_index": batch_index,
            "cursor_before": before,
            "accepted_launches": len(rows_by_mint),
            "accepted_regime_launches": _regime_launch_count(list(rows_by_mint.values())),
            "signatures_seen_total": total_signatures,
            "transactions_hydrated_total": total_hydrated,
            "direct_pumpfun_instruction_count": total_direct,
            "last_batch_verified_create_count": len(report.verified_create_candidates),
            "last_batch_unknown_instruction_count": len(report.unknown_pumpfun_instructions),
            "output_path": str(args.output_path),
            "csv_output_path": str(args.csv_output_path),
        }
        _write_checkpoint(args.checkpoint_path, checkpoint_payload)
        print(
            "batch_progress "
            f"batch={batch_index} accepted_launches={len(rows_by_mint)} "
            f"accepted_regime_launches={_regime_launch_count(list(rows_by_mint.values()))} "
            f"last_batch_verified={len(report.verified_create_candidates)} "
            f"signatures_seen_total={total_signatures} transactions_hydrated_total={total_hydrated} "
            f"cursor_before={before}",
            flush=True,
        )
        if not before or report.signatures_seen_total == 0:
            break

    print(f"accepted_launches={len(rows_by_mint)}")
    print(f"accepted_regime_launches={_regime_launch_count(list(rows_by_mint.values()))}")
    print(f"signatures_seen_total={total_signatures}")
    print(f"transactions_hydrated_total={total_hydrated}")
    print(f"direct_pumpfun_instruction_count={total_direct}")
    print(f"output_path={args.output_path}")
    print(f"csv_output_path={args.csv_output_path}")
    print(f"checkpoint_path={args.checkpoint_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Checkpointed Pump.fun create-census collection.")
    parser.add_argument("--program-id", default=PUMP_FUN_PROGRAM_ID)
    parser.add_argument("--target-launches", type=int, default=2500)
    parser.add_argument("--target-regime-launches", type=int)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--max-batches", type=int, default=1000)
    parser.add_argument("--cursor-before")
    parser.add_argument("--output-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--csv-output-path", default="data/normalized/pumpfun_creation_census.csv")
    parser.add_argument("--checkpoint-path", default="data/backtests/diagnostics/reports/pumpfun_create_census_collection_checkpoint.json")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _load_checkpoint(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_checkpoint(path: Path | str, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _accepted_launch_count(rows: list[PumpFunCreationCensusRow]) -> int:
    return len({row.mint for row in rows if row.accepted and row.mint})


def _regime_launch_count(rows: list[PumpFunCreationCensusRow]) -> int:
    return len(
        {
            row.mint
            for row in rows
            if row.accepted
            and row.mint
            and row.block_time is not None
            and _in_launch_regime(int(row.block_time))
        }
    )


def _collection_target_met(
    rows_by_mint: dict[str | None, PumpFunCreationCensusRow],
    target_launches: int,
    target_regime_launches: int | None,
) -> bool:
    rows = list(rows_by_mint.values())
    if target_regime_launches is not None:
        return _regime_launch_count(rows) >= target_regime_launches
    return len(rows_by_mint) >= target_launches


def _in_launch_regime(block_time: int) -> bool:
    local = datetime.fromtimestamp(block_time, tz=PACIFIC)
    seconds_since_midnight = local.hour * 3600 + local.minute * 60 + local.second
    return local.weekday() in REGIME_WEEKDAYS and any(
        start <= seconds_since_midnight <= end for start, end in REGIME_WINDOWS
    )


if __name__ == "__main__":
    raise SystemExit(main())
