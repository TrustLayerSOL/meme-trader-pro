"""Bounded migration/graduation label collection pilot."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.validation.migration_graduation_enrichment_planner import (
    CLASSIFICATION_GO,
    build_migration_graduation_enrichment_dry_run_plan,
)


PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

READINESS_READY = "migration_labels_ready_for_larger_collection"
READINESS_PARTIAL = "migration_labels_partial_needs_parser_repair"
READINESS_BLOCKED = "migration_labels_blocked"

LABEL_FIELDS = [
    "pumpfun_migrate_event_observed",
    "graduated_to_pumpswap",
    "migrated_to_raydium",
    "dex_pair_detected",
    "liquidity_pool_created_after_launch",
    "migration_time",
    "migration_signature",
    "migration_source",
    "migration_confidence",
    "migration_missing_reason",
]

DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_RAW_DIR = data_lake_path("data", "backtests", "migration_graduation", "raw")
DEFAULT_JSONL_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "migration_graduation_pilot_candidates.jsonl"
)
DEFAULT_PARQUET_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "migration_graduation_pilot_candidates.parquet"
)
DEFAULT_CHECKPOINT_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "migration_graduation_collection_checkpoint.json"
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "migration_graduation_collection"
)


def run_migration_graduation_enrichment_collection(
    *,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    execute: bool = False,
    mint_limit: int = 100,
    window: str = "24h",
    max_signature_pages_per_mint: int = 3,
    max_transactions_per_mint: int = 25,
    max_total_transactions: int = 2500,
    request_ceiling: int = 3000,
    hard_stop_projected_requests: int = 5000,
    output_paths: dict[str, Path | str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run a dry-run or explicitly executed capped migration/graduation pilot."""

    started = time.time()
    paths = _resolve_output_paths(output_paths)
    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=candidates_path,
        mint_limit=mint_limit,
        windows=[window],
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
        selection="deterministic",
        dry_run=True,
    )
    selected = plan["selected_mints"]
    planned_high = plan["request_estimate"]["primary_high_projected_requests"]

    base_report = _base_report(
        plan=plan,
        paths=paths,
        execute=execute,
        started=started,
    )

    if not execute:
        report = {
            **base_report,
            "readiness_classification": READINESS_PARTIAL,
            "warnings": ["dry_run_only_no_collection_performed"],
            "exact_execute_command": plan["exact_later_execute_command"],
        }
        _write_reports(report, paths)
        return report

    if planned_high > hard_stop_projected_requests or plan["dry_run_classification"] != CLASSIFICATION_GO:
        failed = plan["stop_go"]["failed_gates"]
        report = {
            **base_report,
            "readiness_classification": READINESS_BLOCKED,
            "warnings": ["projected_request_gate_failed", *failed],
            "requests": {
                **base_report["requests"],
                "stopped_due_ceiling": True,
            },
        }
        _write_reports(report, paths)
        return report

    rpc = client or HeliusHistoricalAdapter.from_env()
    checkpoint = load_collection_checkpoint(paths["checkpoint_path"])
    completed_mints = set(checkpoint.get("completed_mints") or [])
    rows: list[dict[str, Any]] = _dedupe_rows_by_mint(_read_existing_jsonl(paths["jsonl_path"]))
    existing_signatures = _read_existing_raw_signatures(paths["raw_dir"] / "migration_graduation_raw_transactions.jsonl")
    raw_files_written: set[str] = set()
    auth_provider_errors: list[str] = []
    requests_used = int(checkpoint.get("requests_used") or 0)
    signatures_fetched = int(checkpoint.get("signatures_fetched") or 0)
    transactions_fetched = int(checkpoint.get("transactions_fetched") or 0)
    mints_attempted = 0
    mints_completed = 0
    stopped_due_ceiling = False
    window_seconds = _window_seconds(window)

    for mint_row in selected:
        mint = mint_row["mint"]
        if mint in completed_mints:
            continue
        if requests_used >= request_ceiling:
            stopped_due_ceiling = True
            break
        mints_attempted += 1
        try:
            collected = _collect_one_mint(
                rpc=rpc,
                mint_row=mint_row,
                window=window,
                window_seconds=window_seconds,
                max_signature_pages_per_mint=max_signature_pages_per_mint,
                max_transactions_per_mint=max_transactions_per_mint,
                max_total_transactions=max_total_transactions,
                request_ceiling=request_ceiling,
                requests_used=requests_used,
                transactions_fetched_total=transactions_fetched,
                raw_dir=paths["raw_dir"],
                existing_signatures=existing_signatures,
            )
        except Exception as exc:  # fail closed on provider/auth/budget errors
            auth_provider_errors.append(str(exc))
            break

        requests_used = collected["requests_used"]
        signatures_fetched += collected["signatures_fetched"]
        transactions_fetched += collected["transactions_fetched"]
        stopped_due_ceiling = stopped_due_ceiling or collected["stopped_due_ceiling"]
        raw_files_written.update(collected["raw_files_written"])
        rows = [row for row in rows if row.get("mint") != mint]
        rows.append(collected["candidate_row"])
        completed_mints.add(mint)
        mints_completed += 1
        _write_jsonl(paths["jsonl_path"], rows)
        _write_parquet(rows, paths["parquet_path"])
        write_collection_checkpoint(
            paths["checkpoint_path"],
            {
                "completed_mints": sorted(completed_mints),
                "requests_used": requests_used,
                "signatures_fetched": signatures_fetched,
                "transactions_fetched": transactions_fetched,
                "last_mint": mint,
                "updated_at": _utc_now(),
            },
        )
        if stopped_due_ceiling:
            break

    report = _final_report(
        base_report=base_report,
        selected=selected,
        rows=rows,
        mints_attempted=mints_attempted,
        mints_completed=mints_completed,
        signatures_fetched=signatures_fetched,
        transactions_fetched=transactions_fetched,
        requests_used=requests_used,
        stopped_due_ceiling=stopped_due_ceiling,
        raw_files_written=raw_files_written,
        auth_provider_errors=auth_provider_errors,
        started=started,
    )
    _write_reports(report, paths)
    return report


def load_collection_checkpoint(path: Path | str) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def write_collection_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _collect_one_mint(
    *,
    rpc: Any,
    mint_row: dict[str, Any],
    window: str,
    window_seconds: int,
    max_signature_pages_per_mint: int,
    max_transactions_per_mint: int,
    max_total_transactions: int,
    request_ceiling: int,
    requests_used: int,
    transactions_fetched_total: int,
    raw_dir: Path,
    existing_signatures: set[str],
) -> dict[str, Any]:
    start_time = int(mint_row["launch_ts"])
    end_time = start_time + window_seconds
    address = mint_row.get("bonding_curve") or mint_row.get("associated_bonding_curve") or mint_row["mint"]
    before = None
    signatures: list[Any] = []
    stopped_due_ceiling = False

    for _ in range(max_signature_pages_per_mint):
        if requests_used + 1 > request_ceiling:
            stopped_due_ceiling = True
            break
        result = rpc.fetch_signatures_for_address(
            HeliusBackfillRequest(
                address=address,
                token_mint=mint_row["mint"],
                role="migration_graduation_window",
                start_time=start_time,
                end_time=end_time,
                before=before,
                limit=1000,
                include_failed=False,
                metadata_json={"window": window, "launch_id": mint_row.get("launch_id")},
            )
        )
        requests_used += 1
        page_records = list(getattr(result, "records", []))
        signatures.extend([record for record in page_records if _in_window(getattr(record, "block_time", None), start_time, end_time)])
        before = getattr(result, "next_before", None)
        if not before or not page_records:
            break
        if any((getattr(record, "block_time", None) or end_time) < start_time for record in page_records):
            break

    raw_path = raw_dir / "migration_graduation_raw_transactions.jsonl"
    transactions: list[dict[str, Any]] = []
    signatures_seen = {record.signature for record in signatures if getattr(record, "signature", None)}
    for record in signatures[:max_transactions_per_mint]:
        if transactions_fetched_total >= max_total_transactions:
            stopped_due_ceiling = True
            break
        if requests_used + 1 > request_ceiling:
            stopped_due_ceiling = True
            break
        signature = record.signature
        tx = rpc.fetch_transaction(signature)
        requests_used += 1
        if not tx:
            continue
        transactions_fetched_total += 1
        transactions.append({"signature": signature, "block_time": getattr(record, "block_time", None), "raw_json": tx})
        if signature not in existing_signatures:
            _append_raw_transaction(raw_path, mint_row, record, tx)
            existing_signatures.add(signature)

    candidate = _candidate_label_row(mint_row, window, signatures_seen, transactions)
    return {
        "candidate_row": candidate,
        "requests_used": requests_used,
        "signatures_fetched": len(signatures_seen),
        "transactions_fetched": len(transactions),
        "stopped_due_ceiling": stopped_due_ceiling,
        "raw_files_written": [str(raw_path)] if raw_path.exists() else [],
    }


def _candidate_label_row(
    mint_row: dict[str, Any],
    window: str,
    signatures_seen: set[str],
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    detections = [_detect_migration_candidate(item["signature"], item["raw_json"]) for item in transactions]
    detected = [item for item in detections if item["pumpfun_migrate_event_observed"] or item["graduated_to_pumpswap"] or item["migrated_to_raydium"]]
    first = min(detected, key=lambda row: row.get("migration_time") or "") if detected else None
    base = {
        "launch_id": mint_row.get("launch_id"),
        "mint": mint_row.get("mint"),
        "creator": mint_row.get("creator"),
        "launch_time": mint_row.get("launch_time"),
        "launch_ts": mint_row.get("launch_ts"),
        "collection_window": window,
        "signatures_fetched": len(signatures_seen),
        "transactions_fetched": len(transactions),
        "parsed_candidate_fields": sorted(LABEL_FIELDS),
        "errors": [],
    }
    if first:
        return {**base, **first}
    return {
        **base,
        "pumpfun_migrate_event_observed": False,
        "graduated_to_pumpswap": False,
        "migrated_to_raydium": False,
        "dex_pair_detected": False,
        "liquidity_pool_created_after_launch": False,
        "migration_time": None,
        "migration_signature": None,
        "migration_source": None,
        "migration_confidence": 0.0,
        "migration_missing_reason": "not_observed_in_window" if transactions else "no_transactions_in_window",
    }


def _detect_migration_candidate(signature: str, raw_json: dict[str, Any]) -> dict[str, Any]:
    logs = [log.lower() for log in _extract_logs(raw_json)]
    program_ids = _extract_program_ids(raw_json)
    has_pumpfun = PUMPFUN_PROGRAM_ID in program_ids or any(PUMPFUN_PROGRAM_ID.lower() in log for log in logs)
    has_migrate_log = any(_instruction_name(log) in {"migrate", "migratev2"} for log in logs)
    pumpfun_migrate = has_pumpfun and has_migrate_log
    block_time = _raw_block_time(raw_json)
    migration_time = _timestamp(block_time) if block_time is not None and pumpfun_migrate else None
    missing_reason = None
    if pumpfun_migrate and migration_time is None:
        missing_reason = "migration_detected_missing_block_time"
    if not pumpfun_migrate:
        missing_reason = "not_observed_in_window"
    return {
        "pumpfun_migrate_event_observed": pumpfun_migrate,
        "graduated_to_pumpswap": False,
        "migrated_to_raydium": False,
        "dex_pair_detected": False,
        "liquidity_pool_created_after_launch": pumpfun_migrate,
        "migration_time": migration_time,
        "migration_signature": signature if pumpfun_migrate else None,
        "migration_source": "helius_json_rpc_pumpfun_migrate_log" if pumpfun_migrate else None,
        "migration_confidence": 0.9 if pumpfun_migrate and migration_time else 0.0,
        "migration_missing_reason": missing_reason,
    }


def _final_report(
    *,
    base_report: dict[str, Any],
    selected: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    mints_attempted: int,
    mints_completed: int,
    signatures_fetched: int,
    transactions_fetched: int,
    requests_used: int,
    stopped_due_ceiling: bool,
    raw_files_written: set[str],
    auth_provider_errors: list[str],
    started: float,
) -> dict[str, Any]:
    detected_rows = [row for row in rows if row.get("pumpfun_migrate_event_observed") or row.get("graduated_to_pumpswap") or row.get("migrated_to_raydium")]
    missing_reasons = Counter(row.get("migration_missing_reason") or "none" for row in rows)
    confidence = Counter(str(row.get("migration_confidence", 0.0)) for row in rows)
    timestamp_covered = sum(1 for row in detected_rows if row.get("migration_time"))
    readiness = _readiness(
        auth_provider_errors=auth_provider_errors,
        stopped_due_ceiling=stopped_due_ceiling,
        detected_rows=detected_rows,
        timestamp_covered=timestamp_covered,
    )
    return {
        **base_report,
        "readiness_classification": readiness,
        "execution": {**base_report["execution"], "mode": "execute", "elapsed_seconds": round(time.time() - started, 3)},
        "collection": {
            "mints_planned": len(selected),
            "mints_attempted": mints_attempted,
            "mints_completed": mints_completed,
            "creators_covered": len({row.get("creator") for row in rows if row.get("creator")}),
            "signatures_fetched": signatures_fetched,
            "transactions_fetched": transactions_fetched,
            "raw_transactions_preserved": transactions_fetched,
        },
        "requests": {
            **base_report["requests"],
            "requests_used": requests_used,
            "helius_credits_used": None,
            "stopped_due_ceiling": stopped_due_ceiling,
        },
        "provider": {
            "auth_provider_errors": auth_provider_errors,
            "budget_errors": [],
        },
        "labels": {
            "candidate_labels_found": Counter(_label_summary(row) for row in rows),
            "unique_migrated_graduated_mints_detected": len({row.get("mint") for row in detected_rows}),
            "migration_timestamp_coverage": {
                "detected_candidates": len(detected_rows),
                "with_migration_time": timestamp_covered,
                "coverage_pct": _pct(timestamp_covered, len(detected_rows)),
            },
            "confidence_distribution": dict(confidence),
            "missing_reason_counts": dict(missing_reasons),
        },
        "raw_files_written": sorted(raw_files_written),
        "warnings": _warnings(auth_provider_errors, stopped_due_ceiling, detected_rows, timestamp_covered),
    }


def _base_report(*, plan: dict[str, Any], paths: dict[str, Path], execute: bool, started: float) -> dict[str, Any]:
    return {
        "report_id": "migration_graduation_collection_summary_v0",
        "execution": {
            "mode": "execute" if execute else "dry_run",
            "started_at": _timestamp(int(started)),
            "elapsed_seconds": 0.0,
        },
        "scope": {
            "dataset": "all_collected_launches",
            "selected_mints": plan["scope"]["selected_mint_count"],
            "selected_creators": plan["scope"]["selected_creator_count"],
            "window": plan["request_estimate"]["primary_window"],
        },
        "requests": {
            "base_projected_requests": plan["request_estimate"]["primary_base_projected_requests"],
            "high_projected_requests": plan["request_estimate"]["primary_high_projected_requests"],
            "request_ceiling": plan["request_estimate"]["request_ceiling"],
            "request_ceiling_status": plan["request_estimate"]["request_ceiling_status"],
            "requests_used": 0,
            "helius_credits_used": None,
            "stopped_due_ceiling": False,
        },
        "outputs": {key: str(value) for key, value in paths.items()},
        "guardrails": {
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
            "paper_trading_runs": 0,
            "live_trading_runs": 0,
            "trading_logic_added": False,
            "threshold_optimization": False,
            "grid_search": False,
            "ml": False,
        },
    }


def _readiness(
    *,
    auth_provider_errors: list[str],
    stopped_due_ceiling: bool,
    detected_rows: list[dict[str, Any]],
    timestamp_covered: int,
) -> str:
    if auth_provider_errors:
        return READINESS_BLOCKED
    if stopped_due_ceiling:
        return READINESS_PARTIAL
    if detected_rows and timestamp_covered == len(detected_rows):
        return READINESS_READY
    return READINESS_PARTIAL


def _warnings(
    auth_provider_errors: list[str],
    stopped_due_ceiling: bool,
    detected_rows: list[dict[str, Any]],
    timestamp_covered: int,
) -> list[str]:
    warnings: list[str] = []
    if auth_provider_errors:
        warnings.append("provider_or_auth_error")
    if stopped_due_ceiling:
        warnings.append("stopped_due_request_ceiling")
    if not detected_rows:
        warnings.append("no_migration_graduation_labels_detected")
    if detected_rows and timestamp_covered < len(detected_rows):
        warnings.append("migration_detected_without_full_timestamp_coverage")
    return warnings


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> dict[str, Path]:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    json_path = paths["report_dir"] / "migration_graduation_collection_summary.json"
    md_path = paths["report_dir"] / "migration_graduation_collection_summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return {"json_path": json_path, "markdown_path": md_path}


def _markdown(report: dict[str, Any]) -> str:
    collection = report.get("collection", {})
    labels = report.get("labels", {})
    lines = [
        "# Migration / Graduation Collection Summary",
        "",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Execution mode: `{report['execution']['mode']}`",
        f"- Selected mints: `{report['scope']['selected_mints']}`",
        f"- Selected creators: `{report['scope']['selected_creators']}`",
        f"- Window: `{report['scope']['window']}`",
        f"- Requests used: `{report['requests']['requests_used']}`",
        f"- Stopped due ceiling: `{report['requests']['stopped_due_ceiling']}`",
        f"- Mints attempted: `{collection.get('mints_attempted', 0)}`",
        f"- Mints completed: `{collection.get('mints_completed', 0)}`",
        f"- Signatures fetched: `{collection.get('signatures_fetched', 0)}`",
        f"- Transactions fetched: `{collection.get('transactions_fetched', 0)}`",
        f"- Unique migrated/graduated mints detected: `{labels.get('unique_migrated_graduated_mints_detected', 0)}`",
        f"- Migration timestamp coverage: `{labels.get('migration_timestamp_coverage', {})}`",
        f"- Missing reason counts: `{labels.get('missing_reason_counts', {})}`",
        f"- Warnings: `{report.get('warnings', [])}`",
        "",
        "No thesis, backtest, validation, paper trading, live trading, threshold optimization, grid search, or ML workflow was run.",
    ]
    return "\n".join(lines) + "\n"


def _resolve_output_paths(output_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = output_paths or {}
    return {
        "raw_dir": Path(supplied.get("raw_dir", DEFAULT_RAW_DIR)),
        "jsonl_path": Path(supplied.get("jsonl_path", DEFAULT_JSONL_PATH)),
        "parquet_path": Path(supplied.get("parquet_path", DEFAULT_PARQUET_PATH)),
        "checkpoint_path": Path(supplied.get("checkpoint_path", DEFAULT_CHECKPOINT_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _append_raw_transaction(raw_path: Path, mint_row: dict[str, Any], record: Any, tx: dict[str, Any]) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "launch_id": mint_row.get("launch_id"),
        "mint": mint_row.get("mint"),
        "creator": mint_row.get("creator"),
        "launch_time": mint_row.get("launch_time"),
        "signature": getattr(record, "signature", None),
        "block_time": getattr(record, "block_time", None),
        "slot": getattr(record, "slot", None),
        "raw_json": tx,
    }
    with raw_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True))
        f.write("\n")


def _read_existing_raw_signatures(raw_path: Path) -> set[str]:
    if not raw_path.exists():
        return set()
    output = set()
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                signature = json.loads(line).get("signature")
            except json.JSONDecodeError:
                continue
            if signature:
                output.add(signature)
    return output


def _read_existing_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _dedupe_rows_by_mint(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in rows:
        mint = row.get("mint")
        if not mint:
            anonymous.append(row)
            continue
        output[mint] = row
    return [*anonymous, *output.values()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _extract_logs(raw_json: dict[str, Any]) -> list[str]:
    logs = (raw_json.get("meta") or {}).get("logMessages") or []
    return [item for item in logs if isinstance(item, str)]


def _instruction_name(log: str) -> str | None:
    if "instruction:" not in log:
        return None
    return log.split("instruction:", 1)[1].strip().split()[0].lower()


def _extract_program_ids(raw_json: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(raw_json, dict):
        for key, value in raw_json.items():
            if key in {"programId", "program_id", "pubkey"} and isinstance(value, str):
                output.add(value)
            output.update(_extract_program_ids(value))
    elif isinstance(raw_json, list):
        for item in raw_json:
            output.update(_extract_program_ids(item))
    return output


def _raw_block_time(raw_json: dict[str, Any]) -> int | None:
    value = raw_json.get("blockTime") or raw_json.get("timestamp")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _in_window(value: int | None, start_time: int, end_time: int) -> bool:
    return value is not None and start_time <= int(value) <= end_time


def _window_seconds(window: str) -> int:
    if window == "24h":
        return 24 * 60 * 60
    if window == "72h":
        return 72 * 60 * 60
    if window == "7d":
        return 7 * 24 * 60 * 60
    raise ValueError("window must be one of 24h, 72h, 7d")


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _label_summary(row: dict[str, Any]) -> str:
    if row.get("pumpfun_migrate_event_observed"):
        return "pumpfun_migrate_event_observed"
    if row.get("graduated_to_pumpswap"):
        return "graduated_to_pumpswap"
    if row.get("migrated_to_raydium"):
        return "migrated_to_raydium"
    return "not_observed"
