"""Bounded API recovery for missing aligned P0 creator metadata."""

from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner


READINESS_GO = "creator_api_recovery_ready_for_metadata_repair"
READINESS_PARTIAL = "creator_api_recovery_partial_needs_review"
READINESS_BLOCKED = "creator_api_recovery_blocked"

REPORT_ID = "aligned_p0_creator_api_recovery_v0"
DEFAULT_STRUCTURAL_FEATURES_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "aligned_p0_medium_structural_features.parquet",
)
DEFAULT_OUTPUT_ROOT = data_lake_path()
DEFAULT_STATUS_PATH = Path("theses/ALIGNED_P0_CREATOR_API_RECOVERY_STATUS.md")


def run_aligned_p0_creator_api_recovery(
    *,
    structural_features_path: Path | str = DEFAULT_STRUCTURAL_FEATURES_PATH,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    execute: bool = False,
    max_mints: int = 150,
    pre_launch_buffer_seconds: int = 600,
    post_launch_buffer_seconds: int = 600,
    max_pages_per_mint: int = 1,
    max_transactions_per_mint: int = 25,
    max_total_transactions: int = 5_000,
    request_ceiling: int = 500,
    transaction_workers: int = 8,
    client: Any | None = None,
) -> dict[str, Any]:
    started = time.time()
    paths = _output_paths(Path(output_root))
    _ensure_output_dirs(paths)
    targets = _unknown_creator_targets(structural_features_path, max_mints=max_mints)
    projected_requests = len(targets) * max_pages_per_mint
    base = {
        "report_id": REPORT_ID,
        "executed": execute,
        "started_at": _utc_now(),
        "input_paths": {"structural_features_path": str(structural_features_path)},
        "limits": {
            "max_mints": max_mints,
            "pre_launch_buffer_seconds": pre_launch_buffer_seconds,
            "post_launch_buffer_seconds": post_launch_buffer_seconds,
            "max_pages_per_mint": max_pages_per_mint,
            "max_transactions_per_mint": max_transactions_per_mint,
            "max_total_transactions": max_total_transactions,
            "request_ceiling": request_ceiling,
        },
        "selected_unknown_mints": len(targets),
        "projected_requests": projected_requests,
        "methodology_flags": [
            "research_only",
            "data_quality_only",
            "bounded_api_recovery",
            "explicit_execute_required",
            "not_a_thesis",
            "no_backtest",
            "no_walk_forward_validation",
            "no_paper_trading",
            "no_live_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_trading_logic",
            "neutral_proxy_labels_only",
        ],
        "outputs": {key: str(path) for key, path in paths.items() if key.endswith("_path")},
    }
    _write_target_plan(paths["target_plan_csv_path"], targets)

    if request_ceiling < min(1, len(targets)):
        report = _finalize_report(
            base,
            rows=[],
            requests_used=0,
            transactions_seen=0,
            raw_transactions_preserved=0,
            provider_errors=[],
            warnings=["request_ceiling_too_low_for_selected_mints"],
            readiness=READINESS_BLOCKED,
            started=started,
        )
        _write_outputs(report, [], paths, status_path)
        return report

    if not execute:
        report = _finalize_report(
            base,
            rows=[],
            requests_used=0,
            transactions_seen=0,
            raw_transactions_preserved=0,
            provider_errors=[],
            warnings=["dry_run_only_no_api_calls_made"],
            readiness=READINESS_PARTIAL,
            started=started,
        )
        _write_outputs(report, [], paths, status_path)
        return report

    rpc = client or HeliusHistoricalAdapter.from_env(transaction_workers=transaction_workers)
    scanner = PumpFunCreateScanner()
    requests_used = 0
    transactions_seen = 0
    raw_preserved = 0
    provider_errors: list[str] = []
    rows: list[dict[str, Any]] = []
    raw_signatures = _existing_raw_signatures(paths["raw_jsonl_path"])

    for target in targets:
        if requests_used >= request_ceiling or transactions_seen >= max_total_transactions:
            break
        transactions: list[dict[str, Any]] = []
        pagination_token = None
        stopped_due_ceiling = False
        for _page_index in range(max_pages_per_mint):
            if requests_used >= request_ceiling or transactions_seen >= max_total_transactions:
                stopped_due_ceiling = True
                break
            remaining_mint = max_transactions_per_mint - len(transactions)
            remaining_total = max_total_transactions - transactions_seen
            if remaining_mint <= 0 or remaining_total <= 0:
                stopped_due_ceiling = remaining_total <= 0
                break
            try:
                result = rpc.fetch_transactions_for_address_window(
                    target["mint"],
                    start_time=int(target["launch_ts"]) - pre_launch_buffer_seconds,
                    end_time=int(target["launch_ts"]) + post_launch_buffer_seconds,
                    limit=max(1, min(remaining_mint, remaining_total, 1000)),
                    pagination_token=pagination_token,
                    transaction_details="full",
                    sort_order="asc",
                )
            except Exception as exc:
                provider_errors.append(str(exc))
                break
            requests_used += 1
            page = [_normalize_transaction_for_scanner(tx) for tx in result.get("transactions") or [] if isinstance(tx, dict)]
            for tx in page:
                transactions.append(tx)
                transactions_seen += 1
                signature = _signature(tx)
                if signature and signature not in raw_signatures:
                    _append_raw(paths["raw_jsonl_path"], target, tx)
                    raw_signatures.add(signature)
                    raw_preserved += 1
                if len(transactions) >= max_transactions_per_mint or transactions_seen >= max_total_transactions:
                    stopped_due_ceiling = transactions_seen >= max_total_transactions
                    break
            pagination_token = result.get("pagination_token")
            if not pagination_token or not page:
                break
        rows.append(_recovery_row(target, transactions, scanner, stopped_due_ceiling))
        if provider_errors:
            break

    warnings = _warnings(
        targets=targets,
        rows=rows,
        provider_errors=provider_errors,
        requests_used=requests_used,
        request_ceiling=request_ceiling,
        transactions_seen=transactions_seen,
        max_total_transactions=max_total_transactions,
    )
    readiness = _readiness(rows, provider_errors, warnings)
    report = _finalize_report(
        base,
        rows=rows,
        requests_used=requests_used,
        transactions_seen=transactions_seen,
        raw_transactions_preserved=raw_preserved,
        provider_errors=provider_errors,
        warnings=warnings,
        readiness=readiness,
        started=started,
    )
    _write_outputs(report, rows, paths, status_path)
    return report


def _output_paths(root: Path) -> dict[str, Path]:
    report_dir = root / "data" / "backtests" / "diagnostics" / "reports" / "aligned_p0_creator_api_recovery"
    structural_dir = root / "data" / "backtests" / "structural_enrichment"
    raw_dir = root / "data" / "raw" / "structural_enrichment" / "aligned_p0_creator_api_recovery"
    return {
        "report_dir": report_dir,
        "structural_dir": structural_dir,
        "raw_dir": raw_dir,
        "summary_json_path": report_dir / "aligned_p0_creator_api_recovery_summary.json",
        "summary_md_path": report_dir / "aligned_p0_creator_api_recovery_summary.md",
        "target_plan_csv_path": report_dir / "aligned_p0_creator_api_recovery_targets.csv",
        "jsonl_path": structural_dir / "aligned_p0_creator_api_recovery.jsonl",
        "parquet_path": structural_dir / "aligned_p0_creator_api_recovery.parquet",
        "raw_jsonl_path": raw_dir / "aligned_p0_creator_api_recovery_raw_transactions.jsonl",
    }


def _ensure_output_dirs(paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        if key.endswith("_dir"):
            path.mkdir(parents=True, exist_ok=True)


def _unknown_creator_targets(path: Path | str, *, max_mints: int) -> list[dict[str, Any]]:
    rows = _read_records(path)
    output = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: (_int_or_none(item.get("launch_ts")) or 0, str(item.get("mint") or ""))):
        mint = str(row.get("mint") or "")
        launch_ts = _int_or_none(row.get("launch_ts"))
        if not mint or mint in seen or launch_ts is None or _clean_creator(row.get("creator")):
            continue
        seen.add(mint)
        output.append(
            {
                "launch_id": row.get("launch_id"),
                "mint": mint,
                "launch_ts": launch_ts,
                "launch_time_utc": row.get("launch_time_utc") or _timestamp(launch_ts),
                "launch_date": row.get("launch_date") or _date_from_ts(launch_ts),
                "milestone_tier": row.get("milestone_tier"),
            }
        )
        if len(output) >= max_mints:
            break
    return output


def _recovery_row(target: dict[str, Any], transactions: list[dict[str, Any]], scanner: PumpFunCreateScanner, stopped_due_ceiling: bool) -> dict[str, Any]:
    candidates, _rejected, unknown, direct_count = scanner._extract_candidates(
        transactions,
        remaining_target=1,
        include_low_confidence=False,
        min_confidence="high",
    )
    candidate = next((item for item in candidates if item.token_mint == target["mint"] and item.creator_wallet), None)
    if candidate:
        return {
            **target,
            "creator_deployer": candidate.creator_wallet,
            "creation_signature": candidate.signature,
            "creation_slot": candidate.slot,
            "creation_block_time": candidate.block_time,
            "bonding_curve": candidate.bonding_curve,
            "associated_bonding_curve": candidate.associated_bonding_curve,
            "parser_confidence": candidate.extraction_confidence,
            "creator_recovery_confidence": "high",
            "creator_recovery_source": "helius_mint_window_pumpfun_create",
            "creator_recovery_missing_reason": None,
            "transaction_count_seen": len(transactions),
            "direct_pumpfun_instruction_count": direct_count,
            "unknown_pumpfun_instruction_count": len(unknown),
            "stopped_due_ceiling": stopped_due_ceiling,
            "warning_flags": candidate.warning_flags,
            "metadata_json": {
                "instruction_discriminator": candidate.instruction_discriminator,
                "instruction_type": candidate.metadata_json.get("instruction_type"),
                "source_method": "bounded_mint_window_api_recovery",
            },
        }
    return {
        **target,
        "creator_deployer": None,
        "creation_signature": None,
        "creation_slot": None,
        "creation_block_time": None,
        "bonding_curve": None,
        "associated_bonding_curve": None,
        "parser_confidence": "none",
        "creator_recovery_confidence": "none",
        "creator_recovery_source": "helius_mint_window_pumpfun_create",
        "creator_recovery_missing_reason": "no_verified_create_instruction_found",
        "transaction_count_seen": len(transactions),
        "direct_pumpfun_instruction_count": direct_count,
        "unknown_pumpfun_instruction_count": len(unknown),
        "stopped_due_ceiling": stopped_due_ceiling,
        "warning_flags": [],
        "metadata_json": {"source_method": "bounded_mint_window_api_recovery"},
    }


def _normalize_transaction_for_scanner(tx: dict[str, Any]) -> dict[str, Any]:
    if isinstance(tx.get("transaction"), dict) and isinstance(tx["transaction"].get("message"), dict):
        return tx
    instructions = tx.get("instructions") if isinstance(tx.get("instructions"), list) else []
    if not instructions:
        return tx
    account_keys = tx.get("accountKeys") or tx.get("account_keys") or []
    return {
        **tx,
        "blockTime": tx.get("blockTime", tx.get("timestamp")),
        "transaction": {
            "signatures": [tx.get("signature")] if tx.get("signature") else [],
            "message": {"instructions": instructions, "accountKeys": account_keys},
        },
    }


def _read_records(path: Path | str) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if source.suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get("rows") or payload.get("launch_feature_rows") or payload.get("data")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []
    if source.suffix == ".csv":
        with source.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if source.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(source).to_dict("records")
    return []


def _write_outputs(report: dict[str, Any], rows: list[dict[str, Any]], paths: dict[str, Path], status_path: Path | str) -> None:
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_jsonl(paths["jsonl_path"], rows)
    _write_parquet(rows, paths["parquet_path"])
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report), encoding="utf-8")


def _write_target_plan(path: Path, targets: list[dict[str, Any]]) -> None:
    if not targets:
        _write_csv(path, [])
        return
    _write_csv(path, targets)


def _append_raw(path: Path, target: dict[str, Any], tx: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"mint": target["mint"], "launch_id": target.get("launch_id"), "raw_json": tx}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")


def _existing_raw_signatures(path: Path) -> set[str]:
    signatures: set[str] = set()
    if not path.exists():
        return signatures
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        raw = row.get("raw_json") if isinstance(row, dict) else {}
        signature = _signature(raw) if isinstance(raw, dict) else None
        if signature:
            signatures.add(signature)
    return signatures


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write("\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(path, index=False)
    except Exception:
        path.write_text("", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def _finalize_report(
    base: dict[str, Any],
    *,
    rows: list[dict[str, Any]],
    requests_used: int,
    transactions_seen: int,
    raw_transactions_preserved: int,
    provider_errors: list[str],
    warnings: list[str],
    readiness: str,
    started: float,
) -> dict[str, Any]:
    recovered = [row for row in rows if row.get("creator_deployer")]
    missing = [row for row in rows if not row.get("creator_deployer")]
    return {
        **base,
        "network_calls_made": requests_used,
        "transactions_seen": transactions_seen,
        "raw_transactions_preserved": raw_transactions_preserved,
        "rows_written": len(rows),
        "recovered_creator_count": len(recovered),
        "unknown_or_missing_count": len(missing),
        "recovery_coverage_pct": _pct(len(recovered), len(rows)),
        "missing_reason_counts": dict(Counter(row.get("creator_recovery_missing_reason") or "recovered" for row in rows)),
        "provider_errors": provider_errors,
        "warnings": warnings,
        "readiness_classification": readiness,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _warnings(
    *,
    targets: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    provider_errors: list[str],
    requests_used: int,
    request_ceiling: int,
    transactions_seen: int,
    max_total_transactions: int,
) -> list[str]:
    warnings: list[str] = []
    if provider_errors:
        warnings.append("provider_error")
    if len(rows) < len(targets):
        warnings.append("not_all_targets_processed")
    if requests_used >= request_ceiling:
        warnings.append("request_ceiling_reached")
    if transactions_seen >= max_total_transactions:
        warnings.append("max_total_transactions_reached")
    if rows and not any(row.get("creator_deployer") for row in rows):
        warnings.append("no_creators_recovered")
    return warnings


def _readiness(rows: list[dict[str, Any]], provider_errors: list[str], warnings: list[str]) -> str:
    if provider_errors:
        return READINESS_BLOCKED
    if any(row.get("creator_deployer") for row in rows):
        return READINESS_GO
    if "request_ceiling_reached" in warnings and not rows:
        return READINESS_BLOCKED
    return READINESS_PARTIAL


def _clean_creator(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _signature(tx: dict[str, Any]) -> str | None:
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        return signatures[0]
    signature = tx.get("signature")
    return str(signature) if signature else None


def _timestamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _date_from_ts(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pct(num: int, den: int) -> float:
    return round((num / den * 100.0), 4) if den else 0.0


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Aligned P0 Creator API Recovery",
            "",
            f"- Executed: {report['executed']}",
            f"- Selected unknown mints: {report['selected_unknown_mints']}",
            f"- Projected requests: {report['projected_requests']}",
            f"- Network calls made: {report['network_calls_made']}",
            f"- Transactions seen: {report['transactions_seen']}",
            f"- Creators recovered: {report['recovered_creator_count']}",
            f"- Unknown/missing: {report['unknown_or_missing_count']}",
            f"- Recovery coverage: {report['recovery_coverage_pct']}%",
            f"- Readiness: {report['readiness_classification']}",
            f"- Warnings: {', '.join(report['warnings']) if report['warnings'] else 'none'}",
            "",
            "This is a bounded creator-metadata recovery run only. It does not run theses, validation, backtests, paper trading, or live trading.",
        ]
    )


def _status_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Aligned P0 Creator API Recovery Status",
            "",
            f"- Report ID: {report['report_id']}",
            f"- Executed: {report['executed']}",
            f"- Unknown mints selected: {report['selected_unknown_mints']}",
            f"- Network calls made: {report['network_calls_made']}",
            f"- Creator rows recovered: {report['recovered_creator_count']}",
            f"- Readiness: {report['readiness_classification']}",
            f"- Summary JSON: {report['outputs']['summary_json_path']}",
            f"- Recovery JSONL: {report['outputs']['jsonl_path']}",
            f"- Raw JSONL: {report['outputs']['raw_jsonl_path']}",
            "",
            "Recovered creators are accepted only from deterministic Pump.fun create-instruction parsing.",
        ]
    ) + "\n"
