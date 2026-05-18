from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from research.outcome_labeler import label_later_token_outcome
from research.outcome_linker import (
    build_later_outcome_from_snapshots,
    build_windowed_outcomes_from_snapshots,
)
from wallets.wallet_evidence_models import (
    as_dict,
    empty_window_labels,
    evidence_confidence,
    missing_fields_for_evidence,
    replay_outcome_candidates_by_mint,
    replay_outcome_is_known,
    safe_float,
)


ENRICHMENT_VERSION = "wallet_evidence_enrichment.v1"
MODE = "WALLET_EVIDENCE_ENRICHMENT_REVIEW_ONLY"
MAX_REPLAY_FALLBACK_DELAY_SECONDS = 3600.0


def normalize_market_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = parse_json_dict(row.get("payload_json"))
    context = parse_json_dict(row.get("context"))
    mint = str(row.get("mint") or payload.get("mint") or "").strip()
    return {
        "mint": mint,
        "time": safe_float(row.get("time"), None),
        "source": row.get("source") or "market_snapshot",
        "price": first_float(row.get("price"), payload.get("price"), payload.get("price_usd")),
        "liquidity": first_float(
            row.get("liquidity"),
            payload.get("liquidity"),
            payload.get("liquidity_usd"),
            as_dict(payload.get("liquidity")).get("usd"),
        ),
        "market_cap": first_float(
            row.get("market_cap"),
            payload.get("market_cap"),
            payload.get("marketCap"),
            payload.get("fdv"),
            payload.get("fdv_usd"),
        ),
        "token_age_seconds": first_float(
            row.get("token_age_seconds"),
            payload.get("token_age_seconds"),
            payload.get("age_seconds"),
            context.get("token_age_seconds"),
        ),
        "risk_label": row.get("risk_label") or payload.get("risk_label"),
    }


def parse_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def first_float(*values: Any) -> float | None:
    for value in values:
        number = safe_float(value, None)
        if number is not None:
            return number
    return None


def group_snapshots_by_mint(market_snapshots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in market_snapshots or []:
        if not isinstance(row, dict):
            continue
        snapshot = normalize_market_snapshot(row)
        if not snapshot["mint"] or snapshot["time"] is None:
            continue
        grouped[snapshot["mint"]].append(snapshot)
    for rows in grouped.values():
        rows.sort(key=lambda item: safe_float(item.get("time"), 0.0) or 0.0)
    return dict(grouped)


def prior_snapshot(rows: list[dict[str, Any]], timestamp: float | None) -> dict[str, Any] | None:
    if timestamp is None:
        return None
    candidate = None
    for row in rows:
        row_time = safe_float(row.get("time"), None)
        if row_time is None:
            continue
        if row_time <= timestamp:
            candidate = row
        else:
            break
    return candidate


def known_outcome(outcome: dict[str, Any]) -> bool:
    return as_dict(outcome).get("outcome_type") not in (None, "", "unknown")


def known_window_labels(windows: dict[str, Any]) -> bool:
    return any(known_outcome(as_dict(row)) for row in as_dict(windows).values())


def snapshot_entry_context(snapshot: dict[str, Any], timestamp: float) -> dict[str, Any]:
    snapshot_time = safe_float(snapshot.get("time"), None)
    return {
        "price": safe_float(snapshot.get("price"), None),
        "market_cap": safe_float(snapshot.get("market_cap"), None),
        "liquidity": safe_float(snapshot.get("liquidity"), None),
        "token_age_seconds": safe_float(snapshot.get("token_age_seconds"), None),
        "source": snapshot.get("source") or "market_snapshot",
        "snapshot_time": snapshot_time,
        "seconds_after_snapshot": round(timestamp - snapshot_time, 6) if snapshot_time is not None else None,
        "decision_time_safe": True,
    }


def status_for_row(row: dict[str, Any], notes: list[str]) -> str:
    has_entry = as_dict(row.get("estimated_entry_context")).get("price") not in (None, "")
    has_later = known_outcome(as_dict(row.get("later_token_outcome")))
    has_windows = known_window_labels(as_dict(row.get("outcome_window_labels")))
    if has_entry and (has_later or has_windows):
        return "ENRICHED"
    if not has_entry:
        return "MISSING_MARKET_CONTEXT"
    if not has_later and not has_windows:
        return "MISSING_OUTCOME_LABELS"
    if notes:
        return "PARTIAL_ENRICHMENT"
    return "PARTIAL_ENRICHMENT"


def select_replay_fallback_outcome(
    *,
    candidates: list[dict[str, Any]],
    evidence_timestamp: float | None,
    max_delay_seconds: float = MAX_REPLAY_FALLBACK_DELAY_SECONDS,
) -> dict[str, Any] | None:
    if evidence_timestamp is None:
        return None
    eligible = []
    for candidate in candidates or []:
        if not replay_outcome_is_known(candidate):
            continue
        signal_time = safe_float(candidate.get("signal_timestamp"), None)
        if signal_time is None:
            continue
        delay = signal_time - evidence_timestamp
        if 0 <= delay <= max(0.0, float(max_delay_seconds)):
            eligible.append((delay, candidate))
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0])
    return eligible[0][1]


def context_price(row: dict[str, Any]) -> float | None:
    context = as_dict(row.get("estimated_entry_context"))
    return safe_float(context.get("price"), None) or safe_float(context.get("execution_price_quote"), None)


def context_quote_mint(row: dict[str, Any]) -> str:
    context = as_dict(row.get("estimated_entry_context"))
    return str(row.get("quote_mint") or context.get("quote_mint") or "").strip()


def apply_wallet_lifecycle_exit_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        wallet = str(row.get("wallet") or "").strip()
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if wallet and mint:
            grouped[(wallet, mint)].append(row)

    for lifecycle_rows in grouped.values():
        lifecycle_rows.sort(key=lambda item: safe_float(item.get("timestamp"), 0.0) or 0.0)
        sell_rows = [
            row for row in lifecycle_rows
            if row.get("observed_action") == "sell"
            and context_price(row) not in (None, 0)
            and safe_float(row.get("timestamp"), None) is not None
        ]
        for row in lifecycle_rows:
            if row.get("observed_action") != "buy":
                continue
            if known_outcome(as_dict(row.get("later_token_outcome"))):
                continue
            entry_price = context_price(row)
            entry_time = safe_float(row.get("timestamp"), None)
            if entry_price in (None, 0) or entry_time is None:
                continue
            exit_row = next(
                (
                    sell for sell in sell_rows
                    if (safe_float(sell.get("timestamp"), 0.0) or 0.0) >= entry_time
                ),
                None,
            )
            if exit_row is None:
                continue
            exit_context = as_dict(exit_row.get("estimated_entry_context"))
            exit_price = safe_float(exit_context.get("price"), None)
            if exit_price in (None, 0):
                buy_quote = context_quote_mint(row)
                sell_quote = context_quote_mint(exit_row)
                if buy_quote and buy_quote == sell_quote:
                    exit_price = safe_float(exit_context.get("execution_price_quote"), None)
            exit_time = safe_float(exit_row.get("timestamp"), None)
            if exit_price in (None, 0) or exit_time is None:
                continue
            entry_context = as_dict(row.get("estimated_entry_context"))
            price_source = "wallet_lifecycle_sell_context"
            if safe_float(exit_context.get("price"), None) in (None, 0):
                price_source = "wallet_lifecycle_quote_execution_context"
            row["estimated_exit_context"] = {
                **as_dict(row.get("estimated_exit_context")),
                "price": exit_price,
                "market_cap": safe_float(exit_context.get("market_cap"), None),
                "liquidity": safe_float(exit_context.get("liquidity"), None),
                "quote_mint": context_quote_mint(exit_row) or None,
                "source": price_source,
                "sell_transaction_signature": exit_row.get("transaction_signature"),
                "exit_timestamp": exit_time,
                "hold_seconds": round(exit_time - entry_time, 6),
                "decision_time_safe": False,
                "future_outcome_separated": True,
            }
            outcome = label_later_token_outcome(outcome={
                "status": "wallet_exit_observed",
                "source": "wallet_lifecycle_exit",
                "mint": row.get("token_mint") or row.get("mint"),
                "signal_time": entry_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "entry_liquidity_usd": safe_float(entry_context.get("liquidity"), None),
                "exit_liquidity_usd": safe_float(exit_context.get("liquidity"), None),
                "entry_transaction_signature": row.get("transaction_signature"),
                "exit_transaction_signature": exit_row.get("transaction_signature"),
                "hold_seconds": round(exit_time - entry_time, 6),
            })
            if known_outcome(outcome):
                row["later_token_outcome"] = outcome
                row["enrichment_notes"] = [
                    note for note in row.get("enrichment_notes", [])
                    if note not in {"no known snapshot outcome labels", "no later token outcome"}
                ]
            row["enrichment_status"] = status_for_row(row, as_dict({"notes": row.get("enrichment_notes")}).get("notes") or [])
            row["missing_fields"] = missing_fields_for_evidence(row)
            row["confidence_score"] = evidence_confidence(row)
    return rows


def enrich_evidence_record(
    row: dict[str, Any],
    *,
    market_by_mint: dict[str, list[dict[str, Any]]],
    replay_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    enriched = dict(row)
    mint = str(enriched.get("token_mint") or enriched.get("mint") or "").strip()
    timestamp = safe_float(enriched.get("timestamp"), None)
    notes: list[str] = []
    snapshots = market_by_mint.get(mint, [])

    if timestamp is None:
        notes.append("missing evidence timestamp")

    if mint and timestamp is not None:
        entry_snapshot = prior_snapshot(snapshots, timestamp)
        if entry_snapshot:
            current_entry = as_dict(enriched.get("estimated_entry_context"))
            enriched["estimated_entry_context"] = {
                **current_entry,
                **snapshot_entry_context(entry_snapshot, timestamp),
            }
        else:
            notes.append("no prior market snapshot")

        if snapshots:
            windows = build_windowed_outcomes_from_snapshots(
                mint=mint,
                signal_time=timestamp,
                snapshots=snapshots,
            )
            if known_window_labels(windows):
                enriched["outcome_window_labels"] = windows
                later = build_later_outcome_from_snapshots(
                    mint=mint,
                    signal_time=timestamp,
                    snapshots=snapshots,
                )
                enriched["later_token_outcome"] = later
            else:
                notes.append("no known snapshot outcome labels")

    replay_outcome = select_replay_fallback_outcome(
        candidates=replay_by_mint.get(mint, []),
        evidence_timestamp=timestamp,
    )
    if replay_outcome and not known_outcome(as_dict(enriched.get("later_token_outcome"))):
        enriched["later_token_outcome"] = replay_outcome
        enriched["outcome_window_labels"] = as_dict(replay_outcome.get("windows")) or empty_window_labels()

    if not known_outcome(as_dict(enriched.get("later_token_outcome"))):
        notes.append("no later token outcome")
    if not known_window_labels(as_dict(enriched.get("outcome_window_labels"))):
        enriched["outcome_window_labels"] = as_dict(enriched.get("outcome_window_labels")) or empty_window_labels()

    enriched["enrichment_version"] = ENRICHMENT_VERSION
    enriched["enrichment_notes"] = sorted(set(notes))
    enriched["enrichment_status"] = status_for_row(enriched, notes)
    enriched["missing_fields"] = missing_fields_for_evidence(enriched)
    enriched["confidence_score"] = evidence_confidence(enriched)
    return enriched


def build_wallet_evidence_enrichment_report(
    *,
    evidence_records: list[dict[str, Any]],
    market_snapshots: list[dict[str, Any]],
    replay_events: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    market_by_mint = group_snapshots_by_mint(market_snapshots)
    replay_by_mint = replay_outcome_candidates_by_mint(replay_events or [])
    rows = [
        enrich_evidence_record(row, market_by_mint=market_by_mint, replay_by_mint=replay_by_mint)
        for row in evidence_records or []
        if isinstance(row, dict)
    ]
    rows = apply_wallet_lifecycle_exit_outcomes(rows)
    summary = summarize_enriched_rows(rows)
    summary["market_mints_with_snapshots"] = len(market_by_mint)
    summary["input_market_snapshots"] = sum(len(items) for items in market_by_mint.values())
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "enrichment_version": ENRICHMENT_VERSION,
        "summary": summary,
        "evidence_records": rows,
    }


def summarize_enriched_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(row.get("enrichment_status") or "") for row in rows]
    return {
        "total_evidence_rows": len(rows),
        "unique_wallets": len({row.get("wallet") for row in rows if row.get("wallet")}),
        "unique_mints": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        "enriched_rows": statuses.count("ENRICHED"),
        "partial_enrichment_rows": statuses.count("PARTIAL_ENRICHMENT"),
        "missing_market_context_rows": statuses.count("MISSING_MARKET_CONTEXT"),
        "missing_outcome_label_rows": statuses.count("MISSING_OUTCOME_LABELS"),
        "rows_with_entry_context": sum(
            1 for row in rows if as_dict(row.get("estimated_entry_context")).get("price") not in (None, "")
        ),
        "rows_with_known_outcome": sum(1 for row in rows if known_outcome(as_dict(row.get("later_token_outcome")))),
        "rows_with_window_labels": sum(1 for row in rows if known_window_labels(as_dict(row.get("outcome_window_labels")))),
        "runner_rows": sum(1 for row in rows if as_dict(row.get("later_token_outcome")).get("runner")),
        "rug_rows": sum(1 for row in rows if as_dict(row.get("later_token_outcome")).get("rug")),
    }


def write_wallet_evidence_enrichment_outputs(
    report: dict[str, Any],
    *,
    report_path: Path,
    evidence_path: Path,
    snapshot_dir: Path,
    generated_at: float | None = None,
) -> dict[str, Path]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(generated_at))
    snapshot_path = snapshot_dir / f"wallet_evidence_enrichment_{timestamp}.json"
    for path in (report_path, evidence_path, snapshot_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    snapshot_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    rows = report.get("evidence_records") if isinstance(report.get("evidence_records"), list) else []
    with evidence_path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "report_path": report_path,
        "evidence_path": evidence_path,
        "snapshot_path": snapshot_path,
    }
