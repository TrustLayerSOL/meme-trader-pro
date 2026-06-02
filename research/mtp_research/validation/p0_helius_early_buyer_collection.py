"""Bounded P0 early-buyer wallet-history collection pilot."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter


READINESS_READY = "early_buyer_history_ready_for_review"
READINESS_PARTIAL = "early_buyer_history_partial_needs_review"
READINESS_BLOCKED = "early_buyer_history_blocked"

DEFAULT_TARGET_CSV_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_helius_planners",
    "early_buyer_wallet_history_targets.csv",
)
DEFAULT_RAW_PATH = data_lake_path(
    "data",
    "raw",
    "structural_enrichment",
    "early_buyer_wallet_history_pilot",
    "early_buyer_wallet_history_raw_transactions.jsonl",
)
DEFAULT_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "early_buyer_wallet_history_pilot.jsonl",
)
DEFAULT_PARQUET_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "early_buyer_wallet_history_pilot.parquet",
)
DEFAULT_CHECKPOINT_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "checkpoints",
    "early_buyer_wallet_history_pilot.json",
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_early_buyer_wallet_history_pilot",
)


def run_p0_early_buyer_wallet_history_collection(
    *,
    target_csv_path: Path | str = DEFAULT_TARGET_CSV_PATH,
    execute: bool = False,
    max_wallets: int = 1_000,
    lookback_days: int = 30,
    max_pages_per_wallet: int = 1,
    max_transactions_per_wallet: int = 25,
    max_total_transactions: int = 25_000,
    request_ceiling: int = 25_000,
    output_paths: dict[str, Path | str] | None = None,
    client: Any | None = None,
    transaction_workers: int = 16,
) -> dict[str, Any]:
    started = time.time()
    paths = _resolve_output_paths(output_paths)
    targets = _select_targets(_read_target_csv(target_csv_path), max_wallets=max_wallets)
    base = _base_report(
        target_csv_path=target_csv_path,
        targets=targets,
        execute=execute,
        lookback_days=lookback_days,
        request_ceiling=request_ceiling,
        max_total_transactions=max_total_transactions,
        paths=paths,
        started=started,
    )
    if not execute:
        report = {
            **base,
            "readiness_classification": READINESS_PARTIAL,
            "warnings": ["dry_run_only_no_collection_performed"],
        }
        _write_reports(report, paths)
        return report

    rpc = client or HeliusHistoricalAdapter.from_env(transaction_workers=transaction_workers)
    checkpoint = load_early_buyer_collection_checkpoint(paths["checkpoint_path"])
    completed_wallets = set(checkpoint.get("completed_wallets") or [])
    requests_used = int(checkpoint.get("requests_used") or 0)
    transactions_fetched = int(checkpoint.get("transactions_fetched") or 0)
    rows = _dedupe_rows_by_wallet(_read_existing_jsonl(paths["jsonl_path"]))
    raw_signatures = _read_existing_raw_signatures(paths["raw_path"])
    provider_errors: list[str] = []
    stopped_due_ceiling = False

    for target in targets:
        wallet = target["wallet"]
        if wallet in completed_wallets:
            continue
        if requests_used >= request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        try:
            collected = _collect_wallet_history(
                rpc=rpc,
                target=target,
                lookback_days=lookback_days,
                max_pages=max_pages_per_wallet,
                max_transactions=max_transactions_per_wallet,
                max_total_transactions=max_total_transactions,
                request_ceiling=request_ceiling,
                requests_used=requests_used,
                transactions_fetched=transactions_fetched,
            )
        except Exception as exc:
            provider_errors.append(str(exc))
            break

        requests_used = collected["requests_used"]
        transactions_fetched = collected["transactions_fetched"]
        stopped_due_ceiling = stopped_due_ceiling or collected["stopped_due_ceiling"]
        for tx in collected["transactions"]:
            signature = _transaction_signature(tx)
            if signature and signature not in raw_signatures:
                _append_raw_transaction(paths["raw_path"], target, tx)
                raw_signatures.add(signature)

        rows_by_wallet = {row["wallet"]: row for row in rows}
        rows_by_wallet[wallet] = _history_row(target, collected["transactions"], lookback_days)
        rows = list(rows_by_wallet.values())
        completed_wallets.add(wallet)
        _flush_outputs(rows, paths)
        write_early_buyer_collection_checkpoint(
            paths["checkpoint_path"],
            {
                "completed_wallets": sorted(completed_wallets),
                "requests_used": requests_used,
                "transactions_fetched": transactions_fetched,
                "last_wallet": wallet,
                "updated_at": _timestamp(int(time.time())),
            },
        )
        if stopped_due_ceiling:
            break

    _flush_outputs(rows, paths)
    report = _final_report(
        base_report=base,
        rows=rows,
        targets=targets,
        requests_used=requests_used,
        transactions_fetched=transactions_fetched,
        raw_transactions_preserved=len(raw_signatures),
        stopped_due_ceiling=stopped_due_ceiling,
        provider_errors=provider_errors,
        started=started,
    )
    _write_reports(report, paths)
    return report


def load_early_buyer_collection_checkpoint(path: Path | str) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def write_early_buyer_collection_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _collect_wallet_history(
    *,
    rpc: Any,
    target: dict[str, Any],
    lookback_days: int,
    max_pages: int,
    max_transactions: int,
    max_total_transactions: int,
    request_ceiling: int,
    requests_used: int,
    transactions_fetched: int,
) -> dict[str, Any]:
    first_seen = int(target["first_seen_in_launch_time"])
    start_time = first_seen - lookback_days * 86_400
    end_time = max(start_time, first_seen - 1)
    transactions: list[dict[str, Any]] = []
    pagination_token = None
    stopped_due_ceiling = False
    for _ in range(max_pages):
        if requests_used + 1 > request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        remaining_wallet = max_transactions - len(transactions)
        remaining_total = max_total_transactions - transactions_fetched
        if remaining_wallet <= 0 or remaining_total <= 0:
            stopped_due_ceiling = remaining_total <= 0
            break
        result = rpc.fetch_transactions_for_address_window(
            target["wallet"],
            start_time=start_time,
            end_time=end_time,
            limit=max(1, min(remaining_wallet, remaining_total, 1000)),
            pagination_token=pagination_token,
            transaction_details="full",
            sort_order="desc",
        )
        requests_used += 1
        page = list(result.get("transactions") or [])
        for tx in page:
            block_time = _block_time(tx)
            if block_time is not None and not (start_time <= block_time <= end_time):
                continue
            transactions.append(tx)
            transactions_fetched += 1
            if len(transactions) >= max_transactions or transactions_fetched >= max_total_transactions:
                stopped_due_ceiling = transactions_fetched >= max_total_transactions
                break
        pagination_token = result.get("pagination_token")
        if not pagination_token or not page:
            break
    return {
        "transactions": transactions,
        "requests_used": requests_used,
        "transactions_fetched": transactions_fetched,
        "stopped_due_ceiling": stopped_due_ceiling,
    }


def _history_row(target: dict[str, Any], transactions: list[dict[str, Any]], lookback_days: int) -> dict[str, Any]:
    counterparties: set[str] = set()
    mints: set[str] = set()
    native_count = 0
    token_count = 0
    for tx in transactions:
        for transfer in tx.get("nativeTransfers") or []:
            native_count += 1
            _add_counterparty(counterparties, transfer, target["wallet"])
        for transfer in tx.get("tokenTransfers") or []:
            token_count += 1
            _add_counterparty(counterparties, transfer, target["wallet"])
            if transfer.get("mint"):
                mints.add(str(transfer["mint"]))
    latest = max(transactions, key=lambda tx: (_block_time(tx) or 0, _transaction_signature(tx) or ""), default={})
    prior_count = len(transactions)
    return {
        "wallet": target["wallet"],
        "current_launch_id": target.get("current_launch_id"),
        "current_mint": target.get("current_mint"),
        "current_milestone_tier": target.get("current_milestone_tier"),
        "first_seen_in_launch_time": target.get("first_seen_in_launch_time"),
        "lookback_days": lookback_days,
        "prior_transaction_count": prior_count,
        "prior_native_transfer_count": native_count,
        "prior_token_transfer_count": token_count,
        "prior_distinct_counterparties": len(counterparties),
        "prior_distinct_mints": len(mints),
        "latest_prior_signature": _transaction_signature(latest) if latest else None,
        "latest_prior_block_time": _block_time(latest) if latest else None,
        "wallet_history_source_confidence": "medium" if prior_count else "none",
        "history_missing_reason": None if prior_count else "no_prior_transactions_in_lookback_window",
        "source_method": "helius_getTransactionsForAddress",
        "semantic_label": "wallet_structure_proxy",
    }


def _final_report(
    *,
    base_report: dict[str, Any],
    rows: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    requests_used: int,
    transactions_fetched: int,
    raw_transactions_preserved: int,
    stopped_due_ceiling: bool,
    provider_errors: list[str],
    started: float,
) -> dict[str, Any]:
    covered = [row for row in rows if row.get("prior_transaction_count", 0) > 0]
    readiness = _readiness(rows, covered, provider_errors, stopped_due_ceiling)
    return {
        **base_report,
        "readiness_classification": readiness,
        "execution": {**base_report["execution"], "mode": "execute", "elapsed_seconds": round(time.time() - started, 3)},
        "network_calls_made": requests_used,
        "collection": {
            "wallets_planned": len(targets),
            "wallets_completed": len(rows),
            "wallets_with_prior_history": len(covered),
            "launches_covered": len({row.get("current_launch_id") for row in rows if row.get("current_launch_id")}),
            "transactions_fetched": transactions_fetched,
        },
        "requests": {**base_report["requests"], "requests_used": requests_used, "stopped_due_ceiling": stopped_due_ceiling},
        "raw": {"raw_transactions_preserved": raw_transactions_preserved, "raw_path": base_report["outputs"]["raw_path"]},
        "history": {
            "prior_history_coverage": {
                "wallets_with_prior_history": len(covered),
                "total_wallets_completed": len(rows),
                "coverage_pct": _pct(len(covered), len(rows)),
            },
            "prior_transaction_count_distribution": dict(Counter(str(row.get("prior_transaction_count", 0)) for row in rows)),
            "missing_reason_counts": dict(Counter(row.get("history_missing_reason") or "none" for row in rows)),
        },
        "provider": {"errors": provider_errors},
        "warnings": _warnings(provider_errors, stopped_due_ceiling, rows, covered),
    }


def _readiness(rows: list[dict[str, Any]], covered: list[dict[str, Any]], errors: list[str], stopped: bool) -> str:
    if errors:
        return READINESS_BLOCKED
    if not rows:
        return READINESS_BLOCKED
    if stopped:
        return READINESS_PARTIAL
    if _pct(len(covered), len(rows)) >= 25.0:
        return READINESS_READY
    return READINESS_PARTIAL


def _base_report(
    *,
    target_csv_path: Path | str,
    targets: list[dict[str, Any]],
    execute: bool,
    lookback_days: int,
    request_ceiling: int,
    max_total_transactions: int,
    paths: dict[str, Path],
    started: float,
) -> dict[str, Any]:
    return {
        "report_id": "p0_early_buyer_wallet_history_pilot_v0",
        "execution": {"mode": "execute" if execute else "dry_run", "started_at": _timestamp(int(started)), "elapsed_seconds": 0.0},
        "network_calls_made": 0,
        "scope": {
            "target_csv_path": str(target_csv_path),
            "selected_wallets": len(targets),
            "launches_covered": len({row.get("current_launch_id") for row in targets if row.get("current_launch_id")}),
            "lookback_days": lookback_days,
        },
        "requests": {
            "request_ceiling": request_ceiling,
            "max_total_transactions": max_total_transactions,
            "requests_used": 0,
            "stopped_due_ceiling": False,
        },
        "outputs": {key: str(value) for key, value in paths.items()},
        "collection": {
            "wallets_planned": len(targets),
            "wallets_completed": 0,
            "wallets_with_prior_history": 0,
            "launches_covered": 0,
            "transactions_fetched": 0,
        },
        "guardrails": {
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
            "paper_trading_runs": 0,
            "live_trading_runs": 0,
            "trading_logic_added": False,
            "outcome_comparisons": 0,
            "threshold_optimization": False,
            "grid_search": False,
            "ml": False,
        },
    }


def _warnings(errors: list[str], stopped: bool, rows: list[dict[str, Any]], covered: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if errors:
        warnings.append("provider_or_auth_error")
    if stopped:
        warnings.append("stopped_due_request_or_transaction_ceiling")
    if not covered:
        warnings.append("no_prior_wallet_history_detected")
    if rows and _pct(len(covered), len(rows)) < 25.0:
        warnings.append("prior_wallet_history_coverage_below_ready_threshold")
    return warnings


def _select_targets(rows: list[dict[str, Any]], max_wallets: int) -> list[dict[str, Any]]:
    selected = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: (item.get("current_launch_id") or "", item.get("wallet") or "")):
        wallet = row.get("wallet")
        first_seen = _int_or_none(row.get("first_seen_in_launch_time"))
        if not wallet or wallet in seen or first_seen is None:
            continue
        copy = dict(row)
        copy["first_seen_in_launch_time"] = first_seen
        selected.append(copy)
        seen.add(wallet)
        if len(selected) >= max_wallets:
            break
    return selected


def _add_counterparty(output: set[str], transfer: dict[str, Any], wallet: str) -> None:
    for key in ("fromUserAccount", "from", "toUserAccount", "to"):
        value = transfer.get(key)
        if value and value != wallet:
            output.add(str(value))


def _append_raw_transaction(path: Path, target: dict[str, Any], tx: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "wallet": target.get("wallet"),
        "current_launch_id": target.get("current_launch_id"),
        "current_mint": target.get("current_mint"),
        "signature": _transaction_signature(tx),
        "block_time": _block_time(tx),
        "raw_json": tx,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True))
        f.write("\n")


def _flush_outputs(rows: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    sorted_rows = sorted(rows, key=lambda row: (row.get("current_launch_id") or "", row.get("wallet") or ""))
    _write_jsonl(paths["jsonl_path"], sorted_rows)
    _write_parquet(sorted_rows, paths["parquet_path"])


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    (paths["report_dir"] / "early_buyer_wallet_history_pilot_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (paths["report_dir"] / "early_buyer_wallet_history_pilot_summary.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    history = report.get("history", {})
    return "\n".join(
        [
            "# P0 Early-Buyer Wallet History Pilot Summary",
            "",
            f"- Readiness classification: `{report.get('readiness_classification')}`",
            f"- Execution mode: `{report['execution']['mode']}`",
            f"- Selected wallets: `{report['scope']['selected_wallets']}`",
            f"- Wallets completed: `{report['collection']['wallets_completed']}`",
            f"- Requests used: `{report['requests']['requests_used']}`",
            f"- Transactions fetched: `{report['collection']['transactions_fetched']}`",
            f"- Prior history coverage: `{history.get('prior_history_coverage', {})}`",
            f"- Warnings: `{report.get('warnings', [])}`",
            "",
            "No thesis, outcome comparison, validation, backtest, paper trading, live trading, optimization, grid search, or ML workflow was run.",
        ]
    ) + "\n"


def _read_target_csv(path: Path | str) -> list[dict[str, Any]]:
    value = Path(path)
    if not value.exists():
        return []
    with value.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_existing_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _dedupe_rows_by_wallet(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup = {row.get("wallet"): row for row in rows if row.get("wallet")}
    return list(dedup.values())


def _read_existing_raw_signatures(path: Path) -> set[str]:
    if not path.exists():
        return set()
    output = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                signature = json.loads(line).get("signature")
                if signature:
                    output.add(signature)
    return output


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
    except Exception:
        path.with_suffix(".parquet.unavailable.json").write_text(
            json.dumps({"row_count": len(rows), "reason": "pandas_or_parquet_engine_unavailable"}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return
    pd.DataFrame(rows).to_parquet(path, index=False)


def _resolve_output_paths(output_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = output_paths or {}
    return {
        "raw_path": Path(supplied.get("raw_path", DEFAULT_RAW_PATH)),
        "jsonl_path": Path(supplied.get("jsonl_path", DEFAULT_JSONL_PATH)),
        "parquet_path": Path(supplied.get("parquet_path", DEFAULT_PARQUET_PATH)),
        "checkpoint_path": Path(supplied.get("checkpoint_path", DEFAULT_CHECKPOINT_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _transaction_signature(tx: dict[str, Any]) -> str | None:
    if tx.get("signature"):
        return str(tx["signature"])
    signatures = ((tx.get("transaction") or {}).get("signatures") or [])
    return str(signatures[0]) if signatures else None


def _block_time(tx: dict[str, Any]) -> int | None:
    return _int_or_none(tx.get("blockTime") or tx.get("timestamp"))


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 4) if denominator else 0.0


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
