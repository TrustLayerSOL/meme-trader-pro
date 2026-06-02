"""Parallel date-sharded acquisition pilot for historical launch expansion."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from research.mtp_research.data_paths import data_lake_path
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
REGIME_TIME_BLOCKS = [(dt_time(6, 0), dt_time(12, 0)), (dt_time(17, 0), dt_time(22, 0))]
READINESS_READY = "parallel_acquisition_ready_for_execute"
READINESS_EXECUTED = "parallel_acquisition_pilot_executed"
READINESS_BLOCKED = "parallel_acquisition_blocked"

DEFAULT_EXISTING_CENSUS_PATH = data_lake_path("data", "normalized", "pumpfun_creation_census.jsonl")
DEFAULT_CENSUS_PATH = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "pumpfun_creation_census_parallel_pilot.jsonl"
)
DEFAULT_NEW_CENSUS_PATH = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "pumpfun_creation_census_parallel_pilot_new_only.jsonl"
)
DEFAULT_CSV_PATH = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "pumpfun_creation_census_parallel_pilot.csv"
)
DEFAULT_NEW_CSV_PATH = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "pumpfun_creation_census_parallel_pilot_new_only.csv"
)
DEFAULT_RAW_DIR = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "raw_creation_shards"
)
DEFAULT_CHECKPOINT_PATH = data_lake_path(
    "data", "backtests", "explosive_runner_expanded", "parallel_pilot", "parallel_acquisition_checkpoint.json"
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "historical_date_expansion_parallel_pilot"
)


def build_parallel_historical_date_acquisition_plan(
    *,
    existing_census_path: Path | str = DEFAULT_EXISTING_CENSUS_PATH,
    target_dates: list[str] | None = None,
    target_date_count: int = 6,
    max_pages_per_window: int = 2,
    request_ceiling: int = 50,
    hard_stop_projected_requests: int = 100,
    page_limit: int = 1000,
) -> dict[str, Any]:
    existing_rows = load_census_rows(existing_census_path)
    existing_dates = _existing_pt_dates(existing_rows)
    selected_dates = target_dates or _select_prior_regime_dates(existing_dates, target_date_count)
    window_count = len(selected_dates) * len(REGIME_TIME_BLOCKS)
    projected_requests = window_count * max_pages_per_window
    failed_gates = []
    if projected_requests > request_ceiling:
        failed_gates.append("projected_requests_above_request_ceiling")
    if projected_requests > hard_stop_projected_requests:
        failed_gates.append("projected_requests_above_hard_stop")
    if not selected_dates:
        failed_gates.append("no_target_dates_selected")
    return {
        "plan_id": "parallel_historical_date_acquisition_pilot_v0",
        "method": "parallel_date_sharded_helius_gtfa_creation_census",
        "program_id": PUMP_FUN_PROGRAM_ID,
        "existing_dates": existing_dates,
        "selected_dates": selected_dates,
        "target_gap": {
            "additional_20k_trigger_dates_needed": 27,
            "additional_20k_trigger_rows_needed": 578,
        },
        "requests": {
            "window_count": window_count,
            "page_limit": page_limit,
            "max_pages_per_window": max_pages_per_window,
            "projected_requests": projected_requests,
            "request_ceiling": request_ceiling,
            "hard_stop_projected_requests": hard_stop_projected_requests,
            "request_ceiling_status": "within_ceiling" if projected_requests <= request_ceiling else "above_ceiling",
        },
        "stop_go": {
            "failed_gates": failed_gates,
            "classification": READINESS_READY if not failed_gates else READINESS_BLOCKED,
        },
        "guardrails": _guardrails(),
    }


def run_parallel_historical_date_acquisition(
    *,
    existing_census_path: Path | str = DEFAULT_EXISTING_CENSUS_PATH,
    output_paths: dict[str, Path | str] | None = None,
    target_dates: list[str] | None = None,
    target_date_count: int = 6,
    max_pages_per_window: int = 2,
    page_limit: int = 1000,
    request_ceiling: int = 50,
    hard_stop_projected_requests: int = 100,
    execute: bool = False,
    adapter: Any | None = None,
    shard_workers: int = 4,
) -> dict[str, Any]:
    started = time.time()
    paths = _resolve_output_paths(output_paths)
    plan = build_parallel_historical_date_acquisition_plan(
        existing_census_path=existing_census_path,
        target_dates=target_dates,
        target_date_count=target_date_count,
        max_pages_per_window=max_pages_per_window,
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
        page_limit=page_limit,
    )
    base_report = _base_report(plan, paths, execute=execute, started=started, shard_workers=shard_workers)
    if not execute:
        report = {
            **base_report,
            "readiness_classification": plan["stop_go"]["classification"],
            "warnings": ["dry_run_only_no_collection_performed"],
            "recommended_next_command": _recommended_lifecycle_command(paths["new_census_path"]),
        }
        _write_reports(report, paths)
        return report
    if plan["stop_go"]["failed_gates"]:
        report = {
            **base_report,
            "readiness_classification": READINESS_BLOCKED,
            "warnings": ["projected_request_gate_failed", *plan["stop_go"]["failed_gates"]],
            "recommended_next_command": "lower target dates or max pages per window before executing",
        }
        _write_reports(report, paths)
        return report

    rpc = adapter or HeliusHistoricalAdapter.from_env()
    checkpoint = _load_checkpoint(paths["checkpoint_path"])
    completed_dates = set(checkpoint.get("completed_dates") or [])
    selected_dates = [item for item in plan["selected_dates"] if item not in completed_dates]
    shard_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, shard_workers)) as executor:
        futures = [
            executor.submit(
                _collect_date_shard,
                target_date=item,
                adapter=rpc,
                paths=paths,
                max_pages_per_window=max_pages_per_window,
                page_limit=page_limit,
            )
            for item in selected_dates
        ]
        for future in as_completed(futures):
            result = future.result()
            shard_results.append(result)
            completed_dates.add(result["date"])
            _write_checkpoint(
                paths["checkpoint_path"],
                {
                    "completed_dates": sorted(completed_dates),
                    "updated_at": _utc_now(),
                    "last_result": result,
                },
            )
            print(
                "date_shard_progress "
                f"date={result['date']} "
                f"requests_used={result['requests_used']} "
                f"transactions_seen={result['transactions_seen']} "
                f"accepted_added={result['accepted_added']} "
                f"completed_dates={len(completed_dates)}",
                flush=True,
            )

    existing_rows = load_census_rows(existing_census_path)
    new_rows = [row for result in shard_results for row in result["census_rows"]]
    merged_rows = _merge_rows(existing_rows, new_rows)
    write_creation_census(merged_rows, paths["census_path"])
    write_creation_census_csv(merged_rows, paths["csv_path"])
    write_creation_census(_merge_rows([], new_rows), paths["new_census_path"])
    write_creation_census_csv(_merge_rows([], new_rows), paths["new_csv_path"])
    report = _final_report(base_report, shard_results, merged_rows, started, paths)
    _write_reports(report, paths)
    return report


def _collect_date_shard(
    *,
    target_date: str,
    adapter: Any,
    paths: dict[str, Path],
    max_pages_per_window: int,
    page_limit: int,
) -> dict[str, Any]:
    scanner = PumpFunCreateScanner(adapter=adapter)
    raw_path = paths["raw_dir"] / f"date={target_date}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    date_obj = date.fromisoformat(target_date)
    rows_by_mint: dict[str, PumpFunCreationCensusRow] = {}
    requests_used = 0
    transactions_seen = 0
    pages_seen = 0
    windows = []
    raw_signatures = _read_raw_signatures(raw_path)
    for start_local, end_local in _windows_for_date(date_obj):
        pagination_token = None
        window_transactions = 0
        window_added = 0
        for _ in range(max_pages_per_window):
            result = adapter.fetch_transactions_for_address_window(
                PUMP_FUN_PROGRAM_ID,
                start_time=int(start_local.timestamp()),
                end_time=int(end_local.timestamp()),
                limit=page_limit,
                pagination_token=pagination_token,
                transaction_details="full",
                sort_order="asc",
            )
            requests_used += 1
            pages_seen += 1
            transactions = list(result.get("transactions") or [])
            transactions_seen += len(transactions)
            window_transactions += len(transactions)
            _append_raw_transactions(raw_path, target_date, transactions, raw_signatures)
            candidates, _rejected, _unknown, _direct = scanner._extract_candidates(
                transactions,
                remaining_target=100_000,
                include_low_confidence=False,
                min_confidence="high",
            )
            for candidate in candidates:
                if not candidate.token_mint or candidate.token_mint in rows_by_mint:
                    continue
                rows_by_mint[candidate.token_mint] = PumpFunCreationCensusRow(
                    mint=candidate.token_mint,
                    creator_deployer=candidate.creator_wallet,
                    creation_signature=candidate.signature or "",
                    slot=candidate.slot,
                    block_time=candidate.block_time,
                    parser_confidence=candidate.extraction_confidence,
                    instruction_type=candidate.metadata_json.get("instruction_type", "create_v2"),
                    source_method="parallel_historical_date_acquisition_gtfa",
                    accepted=True,
                    bonding_curve=candidate.bonding_curve,
                    associated_bonding_curve=candidate.associated_bonding_curve,
                    instruction_index=candidate.instruction_index,
                    instruction_discriminator=candidate.instruction_discriminator,
                    metadata_json={"warning_flags": candidate.warning_flags, "target_date": target_date},
                )
                window_added += 1
            pagination_token = result.get("pagination_token")
            if not pagination_token or not transactions:
                break
        windows.append(
            {
                "window_start": start_local.isoformat(),
                "window_end": end_local.isoformat(),
                "transactions_seen": window_transactions,
                "accepted_added": window_added,
            }
        )
    return {
        "date": target_date,
        "requests_used": requests_used,
        "pages_seen": pages_seen,
        "transactions_seen": transactions_seen,
        "accepted_added": len(rows_by_mint),
        "raw_path": str(raw_path),
        "windows": windows,
        "census_rows": list(rows_by_mint.values()),
    }


def _base_report(
    plan: dict[str, Any],
    paths: dict[str, Path],
    *,
    execute: bool,
    started: float,
    shard_workers: int,
) -> dict[str, Any]:
    return {
        **plan,
        "execution": {
            "mode": "execute" if execute else "dry_run",
            "network_calls_made": 0 if not execute else None,
            "shard_workers": max(1, shard_workers),
            "started_at": _utc_now(),
            "elapsed_seconds": round(time.time() - started, 3),
        },
        "outputs": {key: str(value) for key, value in paths.items()},
    }


def _final_report(
    base_report: dict[str, Any],
    shard_results: list[dict[str, Any]],
    merged_rows: list[PumpFunCreationCensusRow],
    started: float,
    paths: dict[str, Path],
) -> dict[str, Any]:
    added_rows = [row for result in shard_results for row in result["census_rows"]]
    return {
        **base_report,
        "readiness_classification": READINESS_EXECUTED,
        "execution": {
            **base_report["execution"],
            "mode": "execute",
            "network_calls_made": sum(result["requests_used"] for result in shard_results),
            "elapsed_seconds": round(time.time() - started, 3),
        },
        "requests": {
            **base_report["requests"],
            "requests_used": sum(result["requests_used"] for result in shard_results),
        },
        "collection": {
            "dates_attempted": len(shard_results),
            "dates_completed": len(shard_results),
            "transactions_seen": sum(result["transactions_seen"] for result in shard_results),
            "accepted_added": len({row.mint for row in added_rows if row.mint}),
            "merged_census_rows": len(merged_rows),
            "raw_shard_files": [result["raw_path"] for result in shard_results],
        },
        "date_shards": [_json_safe_result(result) for result in shard_results],
        "warnings": [],
        "recommended_next_command": _recommended_lifecycle_command(paths["new_census_path"]),
    }


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    report_dir = paths["report_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "parallel_historical_date_acquisition_summary.json"
    md_path = report_dir / "parallel_historical_date_acquisition_summary.md"
    json_path.write_text(json.dumps(_json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown_report(report), encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    collection = report.get("collection", {})
    requests = report.get("requests", {})
    return "\n".join(
        [
            "# Parallel Historical Date Acquisition Pilot",
            "",
            "This is a bounded data-acquisition report only. It does not run theses, validation, paper/live trading, or strategy logic.",
            "",
            f"- Readiness: `{report.get('readiness_classification')}`",
            f"- Mode: `{report.get('execution', {}).get('mode')}`",
            f"- Selected dates: `{report.get('selected_dates')}`",
            f"- Projected requests: `{requests.get('projected_requests')}`",
            f"- Requests used: `{requests.get('requests_used', 0)}`",
            f"- Dates completed: `{collection.get('dates_completed', 0)}`",
            f"- Transactions seen: `{collection.get('transactions_seen', 0)}`",
            f"- Accepted launches added: `{collection.get('accepted_added', 0)}`",
            f"- Recommended next command: `{report.get('recommended_next_command')}`",
        ]
    )


def _resolve_output_paths(paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = paths or {}
    return {
        "census_path": Path(supplied.get("census_path", DEFAULT_CENSUS_PATH)),
        "new_census_path": Path(supplied.get("new_census_path", DEFAULT_NEW_CENSUS_PATH)),
        "csv_path": Path(supplied.get("csv_path", DEFAULT_CSV_PATH)),
        "new_csv_path": Path(supplied.get("new_csv_path", DEFAULT_NEW_CSV_PATH)),
        "raw_dir": Path(supplied.get("raw_dir", DEFAULT_RAW_DIR)),
        "checkpoint_path": Path(supplied.get("checkpoint_path", DEFAULT_CHECKPOINT_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _existing_pt_dates(rows: list[PumpFunCreationCensusRow]) -> list[str]:
    return sorted(
        {
            datetime.fromtimestamp(int(row.block_time), tz=PACIFIC).date().isoformat()
            for row in rows
            if row.accepted and row.block_time
        }
    )


def _select_prior_regime_dates(existing_dates: list[str], count: int) -> list[str]:
    if count <= 0:
        return []
    anchor = min(date.fromisoformat(item) for item in existing_dates) if existing_dates else datetime.now(PACIFIC).date()
    selected = []
    cursor = date.fromordinal(anchor.toordinal() - 7)
    existing = set(existing_dates)
    while len(selected) < count:
        week_start = date.fromordinal(cursor.toordinal() - cursor.weekday())
        for offset in sorted(REGIME_WEEKDAYS):
            candidate = date.fromordinal(week_start.toordinal() + offset)
            if candidate >= anchor or candidate.isoformat() in existing:
                continue
            selected.append(candidate.isoformat())
            if len(selected) >= count:
                break
        cursor = date.fromordinal(week_start.toordinal() - 1)
    return selected


def _windows_for_date(value: date) -> list[tuple[datetime, datetime]]:
    if value.weekday() not in REGIME_WEEKDAYS:
        return []
    return [
        (
            datetime.combine(value, start_time, tzinfo=PACIFIC),
            datetime.combine(value, end_time, tzinfo=PACIFIC),
        )
        for start_time, end_time in REGIME_TIME_BLOCKS
    ]


def _merge_rows(
    existing_rows: list[PumpFunCreationCensusRow],
    new_rows: list[PumpFunCreationCensusRow],
) -> list[PumpFunCreationCensusRow]:
    by_mint: dict[str, PumpFunCreationCensusRow] = {}
    for row in sorted([*existing_rows, *new_rows], key=lambda item: (item.block_time or 0, item.creation_signature)):
        if row.accepted and row.mint:
            by_mint.setdefault(row.mint, row)
    return list(by_mint.values())


def _read_raw_signatures(path: Path) -> set[str]:
    if not path.exists():
        return set()
    signatures = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                signature = json.loads(line).get("signature")
            except json.JSONDecodeError:
                continue
            if signature:
                signatures.add(str(signature))
    return signatures


def _append_raw_transactions(path: Path, target_date: str, transactions: list[dict[str, Any]], known_signatures: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for tx in transactions:
            signature = _signature(tx)
            if not signature or signature in known_signatures:
                continue
            f.write(json.dumps({"signature": signature, "target_date": target_date, "raw_json": tx}, sort_keys=True))
            f.write("\n")
            known_signatures.add(signature)


def _signature(tx: dict[str, Any]) -> str | None:
    signature = tx.get("signature")
    if isinstance(signature, str) and signature:
        return signature
    signatures = ((tx.get("transaction") or {}).get("signatures") or [])
    return signatures[0] if signatures and isinstance(signatures[0], str) else None


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def _recommended_lifecycle_command(census_path: Path) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.ingestion.run_pumpfun_lifecycle_collection "
        f"--census-path {census_path} "
        "--raw-path /Volumes/ORICO/MemeTraderPro/data/raw/pumpfun_lifecycle_2h_parallel_pilot.jsonl "
        "--lane existing --collection-method address_window --address-window-workers 16 "
        "--address-window-batch-size 100 --target-launches 500 --max-transactions-per-launch 100 --execute"
    )


def _guardrails() -> list[str]:
    return [
        "data_acquisition_only",
        "no_thesis_rerun",
        "no_validation_run",
        "no_backtest",
        "no_live_trading",
        "no_paper_trading",
        "no_wallet_execution",
        "no_order_routing",
        "no_strategy_generation",
        "no_profitability_claims",
        "fdv_proxy_only_until_true_market_cap_exists",
    ]


def _json_safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "census_rows"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return value


def _utc_now() -> str:
    return datetime.now(tz=ZoneInfo("UTC")).isoformat()
