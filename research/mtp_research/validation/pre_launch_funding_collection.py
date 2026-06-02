"""Bounded pre-launch creator funding-lineage pilot."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.validation.pre_launch_funding_planner import (
    CLASSIFICATION_GO,
    build_pre_launch_funding_dry_run_plan,
)


READINESS_READY = "funding_link_ready_for_T009"
READINESS_PARTIAL = "funding_link_partial_needs_more_data"
READINESS_BLOCKED = "funding_link_blocked"

DEFAULT_CANDIDATES_PATH = data_lake_path("data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl")
DEFAULT_RAW_PATH = data_lake_path("data", "backtests", "funding_link", "raw", "funding_link_raw_transactions.jsonl")
DEFAULT_JSONL_PATH = data_lake_path("data", "backtests", "funding_link", "funding_link_pilot.jsonl")
DEFAULT_PARQUET_PATH = data_lake_path("data", "backtests", "funding_link", "funding_link_pilot.parquet")
DEFAULT_CHECKPOINT_PATH = data_lake_path("data", "backtests", "funding_link", "funding_link_collection_checkpoint.json")
DEFAULT_REPORT_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "funding_link_pilot")


def run_pre_launch_funding_collection(
    *,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    execute: bool = False,
    max_creators: int = 50,
    lookback_hours: int = 24,
    max_signature_pages_per_creator: int = 2,
    max_transactions_per_creator: int = 50,
    max_total_transactions: int = 2500,
    request_ceiling: int = 3000,
    hard_stop_projected_requests: int = 5000,
    output_paths: dict[str, Path | str] | None = None,
    client: Any | None = None,
    transaction_workers: int = 16,
) -> dict[str, Any]:
    started = time.time()
    paths = _resolve_output_paths(output_paths)
    candidates = _read_jsonl(candidates_path)
    candidates_by_launch = {row.get("launch_id"): row for row in candidates if row.get("launch_id")}
    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=candidates_path,
        max_creators=max_creators,
        lookback_hours=lookback_hours,
        request_ceiling=request_ceiling,
        hard_stop_projected_requests=hard_stop_projected_requests,
        dry_run=True,
    )
    base = _base_report(plan=plan, paths=paths, execute=execute, started=started)
    if not execute:
        report = {
            **base,
            "readiness_classification": READINESS_PARTIAL,
            "warnings": ["dry_run_only_no_collection_performed"],
            "exact_execute_command": plan["exact_later_execute_command"],
        }
        _write_reports(report, paths)
        return report
    if plan["dry_run_classification"] != CLASSIFICATION_GO:
        report = {
            **base,
            "readiness_classification": READINESS_BLOCKED,
            "warnings": ["projected_request_gate_failed", *plan["stop_go"]["failed_gates"]],
            "requests": {**base["requests"], "stopped_due_ceiling": True},
        }
        _write_reports(report, paths)
        return report

    rpc = client or HeliusHistoricalAdapter.from_env(transaction_workers=transaction_workers)
    checkpoint = load_funding_collection_checkpoint(paths["checkpoint_path"])
    completed_creators = set(checkpoint.get("completed_creators") or [])
    requests_used = int(checkpoint.get("requests_used") or 0)
    transactions_fetched = int(checkpoint.get("transactions_fetched") or 0)
    rows = _dedupe_rows_by_launch(_read_existing_jsonl(paths["jsonl_path"]))
    raw_signatures = _read_existing_raw_signatures(paths["raw_path"])
    creator_raw: dict[str, list[dict[str, Any]]] = {}
    stopped_due_ceiling = False
    provider_errors: list[str] = []
    creators_attempted = 0
    creators_completed = 0

    for creator_row in plan["selected_creators"]:
        creator = creator_row["creator"]
        if creator in completed_creators:
            continue
        if requests_used >= request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        creators_attempted += 1
        try:
            collected = _collect_creator_window(
                rpc=rpc,
                creator_row=creator_row,
                lookback_hours=lookback_hours,
                max_signature_pages=max_signature_pages_per_creator,
                max_transactions=max_transactions_per_creator,
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
        creator_raw[creator] = collected["transactions"]
        for tx in collected["transactions"]:
            signature = _transaction_signature(tx)
            if signature and signature not in raw_signatures:
                _append_raw_transaction(paths["raw_path"], creator_row, tx)
                raw_signatures.add(signature)
        launch_rows = _rows_for_creator_launches(
            creator_row=creator_row,
            candidates_by_launch=candidates_by_launch,
            transactions=collected["transactions"],
            lookback_hours=lookback_hours,
        )
        existing = {row["launch_id"]: row for row in rows}
        for row in launch_rows:
            existing[row["launch_id"]] = row
        rows = list(existing.values())
        completed_creators.add(creator)
        creators_completed += 1
        write_funding_collection_checkpoint(
            paths["checkpoint_path"],
            {
                "completed_creators": sorted(completed_creators),
                "requests_used": requests_used,
                "transactions_fetched": transactions_fetched,
                "last_creator": creator,
                "updated_at": _utc_now(),
            },
        )
        _flush_outputs(rows, paths)
        if stopped_due_ceiling:
            break

    rows = _add_repeated_funder_fields(rows)
    _flush_outputs(rows, paths)
    selected_creators = {row["creator"] for row in plan["selected_creators"]}
    creators_completed_total = len(completed_creators & selected_creators)
    creators_attempted_total = max(creators_attempted, creators_completed_total)
    report = _final_report(
        base_report=base,
        plan=plan,
        rows=rows,
        creators_attempted=creators_attempted_total,
        creators_completed=creators_completed_total,
        requests_used=requests_used,
        transactions_fetched=transactions_fetched,
        raw_transactions_preserved=len(raw_signatures),
        stopped_due_ceiling=stopped_due_ceiling,
        provider_errors=provider_errors,
        started=started,
    )
    _write_reports(report, paths)
    return report


def load_funding_collection_checkpoint(path: Path | str) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def write_funding_collection_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _collect_creator_window(
    *,
    rpc: Any,
    creator_row: dict[str, Any],
    lookback_hours: int,
    max_signature_pages: int,
    max_transactions: int,
    max_total_transactions: int,
    request_ceiling: int,
    requests_used: int,
    transactions_fetched: int,
) -> dict[str, Any]:
    start_time = int(creator_row["first_launch_ts"]) - lookback_hours * 3600
    end_time = int(creator_row["last_launch_ts"])
    transactions: list[dict[str, Any]] = []
    pagination_token = None
    stopped_due_ceiling = False
    for _ in range(max_signature_pages):
        if requests_used + 1 > request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        remaining_for_creator = max_transactions - len(transactions)
        remaining_total = max_total_transactions - transactions_fetched
        if remaining_for_creator <= 0 or remaining_total <= 0:
            stopped_due_ceiling = remaining_total <= 0
            break
        result = rpc.fetch_transactions_for_address_window(
            creator_row["creator"],
            start_time=start_time,
            end_time=end_time,
            limit=max(1, min(remaining_for_creator, remaining_total, 1000)),
            pagination_token=pagination_token,
            transaction_details="full",
            sort_order="desc",
        )
        requests_used += 1
        page = list(result.get("transactions") or [])
        for tx in page:
            if not _in_window(_block_time(tx), start_time, end_time):
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


def _rows_for_creator_launches(
    *,
    creator_row: dict[str, Any],
    candidates_by_launch: dict[str, dict[str, Any]],
    transactions: list[dict[str, Any]],
    lookback_hours: int,
) -> list[dict[str, Any]]:
    output = []
    for launch_id in creator_row["selected_launch_ids"]:
        candidate = candidates_by_launch.get(launch_id, {})
        launch_ts = _int_or_none(candidate.get("launch_ts"))
        launch_time = candidate.get("launch_time_utc") or _timestamp(launch_ts)
        funding = _latest_funding_candidate(transactions, creator_row["creator"], launch_ts, lookback_hours)
        output.append(_funding_row(candidate, creator_row["creator"], launch_id, launch_time, launch_ts, funding))
    return output


def _latest_funding_candidate(
    transactions: list[dict[str, Any]],
    creator: str,
    launch_ts: int | None,
    lookback_hours: int,
) -> dict[str, Any] | None:
    if launch_ts is None:
        return None
    start = launch_ts - lookback_hours * 3600
    candidates = []
    for tx in transactions:
        block_time = _block_time(tx)
        if not _in_window(block_time, start, launch_ts):
            continue
        candidates.extend(_funding_candidates_from_tx(tx, creator))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.get("candidate_funding_time") or 0, item.get("candidate_funding_signature") or ""))


def _funding_candidates_from_tx(tx: dict[str, Any], creator: str) -> list[dict[str, Any]]:
    block_time = _block_time(tx)
    signature = _transaction_signature(tx)
    output = []
    for transfer in tx.get("nativeTransfers") or []:
        source = transfer.get("fromUserAccount") or transfer.get("from")
        destination = transfer.get("toUserAccount") or transfer.get("to")
        lamports = _float_or_none(transfer.get("amount"))
        if source and destination == creator and source != creator and lamports is not None:
            output.append(_candidate(source, signature, block_time, lamports / 1_000_000_000, None, 0.9, "native_transfer_to_creator"))
    for transfer in tx.get("tokenTransfers") or []:
        source = transfer.get("fromUserAccount") or transfer.get("from")
        destination = transfer.get("toUserAccount") or transfer.get("to")
        amount = transfer.get("tokenAmount") or transfer.get("amount")
        if source and destination == creator and source != creator and amount is not None:
            output.append(_candidate(source, signature, block_time, None, str(amount), 0.7, "token_transfer_to_creator"))
    for instruction in _all_parsed_instructions(tx):
        parsed = instruction.get("parsed") or {}
        info = parsed.get("info") or {}
        source = info.get("source")
        destination = info.get("destination")
        if not source or destination != creator or source == creator:
            continue
        lamports = _float_or_none(info.get("lamports"))
        token_amount = info.get("amount") or (info.get("tokenAmount") or {}).get("amount")
        if lamports is not None:
            output.append(_candidate(source, signature, block_time, lamports / 1_000_000_000, None, 0.85, "parsed_sol_transfer_to_creator"))
        elif token_amount is not None:
            output.append(_candidate(source, signature, block_time, None, str(token_amount), 0.65, "parsed_token_transfer_to_creator"))
    return output


def _candidate(
    wallet: str,
    signature: str | None,
    block_time: int | None,
    amount_sol: float | None,
    amount_token: str | None,
    confidence: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "candidate_funding_wallet": wallet,
        "candidate_funding_signature": signature,
        "candidate_funding_time": _timestamp(block_time),
        "candidate_funding_block_time": block_time,
        "funding_amount_sol": amount_sol,
        "funding_amount_token": amount_token,
        "funding_source_confidence": confidence,
        "funding_source_reason": reason,
    }


def _funding_row(
    candidate: dict[str, Any],
    creator: str,
    launch_id: str,
    launch_time: str | None,
    launch_ts: int | None,
    funding: dict[str, Any] | None,
) -> dict[str, Any]:
    if funding:
        age = launch_ts - funding["candidate_funding_block_time"] if launch_ts is not None and funding.get("candidate_funding_block_time") is not None else None
        return {
            "creator": creator,
            "launch_id": launch_id,
            "launch_time": launch_time,
            "launch_ts": launch_ts,
            "mint": candidate.get("token_mint") or candidate.get("mint"),
            **{key: value for key, value in funding.items() if key != "candidate_funding_block_time"},
            "funding_age_seconds": age,
            "funding_source_missing_reason": None,
            "creator_has_prior_funding_trace": True,
        }
    return {
        "creator": creator,
        "launch_id": launch_id,
        "launch_time": launch_time,
        "launch_ts": launch_ts,
        "mint": candidate.get("token_mint") or candidate.get("mint"),
        "candidate_funding_wallet": None,
        "candidate_funding_signature": None,
        "candidate_funding_time": None,
        "funding_age_seconds": None,
        "funding_amount_sol": None,
        "funding_amount_token": None,
        "funding_source_confidence": 0.0,
        "funding_source_reason": None,
        "funding_source_missing_reason": "no_inbound_transfer_to_creator_in_lookback_window",
        "creator_has_prior_funding_trace": False,
    }


def _add_repeated_funder_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wallet_counts = Counter(row.get("candidate_funding_wallet") for row in rows if row.get("candidate_funding_wallet"))
    creator_wallet_counts = Counter((row.get("creator"), row.get("candidate_funding_wallet")) for row in rows if row.get("candidate_funding_wallet"))
    output = []
    for row in rows:
        wallet = row.get("candidate_funding_wallet")
        output.append(
            {
                **row,
                "launches_sharing_funder": wallet_counts.get(wallet, 0) if wallet else 0,
                "creator_funder_reuse_count": creator_wallet_counts.get((row.get("creator"), wallet), 0) if wallet else 0,
                "common_funder_candidate_id": f"funder-{wallet}" if wallet and wallet_counts.get(wallet, 0) > 1 else None,
            }
        )
    return sorted(output, key=lambda row: (row.get("launch_ts") or 0, row.get("launch_id") or ""))


def _final_report(
    *,
    base_report: dict[str, Any],
    plan: dict[str, Any],
    rows: list[dict[str, Any]],
    creators_attempted: int,
    creators_completed: int,
    requests_used: int,
    transactions_fetched: int,
    raw_transactions_preserved: int,
    stopped_due_ceiling: bool,
    provider_errors: list[str],
    started: float,
) -> dict[str, Any]:
    covered = [row for row in rows if row.get("candidate_funding_wallet")]
    repeated = [row for row in covered if (row.get("launches_sharing_funder") or 0) > 1]
    readiness = _readiness(rows, covered, repeated, provider_errors, stopped_due_ceiling)
    return {
        **base_report,
        "readiness_classification": readiness,
        "t009_feasible": readiness == READINESS_READY,
        "execution": {**base_report["execution"], "mode": "execute", "elapsed_seconds": round(time.time() - started, 3)},
        "collection": {
            "creators_planned": plan["scope"]["selected_creator_count"],
            "creators_attempted": creators_attempted,
            "creators_completed": creators_completed,
            "launches_covered": len(rows),
            "transactions_fetched": transactions_fetched,
        },
        "requests": {**base_report["requests"], "requests_used": requests_used, "stopped_due_ceiling": stopped_due_ceiling},
        "raw": {"raw_transactions_preserved": raw_transactions_preserved, "raw_path": base_report["outputs"]["raw_path"]},
        "funding": {
            "funding_source_coverage": {
                "covered_launches": len(covered),
                "total_launches": len(rows),
                "coverage_pct": _pct(len(covered), len(rows)),
            },
            "repeated_funder_coverage": {
                "launches_with_repeated_funder": len(repeated),
                "coverage_pct": _pct(len(repeated), len(rows)),
                "unique_repeated_funders": len({row.get("candidate_funding_wallet") for row in repeated}),
            },
            "confidence_distribution": dict(Counter(str(row.get("funding_source_confidence", 0.0)) for row in rows)),
            "missing_reason_counts": dict(Counter(row.get("funding_source_missing_reason") or "none" for row in rows)),
            "top_common_funders": _top_common_funders(rows),
        },
        "provider": {"errors": provider_errors},
        "warnings": _warnings(provider_errors, stopped_due_ceiling, rows, covered, repeated),
    }


def _readiness(rows: list[dict[str, Any]], covered: list[dict[str, Any]], repeated: list[dict[str, Any]], errors: list[str], stopped: bool) -> str:
    if errors:
        return READINESS_BLOCKED
    if stopped:
        return READINESS_PARTIAL
    coverage = _pct(len(covered), len(rows))
    if coverage >= 25.0 and repeated:
        return READINESS_READY
    if covered:
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _base_report(*, plan: dict[str, Any], paths: dict[str, Path], execute: bool, started: float) -> dict[str, Any]:
    return {
        "report_id": "funding_link_pilot_v0",
        "execution": {"mode": "execute" if execute else "dry_run", "started_at": _timestamp(int(started)), "elapsed_seconds": 0.0},
        "scope": {
            "dataset": "strict_launch_regime",
            "selected_creators": plan["scope"]["selected_creator_count"],
            "launches_covered_by_selected_creators": plan["scope"]["launches_covered_by_selected_creators"],
            "lookback_hours": int(plan["request_estimate"]["lookback_window"].replace("h", "")),
        },
        "requests": {
            "base_projected_requests": plan["request_estimate"]["base_projected_requests"],
            "high_projected_requests": plan["request_estimate"]["high_projected_requests"],
            "request_ceiling": plan["request_estimate"]["request_ceiling"],
            "request_ceiling_status": plan["request_estimate"]["request_ceiling_status"],
            "requests_used": 0,
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
            "outcome_comparisons": 0,
            "threshold_optimization": False,
            "grid_search": False,
            "ml": False,
        },
    }


def _flush_outputs(rows: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    _write_jsonl(paths["jsonl_path"], _add_repeated_funder_fields(rows))
    _write_parquet(_add_repeated_funder_fields(rows), paths["parquet_path"])


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    (paths["report_dir"] / "funding_link_pilot_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (paths["report_dir"] / "funding_link_pilot_summary.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    funding = report.get("funding", {})
    return "\n".join(
        [
            "# Funding Link Pilot Summary",
            "",
            f"- Readiness classification: `{report.get('readiness_classification')}`",
            f"- Execution mode: `{report['execution']['mode']}`",
            f"- Selected creators: `{report['scope']['selected_creators']}`",
            f"- Launches covered: `{report['scope']['launches_covered_by_selected_creators']}`",
            f"- Requests used: `{report['requests']['requests_used']}`",
            f"- Transactions fetched: `{report.get('collection', {}).get('transactions_fetched', 0)}`",
            f"- Funding source coverage: `{funding.get('funding_source_coverage', {})}`",
            f"- Repeated funder coverage: `{funding.get('repeated_funder_coverage', {})}`",
            f"- Warnings: `{report.get('warnings', [])}`",
            "",
            "No thesis, outcome comparison, validation, backtest, paper trading, live trading, optimization, grid search, or ML workflow was run.",
        ]
    ) + "\n"


def _warnings(errors: list[str], stopped: bool, rows: list[dict[str, Any]], covered: list[dict[str, Any]], repeated: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if errors:
        warnings.append("provider_or_auth_error")
    if stopped:
        warnings.append("stopped_due_request_or_transaction_ceiling")
    if not covered:
        warnings.append("no_creator_funding_sources_detected")
    if covered and not repeated:
        warnings.append("no_repeated_funders_detected")
    if _pct(len(covered), len(rows)) < 25.0:
        warnings.append("funding_source_coverage_below_ready_threshold")
    return warnings


def _top_common_funders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row.get("candidate_funding_wallet") for row in rows if row.get("candidate_funding_wallet"))
    return [
        {"candidate_funding_wallet": wallet, "launch_count": count}
        for wallet, count in counts.most_common(10)
        if count > 1
    ]


def _append_raw_transaction(path: Path, creator_row: dict[str, Any], tx: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "creator": creator_row.get("creator"),
        "signature": _transaction_signature(tx),
        "block_time": _block_time(tx),
        "raw_json": tx,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True))
        f.write("\n")


def _all_parsed_instructions(tx: dict[str, Any]) -> list[dict[str, Any]]:
    message = ((tx.get("transaction") or {}).get("message") or {})
    instructions = [item for item in message.get("instructions") or [] if isinstance(item, dict)]
    for group in (tx.get("meta") or {}).get("innerInstructions") or []:
        instructions.extend([item for item in group.get("instructions") or [] if isinstance(item, dict)])
    return instructions


def _transaction_signature(tx: dict[str, Any]) -> str | None:
    if tx.get("signature"):
        return str(tx["signature"])
    signatures = ((tx.get("transaction") or {}).get("signatures") or [])
    return str(signatures[0]) if signatures else None


def _block_time(tx: dict[str, Any]) -> int | None:
    return _int_or_none(tx.get("blockTime") or tx.get("timestamp"))


def _in_window(value: int | None, start: int, end: int) -> bool:
    return value is not None and start <= value <= end


def _resolve_output_paths(output_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = output_paths or {}
    return {
        "raw_path": Path(supplied.get("raw_path", DEFAULT_RAW_PATH)),
        "jsonl_path": Path(supplied.get("jsonl_path", DEFAULT_JSONL_PATH)),
        "parquet_path": Path(supplied.get("parquet_path", DEFAULT_PARQUET_PATH)),
        "checkpoint_path": Path(supplied.get("checkpoint_path", DEFAULT_CHECKPOINT_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _read_existing_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _dedupe_rows_by_launch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup = {row.get("launch_id"): row for row in rows if row.get("launch_id")}
    return list(dedup.values())


def _read_existing_raw_signatures(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                sig = json.loads(line).get("signature")
                if sig:
                    out.add(sig)
    return out


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


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100), 4) if denominator else 0.0
