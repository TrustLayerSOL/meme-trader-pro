"""Bounded top-holder replay pilot from mint transaction history."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.solana_transaction_parser import extract_token_balance_deltas


READINESS_READY = "top_holder_replay_ready_for_review"
READINESS_PARTIAL = "top_holder_replay_partial_needs_review"
READINESS_BLOCKED = "top_holder_replay_blocked"

DEFAULT_TARGET_CSV_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_helius_planners",
    "top_holder_snapshot_targets.csv",
)
DEFAULT_RAW_PATH = data_lake_path(
    "data",
    "raw",
    "structural_enrichment",
    "top_holder_replay_pilot",
    "top_holder_replay_raw_transactions.jsonl",
)
DEFAULT_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "top_holder_replay_pilot.jsonl",
)
DEFAULT_PARQUET_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "top_holder_replay_pilot.parquet",
)
DEFAULT_CHECKPOINT_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "checkpoints",
    "top_holder_replay_pilot.json",
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_top_holder_replay_pilot",
)


def run_p0_top_holder_replay_pilot(
    *,
    target_csv_path: Path | str = DEFAULT_TARGET_CSV_PATH,
    execute: bool = False,
    max_mints: int = 25,
    max_pages_per_mint: int = 2,
    max_transactions_per_mint: int = 200,
    max_total_transactions: int = 5_000,
    request_ceiling: int = 500,
    output_paths: dict[str, Path | str] | None = None,
    client: Any | None = None,
    transaction_workers: int = 16,
) -> dict[str, Any]:
    started = time.time()
    paths = _resolve_output_paths(output_paths)
    targets = _select_targets(_read_target_csv(target_csv_path), max_mints=max_mints)
    targets_by_mint = _targets_by_mint(targets)
    base = _base_report(
        target_csv_path=target_csv_path,
        targets=targets,
        targets_by_mint=targets_by_mint,
        execute=execute,
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
    checkpoint = load_top_holder_replay_checkpoint(paths["checkpoint_path"])
    completed_mints = set(checkpoint.get("completed_mints") or [])
    requests_used = int(checkpoint.get("requests_used") or 0)
    transactions_fetched = int(checkpoint.get("transactions_fetched") or 0)
    raw_signatures = _read_existing_raw_signatures(paths["raw_path"])
    rows_by_key = _rows_by_key(_read_existing_jsonl(paths["jsonl_path"]))
    stopped_due_ceiling = False
    provider_errors: list[str] = []

    for mint, mint_targets in targets_by_mint.items():
        if mint in completed_mints:
            continue
        if requests_used >= request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        try:
            collected = _collect_mint_history(
                rpc=rpc,
                mint=mint,
                targets=mint_targets,
                max_pages=max_pages_per_mint,
                max_transactions=max_transactions_per_mint,
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
                _append_raw_transaction(paths["raw_path"], mint, tx)
                raw_signatures.add(signature)

        for row in _replay_mint_targets(mint, mint_targets, collected["transactions"]):
            rows_by_key[_row_key(row)] = row
        completed_mints.add(mint)
        _flush_outputs(list(rows_by_key.values()), paths)
        write_top_holder_replay_checkpoint(
            paths["checkpoint_path"],
            {
                "completed_mints": sorted(completed_mints),
                "requests_used": requests_used,
                "transactions_fetched": transactions_fetched,
                "last_mint": mint,
                "updated_at": _timestamp(int(time.time())),
            },
        )
        if stopped_due_ceiling:
            break

    rows = list(rows_by_key.values())
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


def load_top_holder_replay_checkpoint(path: Path | str) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def write_top_holder_replay_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _collect_mint_history(
    *,
    rpc: Any,
    mint: str,
    targets: list[dict[str, Any]],
    max_pages: int,
    max_transactions: int,
    max_total_transactions: int,
    request_ceiling: int,
    requests_used: int,
    transactions_fetched: int,
) -> dict[str, Any]:
    start_time = min(int(row["launch_ts"]) for row in targets if row.get("launch_ts") is not None)
    end_time = max(int(row["milestone_time"]) for row in targets)
    transactions: list[dict[str, Any]] = []
    pagination_token = None
    stopped_due_ceiling = False
    for _ in range(max_pages):
        if requests_used + 1 > request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        remaining_mint = max_transactions - len(transactions)
        remaining_total = max_total_transactions - transactions_fetched
        if remaining_mint <= 0 or remaining_total <= 0:
            stopped_due_ceiling = remaining_total <= 0
            break
        result = rpc.fetch_transactions_for_address_window(
            mint,
            start_time=start_time,
            end_time=end_time,
            limit=max(1, min(remaining_mint, remaining_total, 1000)),
            pagination_token=pagination_token,
            transaction_details="full",
            sort_order="asc",
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
        "transactions": sorted(transactions, key=lambda tx: (_block_time(tx) or 0, _transaction_signature(tx) or "")),
        "requests_used": requests_used,
        "transactions_fetched": transactions_fetched,
        "stopped_due_ceiling": stopped_due_ceiling,
    }


def _replay_mint_targets(mint: str, targets: list[dict[str, Any]], transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_targets = sorted(targets, key=lambda row: (row["milestone_time"], row["milestone"]))
    ordered_transactions = sorted(transactions, key=lambda tx: (_block_time(tx) or 0, _transaction_signature(tx) or ""))
    balances: dict[str, float] = defaultdict(float)
    tx_index = 0
    output = []
    for target in ordered_targets:
        milestone_time = int(target["milestone_time"])
        while tx_index < len(ordered_transactions) and (_block_time(ordered_transactions[tx_index]) or 0) <= milestone_time:
            _apply_token_deltas(balances, mint, ordered_transactions[tx_index])
            tx_index += 1
        output.append(_snapshot_row(target, balances, transactions_seen=tx_index))
    return output


def _apply_token_deltas(balances: dict[str, float], mint: str, tx: dict[str, Any]) -> None:
    for delta in extract_token_balance_deltas(tx):
        if delta.mint != mint or delta.delta is None:
            continue
        owner = delta.owner or delta.account
        if not owner:
            continue
        balances[str(owner)] += float(delta.delta)
        if abs(balances[str(owner)]) < 1e-12:
            balances[str(owner)] = 0.0


def _snapshot_row(target: dict[str, Any], balances: dict[str, float], transactions_seen: int) -> dict[str, Any]:
    positive = {owner: balance for owner, balance in balances.items() if balance > 0}
    total = sum(positive.values())
    if total <= 0:
        return {
            **_target_base(target),
            "transactions_replayed_before_milestone": transactions_seen,
            "holder_count_proxy": None,
            "top_holder_owner": None,
            "top_holder_balance_proxy": None,
            "top_holder_share_proxy": None,
            "top_10_holder_share_proxy": None,
            "holder_snapshot_source": "mint_transaction_balance_delta_replay_v0",
            "holder_snapshot_confidence": "missing",
            "holder_snapshot_missing_reason": "no_token_balance_deltas_before_milestone",
            "is_confirmed_full_chain_snapshot": False,
            "semantic_label": "top_holder_behavior_proxy",
        }
    sorted_balances = sorted(positive.items(), key=lambda item: (-item[1], item[0]))
    top_10_sum = sum(balance for _owner, balance in sorted_balances[:10])
    top_owner, top_balance = sorted_balances[0]
    return {
        **_target_base(target),
        "transactions_replayed_before_milestone": transactions_seen,
        "holder_count_proxy": len(positive),
        "top_holder_owner": top_owner,
        "top_holder_balance_proxy": top_balance,
        "top_holder_share_proxy": top_balance / total,
        "top_10_holder_share_proxy": top_10_sum / total,
        "holder_snapshot_source": "mint_transaction_balance_delta_replay_v0",
        "holder_snapshot_confidence": "medium",
        "holder_snapshot_missing_reason": None,
        "is_confirmed_full_chain_snapshot": False,
        "semantic_label": "top_holder_behavior_proxy",
    }


def _target_base(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "launch_id": target.get("launch_id"),
        "mint": target.get("mint"),
        "milestone": target.get("milestone"),
        "milestone_time": target.get("milestone_time"),
        "milestone_age_seconds": target.get("milestone_age_seconds"),
        "milestone_tier": target.get("milestone_tier"),
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
    usable = [row for row in rows if row.get("top_holder_share_proxy") is not None]
    readiness = _readiness(rows, usable, provider_errors, stopped_due_ceiling)
    return {
        **base_report,
        "readiness_classification": readiness,
        "execution": {**base_report["execution"], "mode": "execute", "elapsed_seconds": round(time.time() - started, 3)},
        "network_calls_made": requests_used,
        "collection": {
            "mints_planned": len({row["mint"] for row in targets}),
            "mints_completed": len({row["mint"] for row in rows}),
            "milestones_planned": len(targets),
            "milestones_completed": len(rows),
            "transactions_fetched": transactions_fetched,
        },
        "requests": {**base_report["requests"], "requests_used": requests_used, "stopped_due_ceiling": stopped_due_ceiling},
        "raw": {"raw_transactions_preserved": raw_transactions_preserved, "raw_path": base_report["outputs"]["raw_path"]},
        "replay_quality": {
            "milestones_with_holder_proxy": len(usable),
            "total_milestones_completed": len(rows),
            "coverage_pct": _pct(len(usable), len(rows)),
            "missing_reason_counts": dict(Counter(row.get("holder_snapshot_missing_reason") or "none" for row in rows)),
        },
        "provider": {"errors": provider_errors},
        "warnings": _warnings(provider_errors, stopped_due_ceiling, rows, usable),
    }


def _readiness(rows: list[dict[str, Any]], usable: list[dict[str, Any]], errors: list[str], stopped: bool) -> str:
    if errors or not rows:
        return READINESS_BLOCKED
    if stopped:
        return READINESS_PARTIAL
    if _pct(len(usable), len(rows)) >= 50.0:
        return READINESS_READY
    return READINESS_PARTIAL


def _base_report(
    *,
    target_csv_path: Path | str,
    targets: list[dict[str, Any]],
    targets_by_mint: dict[str, list[dict[str, Any]]],
    execute: bool,
    request_ceiling: int,
    max_total_transactions: int,
    paths: dict[str, Path],
    started: float,
) -> dict[str, Any]:
    return {
        "report_id": "p0_top_holder_replay_pilot_v0",
        "execution": {"mode": "execute" if execute else "dry_run", "started_at": _timestamp(int(started)), "elapsed_seconds": 0.0},
        "network_calls_made": 0,
        "scope": {
            "target_csv_path": str(target_csv_path),
            "selected_mints": len(targets_by_mint),
            "selected_milestones": len(targets),
            "source_semantics": "mint_transaction_balance_delta_replay_not_confirmed_full_chain_snapshot",
        },
        "requests": {
            "request_ceiling": request_ceiling,
            "max_total_transactions": max_total_transactions,
            "requests_used": 0,
            "stopped_due_ceiling": False,
        },
        "outputs": {key: str(value) for key, value in paths.items()},
        "collection": {
            "mints_planned": len(targets_by_mint),
            "mints_completed": 0,
            "milestones_planned": len(targets),
            "milestones_completed": 0,
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


def _warnings(errors: list[str], stopped: bool, rows: list[dict[str, Any]], usable: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if errors:
        warnings.append("provider_or_auth_error")
    if stopped:
        warnings.append("stopped_due_request_or_transaction_ceiling")
    if not usable:
        warnings.append("no_top_holder_proxy_reconstructed")
    elif rows and _pct(len(usable), len(rows)) < 50.0:
        warnings.append("top_holder_proxy_coverage_below_ready_threshold")
    return warnings


def _select_targets(rows: list[dict[str, Any]], max_mints: int) -> list[dict[str, Any]]:
    output = []
    seen_mints: set[str] = set()
    for row in sorted(rows, key=lambda item: (item.get("milestone_tier") or "", item.get("launch_id") or "", item.get("milestone") or "")):
        mint = row.get("mint")
        milestone_time = _int_or_none(row.get("milestone_time"))
        age = _int_or_none(row.get("milestone_age_seconds"))
        if not mint or milestone_time is None or age is None:
            continue
        if mint not in seen_mints and len(seen_mints) >= max_mints:
            continue
        seen_mints.add(mint)
        copy = dict(row)
        copy["milestone_time"] = milestone_time
        copy["milestone_age_seconds"] = age
        copy["launch_ts"] = milestone_time - age
        output.append(copy)
    return output


def _targets_by_mint(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        grouped[target["mint"]].append(target)
    return dict(grouped)


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("mint")), str(row.get("milestone")))


def _rows_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {_row_key(row): row for row in rows if row.get("mint") and row.get("milestone")}


def _append_raw_transaction(path: Path, mint: str, tx: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "mint": mint,
        "signature": _transaction_signature(tx),
        "block_time": _block_time(tx),
        "raw_json": tx,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True))
        f.write("\n")


def _flush_outputs(rows: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    sorted_rows = sorted(rows, key=lambda row: (row.get("mint") or "", _int_or_none(row.get("milestone_time")) or 0, row.get("milestone") or ""))
    _write_jsonl(paths["jsonl_path"], sorted_rows)
    _write_parquet(sorted_rows, paths["parquet_path"])


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    (paths["report_dir"] / "top_holder_replay_pilot_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (paths["report_dir"] / "top_holder_replay_pilot_summary.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    quality = report.get("replay_quality", {})
    return "\n".join(
        [
            "# P0 Top-Holder Replay Pilot Summary",
            "",
            f"- Readiness classification: `{report.get('readiness_classification')}`",
            f"- Execution mode: `{report['execution']['mode']}`",
            f"- Selected mints: `{report['scope']['selected_mints']}`",
            f"- Milestones completed: `{report['collection']['milestones_completed']}`",
            f"- Requests used: `{report['requests']['requests_used']}`",
            f"- Transactions fetched: `{report['collection']['transactions_fetched']}`",
            f"- Replay coverage: `{quality}`",
            f"- Warnings: `{report.get('warnings', [])}`",
            "",
            "This is a top-holder behavior proxy from mint transaction balance-delta replay, not a confirmed full-chain historical account-state snapshot.",
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
