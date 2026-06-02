"""Bounded creator/funder transfer graph structural enrichment pilot."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter


READINESS_READY = "creator_funder_graph_ready_for_review"
READINESS_PARTIAL = "creator_funder_graph_partial_needs_more_data"
READINESS_BLOCKED = "creator_funder_graph_blocked"

DEFAULT_TARGET_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_helius_planners",
    "creator_funder_transfer_graph_targets.csv",
)
DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_classified",
    "launch_regime_candidates.jsonl",
)
DEFAULT_EARLY_BUYER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "early_buyer_wallet_history_pilot.jsonl",
)
DEFAULT_TOP_HOLDER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "top_holder_replay_pilot.jsonl",
)
DEFAULT_RAW_DIR = data_lake_path(
    "data",
    "raw",
    "structural_enrichment",
    "creator_funder_transfer_graph_pilot",
)
DEFAULT_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "creator_funder_transfer_graph_pilot.jsonl",
)
DEFAULT_PARQUET_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "creator_funder_transfer_graph_pilot.parquet",
)
DEFAULT_CHECKPOINT_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "creator_funder_transfer_graph_checkpoint.json",
)
DEFAULT_REPORT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "p0_creator_funder_transfer_graph_pilot",
)


def run_creator_funder_transfer_graph_collection(
    *,
    target_path: Path | str = DEFAULT_TARGET_PATH,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    early_buyer_path: Path | str = DEFAULT_EARLY_BUYER_PATH,
    top_holder_path: Path | str = DEFAULT_TOP_HOLDER_PATH,
    execute: bool = False,
    lookback_hours: int = 24,
    max_pages_per_address: int = 2,
    max_transactions_per_address: int = 200,
    max_total_transactions: int = 5_000,
    request_ceiling: int = 25_000,
    credit_cap: int = 25_000,
    output_paths: dict[str, Path | str] | None = None,
    client: Any | None = None,
    transaction_workers: int = 16,
) -> dict[str, Any]:
    started = time.time()
    paths = _resolve_output_paths(output_paths)
    target_rows = _read_csv(target_path)
    candidates_by_launch = {row.get("launch_id"): row for row in _read_jsonl(candidates_path) if row.get("launch_id")}
    enriched_targets = _enrich_targets(target_rows, candidates_by_launch)
    early_buyers_by_launch = _wallets_by_launch(early_buyer_path, launch_field="current_launch_id", wallet_field="wallet")
    top_holders_by_launch = _wallets_by_launch(top_holder_path, launch_field="launch_id", wallet_field="top_holder_owner")
    scope = _scope(enriched_targets)
    projected = _projected_requests(scope, max_pages_per_address=max_pages_per_address, projected_credit_cap=25_000)
    base = _base_report(
        execute=execute,
        started=started,
        scope=scope,
        projected=projected,
        paths=paths,
        lookback_hours=lookback_hours,
        credit_cap=credit_cap,
    )

    if projected["projected_credits"] > credit_cap:
        report = {
            **base,
            "readiness_classification": READINESS_BLOCKED,
            "warnings": ["projected_credit_cap_exceeded"],
            "quality": _empty_quality(),
        }
        _write_reports(report, paths)
        return report

    if not execute:
        report = {
            **base,
            "readiness_classification": READINESS_PARTIAL,
            "warnings": ["dry_run_only_no_collection_performed"],
            "quality": _empty_quality(),
        }
        _write_reports(report, paths)
        return report

    rpc = client or HeliusHistoricalAdapter.from_env(transaction_workers=transaction_workers)
    checkpoint = load_creator_funder_checkpoint(paths["checkpoint_path"])
    completed_addresses = set(checkpoint.get("completed_addresses") or [])
    requests_used = int(checkpoint.get("requests_used") or 0)
    transactions_fetched = int(checkpoint.get("transactions_fetched") or 0)
    raw_signatures = _read_existing_raw_signatures(paths["raw_path"])
    existing_transactions = _read_existing_raw_transactions(paths["raw_path"])
    transactions_by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in existing_transactions:
        address = raw.get("address")
        tx = raw.get("raw_json")
        if address and isinstance(tx, dict):
            transactions_by_address[address].append(tx)

    stopped_due_ceiling = False
    provider_errors: list[str] = []
    addresses_attempted = 0
    addresses_completed_now = 0
    for address_row in _address_plan(enriched_targets):
        address = address_row["address"]
        if address in completed_addresses:
            continue
        if requests_used >= request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        addresses_attempted += 1
        try:
            collected = _collect_address_window(
                rpc=rpc,
                address_row=address_row,
                max_pages=max_pages_per_address,
                max_transactions=max_transactions_per_address,
                max_total_transactions=max_total_transactions,
                request_ceiling=request_ceiling,
                requests_used=requests_used,
                transactions_fetched=transactions_fetched,
            )
        except Exception as exc:
            provider_errors.append(str(exc))
            break
        requests_used = collected["requests_used"]
        transactions_fetched = collected["transactions_fetched_total"]
        stopped_due_ceiling = stopped_due_ceiling or collected["stopped_due_ceiling"]
        transactions_by_address[address].extend(collected["transactions"])
        for tx in collected["transactions"]:
            signature = _transaction_signature(tx)
            if signature and signature not in raw_signatures:
                _append_raw_transaction(paths["raw_path"], address_row, tx)
                raw_signatures.add(signature)
        completed_addresses.add(address)
        addresses_completed_now += 1
        write_creator_funder_checkpoint(
            paths["checkpoint_path"],
            {
                "completed_addresses": sorted(completed_addresses),
                "requests_used": requests_used,
                "transactions_fetched": transactions_fetched,
                "last_address": address,
                "updated_at": _utc_now(),
            },
        )
        if stopped_due_ceiling:
            break

    rows = _build_launch_rows(
        enriched_targets,
        transactions_by_address=transactions_by_address,
        early_buyers_by_launch=early_buyers_by_launch,
        top_holders_by_launch=top_holders_by_launch,
        lookback_hours=lookback_hours,
    )
    rows = _add_shared_and_time_linked_fields(rows)
    _write_jsonl(paths["jsonl_path"], rows)
    _write_parquet(rows, paths["parquet_path"])
    report = _final_report(
        base=base,
        rows=rows,
        requests_used=requests_used,
        transactions_fetched=transactions_fetched,
        raw_responses_preserved=len(raw_signatures),
        addresses_attempted=max(addresses_attempted, len(completed_addresses & {row["address"] for row in _address_plan(enriched_targets)})),
        addresses_completed=len(completed_addresses & {row["address"] for row in _address_plan(enriched_targets)}),
        stopped_due_ceiling=stopped_due_ceiling,
        provider_errors=provider_errors,
        started=started,
    )
    _write_reports(report, paths)
    return report


def load_creator_funder_checkpoint(path: Path | str) -> dict[str, Any]:
    checkpoint = Path(path)
    if not checkpoint.exists():
        return {}
    return json.loads(checkpoint.read_text(encoding="utf-8"))


def write_creator_funder_checkpoint(path: Path | str, payload: dict[str, Any]) -> None:
    checkpoint = Path(path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _enrich_targets(target_rows: list[dict[str, Any]], candidates_by_launch: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for target in target_rows:
        candidate = candidates_by_launch.get(target.get("launch_id"), {})
        launch_ts = _int_or_none(candidate.get("launch_ts"))
        enriched.append(
            {
                **target,
                "mint": target.get("mint") or candidate.get("token_mint"),
                "launch_time": candidate.get("launch_time_utc") or _timestamp(launch_ts),
                "launch_ts": launch_ts,
            }
        )
    return sorted(enriched, key=lambda row: (row.get("launch_ts") or 0, row.get("launch_id") or ""))


def _scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    creators = {row.get("creator") for row in rows if row.get("creator")}
    funders = {row.get("candidate_funder") for row in rows if row.get("candidate_funder")}
    launches = {row.get("launch_id") for row in rows if row.get("launch_id")}
    return {
        "target_rows": len(rows),
        "creators_selected": len(creators),
        "candidate_funders_selected": len(funders),
        "launches_covered": len(launches),
        "address_count": len(creators | funders),
    }


def _projected_requests(scope: dict[str, Any], *, max_pages_per_address: int, projected_credit_cap: int) -> dict[str, Any]:
    projected_requests = int(scope["address_count"]) * max_pages_per_address
    return {
        "projected_requests": projected_requests,
        "projected_credits": min(projected_credit_cap, projected_requests),
        "planner_projected_credit_cap": projected_credit_cap,
    }


def _address_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for role, field in (("creator", "creator"), ("candidate_funder", "candidate_funder")):
        for row in rows:
            address = row.get(field)
            launch_ts = row.get("launch_ts")
            if not address or launch_ts is None:
                continue
            current = grouped.setdefault(
                address,
                {"address": address, "roles": set(), "launch_ids": set(), "start_time": launch_ts, "end_time": launch_ts},
            )
            current["roles"].add(role)
            current["launch_ids"].add(row.get("launch_id"))
            current["start_time"] = min(current["start_time"], launch_ts)
            current["end_time"] = max(current["end_time"], launch_ts)
    output = []
    for address, row in grouped.items():
        output.append(
            {
                "address": address,
                "roles": sorted(row["roles"]),
                "launch_ids": sorted(item for item in row["launch_ids"] if item),
                "start_time": int(row["start_time"]) - 24 * 3600,
                "end_time": int(row["end_time"]),
            }
        )
    return sorted(output, key=lambda row: (0 if "creator" in row["roles"] else 1, row["address"]))


def _collect_address_window(
    *,
    rpc: Any,
    address_row: dict[str, Any],
    max_pages: int,
    max_transactions: int,
    max_total_transactions: int,
    request_ceiling: int,
    requests_used: int,
    transactions_fetched: int,
) -> dict[str, Any]:
    transactions: list[dict[str, Any]] = []
    pagination_token = None
    stopped_due_ceiling = False
    for _ in range(max_pages):
        if requests_used + 1 > request_ceiling or transactions_fetched >= max_total_transactions:
            stopped_due_ceiling = True
            break
        remaining_for_address = max_transactions - len(transactions)
        remaining_total = max_total_transactions - transactions_fetched
        if remaining_for_address <= 0 or remaining_total <= 0:
            stopped_due_ceiling = remaining_total <= 0
            break
        result = rpc.fetch_transactions_for_address_window(
            address_row["address"],
            start_time=address_row["start_time"],
            end_time=address_row["end_time"],
            limit=max(1, min(remaining_for_address, remaining_total, 1000)),
            pagination_token=pagination_token,
            transaction_details="full",
            sort_order="desc",
        )
        requests_used += 1
        page = list(result.get("transactions") or [])
        for tx in page:
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
        "transactions_fetched_total": transactions_fetched,
        "stopped_due_ceiling": stopped_due_ceiling,
    }


def _build_launch_rows(
    rows: list[dict[str, Any]],
    *,
    transactions_by_address: dict[str, list[dict[str, Any]]],
    early_buyers_by_launch: dict[str, set[str]],
    top_holders_by_launch: dict[str, set[str]],
    lookback_hours: int,
) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        creator = row.get("creator")
        launch_ts = _int_or_none(row.get("launch_ts"))
        creator_transactions = transactions_by_address.get(creator, [])
        funding = _select_candidate_funder(creator_transactions, creator, row.get("candidate_funder"), launch_ts, lookback_hours)
        relations = _relation_proxies(
            creator=creator,
            transactions=creator_transactions,
            early_buyers=early_buyers_by_launch.get(row.get("launch_id"), set()),
            top_holders=top_holders_by_launch.get(row.get("launch_id"), set()),
        )
        output.append(_launch_row(row, funding, relations))
    return sorted(output, key=lambda item: (item.get("launch_ts") or 0, item.get("launch_id") or ""))


def _select_candidate_funder(
    transactions: list[dict[str, Any]],
    creator: str | None,
    planned_funder: str | None,
    launch_ts: int | None,
    lookback_hours: int,
) -> dict[str, Any] | None:
    if not creator or launch_ts is None:
        return None
    start = launch_ts - lookback_hours * 3600
    candidates = []
    for tx in transactions:
        block_time = _block_time(tx)
        if block_time is None or not (start <= block_time <= launch_ts):
            continue
        for transfer in _transfers(tx):
            if transfer["destination"] != creator or transfer["source"] == creator:
                continue
            if planned_funder and transfer["source"] == planned_funder:
                confidence = "high"
                reason = "planned_funder_transfer_to_creator_confirmed"
            else:
                confidence = "medium"
                reason = "inbound_transfer_to_creator"
            candidates.append(
                {
                    "candidate_funder": transfer["source"],
                    "creator_prior_funding_signature": _transaction_signature(tx),
                    "creator_prior_funding_time": _timestamp(block_time),
                    "creator_prior_funding_block_time": block_time,
                    "funding_amount_sol": transfer["amount_sol"],
                    "funding_amount_token": transfer["amount_token"],
                    "candidate_funder_confidence": confidence,
                    "candidate_funder_source": reason,
                }
            )
    if not candidates:
        return None
    preferred = [candidate for candidate in candidates if candidate["candidate_funder"] == planned_funder]
    selected = preferred or candidates
    return max(selected, key=lambda item: (item.get("creator_prior_funding_block_time") or 0, item.get("creator_prior_funding_signature") or ""))


def _relation_proxies(
    *,
    creator: str | None,
    transactions: list[dict[str, Any]],
    early_buyers: set[str],
    top_holders: set[str],
) -> dict[str, Any]:
    if not creator:
        return {
            "creator_to_early_buyer_transfer_link_proxy": False,
            "creator_to_top_holder_transfer_link_proxy": False,
            "creator_wallet_relation_proxy_count": 0,
            "creator_wallet_relation_proxy_confidence": "none",
        }
    early_linked: set[str] = set()
    top_linked: set[str] = set()
    for tx in transactions:
        for transfer in _transfers(tx):
            pair = {transfer["source"], transfer["destination"]}
            if creator not in pair:
                continue
            early_linked.update(pair & early_buyers)
            top_linked.update(pair & top_holders)
    relation_count = len(early_linked | top_linked)
    return {
        "creator_to_early_buyer_transfer_link_proxy": bool(early_linked),
        "creator_to_top_holder_transfer_link_proxy": bool(top_linked),
        "creator_wallet_relation_proxy_count": relation_count,
        "creator_wallet_relation_proxy_confidence": "medium" if relation_count else "none",
    }


def _launch_row(row: dict[str, Any], funding: dict[str, Any] | None, relations: dict[str, Any]) -> dict[str, Any]:
    launch_ts = _int_or_none(row.get("launch_ts"))
    if funding:
        funding_block_time = funding.get("creator_prior_funding_block_time")
        age = launch_ts - funding_block_time if launch_ts is not None and funding_block_time is not None else None
        candidate_funder = funding.get("candidate_funder")
        missing_reason = None
    else:
        age = None
        candidate_funder = row.get("candidate_funder") or None
        missing_reason = "no_prelaunch_transfer_found"
    return {
        "launch_id": row.get("launch_id"),
        "mint": row.get("mint"),
        "creator": row.get("creator"),
        "launch_time": row.get("launch_time"),
        "launch_ts": launch_ts,
        "candidate_funder": candidate_funder,
        "candidate_funder_confidence": funding.get("candidate_funder_confidence") if funding else "none",
        "candidate_funder_source": funding.get("candidate_funder_source") if funding else None,
        "creator_prior_funding_signature": funding.get("creator_prior_funding_signature") if funding else None,
        "creator_prior_funding_time": funding.get("creator_prior_funding_time") if funding else None,
        "funding_age_seconds": age,
        "funding_amount_sol": funding.get("funding_amount_sol") if funding else None,
        "funding_amount_token": funding.get("funding_amount_token") if funding else None,
        "funding_missing_reason": missing_reason,
        "common_funder_candidate_id": None,
        "launches_sharing_funder": 0,
        "creators_sharing_funder": 0,
        "wallets_sharing_funder_count": 0,
        "shared_funding_proxy": False,
        "shared_funding_confidence": "none",
        "funding_time_cluster_id": None,
        "funding_time_cluster_count": 0,
        "similar_funding_amount_cluster_count": 0,
        "time_linked_funding_proxy": False,
        "time_linked_funding_confidence": "none",
        "shared_funder_with_early_buyer_proxy": False,
        "shared_funder_with_top_holder_proxy": False,
        **relations,
        "semantic_label": "creator_funder_structural_proxy",
    }


def _add_shared_and_time_linked_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_funder: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("candidate_funder") and not row.get("funding_missing_reason"):
            by_funder[row["candidate_funder"]].append(row)
    output = []
    for row in rows:
        funder = row.get("candidate_funder")
        peers = by_funder.get(funder, []) if funder else []
        shared = len(peers) > 1
        cluster_count = _time_cluster_count(row, peers)
        amount_cluster_count = _amount_cluster_count(row, peers)
        output.append(
            {
                **row,
                "common_funder_candidate_id": f"funder-{funder}" if shared else None,
                "launches_sharing_funder": len({peer.get("launch_id") for peer in peers}) if shared else 0,
                "creators_sharing_funder": len({peer.get("creator") for peer in peers}) if shared else 0,
                "wallets_sharing_funder_count": len(peers) if shared else 0,
                "shared_funding_proxy": shared,
                "shared_funding_confidence": "medium" if shared else "none",
                "funding_time_cluster_id": f"time-cluster-{funder}" if cluster_count > 1 else None,
                "funding_time_cluster_count": cluster_count,
                "similar_funding_amount_cluster_count": amount_cluster_count,
                "time_linked_funding_proxy": cluster_count > 1 or amount_cluster_count > 1,
                "time_linked_funding_confidence": "medium" if cluster_count > 1 or amount_cluster_count > 1 else "none",
            }
        )
    return output


def _time_cluster_count(row: dict[str, Any], peers: list[dict[str, Any]]) -> int:
    base = _parse_iso_ts(row.get("creator_prior_funding_time"))
    if base is None:
        return 0
    return sum(1 for peer in peers if (other := _parse_iso_ts(peer.get("creator_prior_funding_time"))) is not None and abs(other - base) <= 3600)


def _amount_cluster_count(row: dict[str, Any], peers: list[dict[str, Any]]) -> int:
    amount = _float_or_none(row.get("funding_amount_sol"))
    if amount is None:
        return 0
    tolerance = max(0.001, amount * 0.10)
    return sum(1 for peer in peers if (other := _float_or_none(peer.get("funding_amount_sol"))) is not None and abs(other - amount) <= tolerance)


def _transfers(tx: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for transfer in tx.get("nativeTransfers") or []:
        source = transfer.get("fromUserAccount") or transfer.get("from")
        destination = transfer.get("toUserAccount") or transfer.get("to")
        lamports = _float_or_none(transfer.get("amount"))
        if source and destination and lamports is not None:
            output.append({"source": source, "destination": destination, "amount_sol": lamports / 1_000_000_000, "amount_token": None})
    for transfer in tx.get("tokenTransfers") or []:
        source = transfer.get("fromUserAccount") or transfer.get("from")
        destination = transfer.get("toUserAccount") or transfer.get("to")
        amount = transfer.get("tokenAmount") or transfer.get("amount")
        if source and destination and amount is not None:
            output.append({"source": source, "destination": destination, "amount_sol": None, "amount_token": str(amount)})
    for instruction in _all_parsed_instructions(tx):
        parsed = instruction.get("parsed") or {}
        info = parsed.get("info") or {}
        source = info.get("source")
        destination = info.get("destination")
        if not source or not destination:
            continue
        lamports = _float_or_none(info.get("lamports"))
        token_amount = info.get("amount") or (info.get("tokenAmount") or {}).get("amount")
        if lamports is not None:
            output.append({"source": source, "destination": destination, "amount_sol": lamports / 1_000_000_000, "amount_token": None})
        elif token_amount is not None:
            output.append({"source": source, "destination": destination, "amount_sol": None, "amount_token": str(token_amount)})
    return output


def _final_report(
    *,
    base: dict[str, Any],
    rows: list[dict[str, Any]],
    requests_used: int,
    transactions_fetched: int,
    raw_responses_preserved: int,
    addresses_attempted: int,
    addresses_completed: int,
    stopped_due_ceiling: bool,
    provider_errors: list[str],
    started: float,
) -> dict[str, Any]:
    candidate_rows = [row for row in rows if not row.get("funding_missing_reason")]
    shared_rows = [row for row in rows if row.get("shared_funding_proxy")]
    time_rows = [row for row in rows if row.get("time_linked_funding_proxy")]
    early_links = [row for row in rows if row.get("creator_to_early_buyer_transfer_link_proxy")]
    top_links = [row for row in rows if row.get("creator_to_top_holder_transfer_link_proxy")]
    readiness = _readiness(rows, candidate_rows, shared_rows, time_rows, provider_errors, stopped_due_ceiling, raw_responses_preserved)
    quality = {
        "candidate_funder_coverage": {
            "covered_launches": len(candidate_rows),
            "total_launches": len(rows),
            "coverage_pct": _pct(len(candidate_rows), len(rows)),
        },
        "shared_funder_coverage": {
            "launches_with_shared_funder_proxy": len(shared_rows),
            "coverage_pct": _pct(len(shared_rows), len(rows)),
            "shared_funder_count": len({row.get("candidate_funder") for row in shared_rows if row.get("candidate_funder")}),
        },
        "time_linked_funding_coverage": {
            "launches_with_time_linked_funding_proxy": len(time_rows),
            "coverage_pct": _pct(len(time_rows), len(rows)),
            "time_linked_funding_clusters_found": len({row.get("funding_time_cluster_id") for row in time_rows if row.get("funding_time_cluster_id")}),
        },
        "creator_wallet_relation_coverage": {
            "creator_to_early_buyer_links_found": len(early_links),
            "creator_to_top_holder_links_found": len(top_links),
            "coverage_pct": _pct(len(early_links) + len(top_links), len(rows)),
        },
        "missing_reason_counts": dict(Counter(row.get("funding_missing_reason") or "none" for row in rows)),
        "confidence_distribution": dict(Counter(row.get("candidate_funder_confidence") or "none" for row in rows)),
    }
    warnings = _warnings(provider_errors, stopped_due_ceiling, rows, candidate_rows, shared_rows, time_rows, raw_responses_preserved)
    return {
        **base,
        "execution": {**base["execution"], "mode": "execute", "elapsed_seconds": round(time.time() - started, 3)},
        "readiness_classification": readiness,
        "collection": {
            "creators_attempted": len({row.get("creator") for row in rows if row.get("creator")}),
            "creators_completed": len({row.get("creator") for row in rows if row.get("creator")}),
            "addresses_attempted": addresses_attempted,
            "addresses_completed": addresses_completed,
            "launches_covered": len(rows),
            "transactions_fetched": transactions_fetched,
        },
        "requests": {**base["requests"], "requests_used": requests_used, "actual_helius_credits_estimate": requests_used, "stopped_due_ceiling": stopped_due_ceiling},
        "raw": {"raw_responses_preserved": raw_responses_preserved, "raw_path": base["outputs"]["raw_path"]},
        "quality": quality,
        "provider": {"errors": provider_errors},
        "warnings": warnings,
    }


def _readiness(
    rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    shared_rows: list[dict[str, Any]],
    time_rows: list[dict[str, Any]],
    provider_errors: list[str],
    stopped_due_ceiling: bool,
    raw_count: int,
) -> str:
    if provider_errors or raw_count == 0:
        return READINESS_BLOCKED
    if stopped_due_ceiling:
        return READINESS_PARTIAL
    if _pct(len(candidate_rows), len(rows)) >= 25.0 and (shared_rows or time_rows):
        return READINESS_READY
    if candidate_rows:
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _base_report(
    *,
    execute: bool,
    started: float,
    scope: dict[str, Any],
    projected: dict[str, Any],
    paths: dict[str, Path],
    lookback_hours: int,
    credit_cap: int,
) -> dict[str, Any]:
    return {
        "report_id": "creator_funder_transfer_graph_pilot_v0",
        "execution": {"mode": "execute" if execute else "dry_run", "started_at": _timestamp(int(started)), "elapsed_seconds": 0.0},
        "scope": {**scope, "lookback_hours": lookback_hours},
        "requests": {
            **projected,
            "credit_cap": credit_cap,
            "request_ceiling_status": "within_cap" if projected["projected_credits"] <= credit_cap else "over_cap",
            "requests_used": 0,
            "actual_helius_credits_estimate": 0,
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
            "neutral_proxy_labels": [
                "creator_link_proxy",
                "funder_link_proxy",
                "shared_funding_proxy",
                "time_linked_funding_proxy",
                "common_funder_proxy",
                "creator_wallet_relation_proxy",
            ],
        },
    }


def _empty_quality() -> dict[str, Any]:
    return {
        "candidate_funder_coverage": {"covered_launches": 0, "total_launches": 0, "coverage_pct": 0.0},
        "shared_funder_coverage": {"launches_with_shared_funder_proxy": 0, "coverage_pct": 0.0, "shared_funder_count": 0},
        "time_linked_funding_coverage": {"launches_with_time_linked_funding_proxy": 0, "coverage_pct": 0.0, "time_linked_funding_clusters_found": 0},
        "creator_wallet_relation_coverage": {"creator_to_early_buyer_links_found": 0, "creator_to_top_holder_links_found": 0, "coverage_pct": 0.0},
        "missing_reason_counts": {},
        "confidence_distribution": {},
    }


def _warnings(
    errors: list[str],
    stopped: bool,
    rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    shared_rows: list[dict[str, Any]],
    time_rows: list[dict[str, Any]],
    raw_count: int,
) -> list[str]:
    warnings: list[str] = []
    if errors:
        warnings.append("provider_or_auth_error")
    if stopped:
        warnings.append("stopped_due_request_or_transaction_ceiling")
    if raw_count == 0:
        warnings.append("no_raw_responses_preserved")
    if not candidate_rows:
        warnings.append("no_candidate_funders_detected")
    if candidate_rows and not shared_rows:
        warnings.append("no_shared_funding_proxy_detected")
    if candidate_rows and not time_rows:
        warnings.append("no_time_linked_funding_proxy_detected")
    if _pct(len(candidate_rows), len(rows)) < 25.0:
        warnings.append("candidate_funder_coverage_below_ready_threshold")
    return warnings


def _write_reports(report: dict[str, Any], paths: dict[str, Path]) -> None:
    paths["report_dir"].mkdir(parents=True, exist_ok=True)
    (paths["report_dir"] / "creator_funder_transfer_graph_pilot_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (paths["report_dir"] / "creator_funder_transfer_graph_pilot_summary.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    quality = report.get("quality", {})
    return "\n".join(
        [
            "# Creator/Funder Transfer Graph Pilot Summary",
            "",
            f"- Readiness classification: `{report.get('readiness_classification')}`",
            f"- Execution mode: `{report['execution']['mode']}`",
            f"- Creators selected: `{report['scope']['creators_selected']}`",
            f"- Candidate funders selected: `{report['scope']['candidate_funders_selected']}`",
            f"- Launches covered: `{report['scope']['launches_covered']}`",
            f"- Requests used: `{report['requests']['requests_used']}`",
            f"- Actual Helius credits estimate: `{report['requests']['actual_helius_credits_estimate']}`",
            f"- Transactions fetched: `{report.get('collection', {}).get('transactions_fetched', 0)}`",
            f"- Raw responses preserved: `{report.get('raw', {}).get('raw_responses_preserved', 0)}`",
            f"- Candidate funder coverage: `{quality.get('candidate_funder_coverage', {})}`",
            f"- Shared funding coverage: `{quality.get('shared_funder_coverage', {})}`",
            f"- Time-linked funding coverage: `{quality.get('time_linked_funding_coverage', {})}`",
            f"- Creator-wallet relation coverage: `{quality.get('creator_wallet_relation_coverage', {})}`",
            f"- Warnings: `{report.get('warnings', [])}`",
            "",
            "No thesis, outcome comparison, validation, backtest, paper trading, live trading, optimization, grid search, or ML workflow was run.",
        ]
    ) + "\n"


def _append_raw_transaction(path: Path, address_row: dict[str, Any], tx: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "address": address_row.get("address"),
        "roles": address_row.get("roles"),
        "launch_ids": address_row.get("launch_ids"),
        "signature": _transaction_signature(tx),
        "block_time": _block_time(tx),
        "raw_json": tx,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")


def _resolve_output_paths(output_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    supplied = output_paths or {}
    raw_dir = Path(supplied.get("raw_dir", DEFAULT_RAW_DIR))
    return {
        "raw_dir": raw_dir,
        "raw_path": raw_dir / "creator_funder_transfer_graph_raw_transactions.jsonl",
        "jsonl_path": Path(supplied.get("jsonl_path", DEFAULT_JSONL_PATH)),
        "parquet_path": Path(supplied.get("parquet_path", DEFAULT_PARQUET_PATH)),
        "checkpoint_path": Path(supplied.get("checkpoint_path", DEFAULT_CHECKPOINT_PATH)),
        "report_dir": Path(supplied.get("report_dir", DEFAULT_REPORT_DIR)),
    }


def _read_csv(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    jsonl = Path(path)
    if not jsonl.exists():
        return []
    with jsonl.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _wallets_by_launch(path: Path | str, *, launch_field: str, wallet_field: str) -> dict[str, set[str]]:
    output: dict[str, set[str]] = defaultdict(set)
    for row in _read_jsonl(path):
        launch_id = row.get(launch_field)
        wallet = row.get(wallet_field)
        if launch_id and wallet:
            output[launch_id].add(wallet)
    return output


def _read_existing_raw_signatures(path: Path) -> set[str]:
    return {row.get("signature") for row in _read_jsonl(path) if row.get("signature")}


def _read_existing_raw_transactions(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


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


def _parse_iso_ts(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100), 4) if denominator else 0.0
