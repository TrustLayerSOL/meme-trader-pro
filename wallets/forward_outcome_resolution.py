from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from research.outcome_linker import DEFAULT_EVALUATION_WINDOWS
from research.outcome_linker import build_later_outcome_from_snapshots
from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import empty_window_labels
from wallets.wallet_evidence_models import safe_float


MODE = "FORWARD_OUTCOME_RESOLUTION_REVIEW_ONLY"
VERSION = "forward_outcome_resolution.v1"
SOURCE = "forward_market_context_snapshots"
KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser", "flat"}


def is_forward_evidence(row: dict[str, Any]) -> bool:
    if row.get("forward_observation") is True:
        return True
    if str(row.get("collection_source") or "") == "forward_wallet_activity":
        return True
    return "forward_current_activity" in (row.get("risk_flags") or [])


def row_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def row_time(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("timestamp"), None)


def row_id(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("wallet") or ""),
        str(row.get("transaction_signature") or ""),
        row_mint(row),
        str(row.get("observed_action") or ""),
        str(row.get("timestamp") or ""),
    ]
    return "|".join(parts)


def normalize_snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    mint = str(row.get("mint") or row.get("token_mint") or "").strip()
    timestamp = safe_float(row.get("time") or row.get("timestamp"), None)
    if not mint or timestamp is None:
        return None
    return {
        "time": timestamp,
        "mint": mint,
        "source": row.get("source") or SOURCE,
        "price": safe_float(row.get("price"), None),
        "liquidity": safe_float(row.get("liquidity"), None),
        "market_cap": safe_float(row.get("market_cap"), None),
        "risk_label": row.get("risk_label"),
    }


def snapshots_by_mint(snapshots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshots or []:
        normalized = normalize_snapshot(row)
        if normalized is None:
            continue
        grouped[normalized["mint"]].append(normalized)
    for rows in grouped.values():
        rows.sort(key=lambda item: safe_float(item.get("time"), 0.0) or 0.0)
    return dict(grouped)


def entry_anchor(row: dict[str, Any]) -> dict[str, Any] | None:
    context = as_dict(row.get("estimated_entry_context"))
    event_time = row_time(row)
    price = safe_float(context.get("price"), None)
    if event_time is None or price in (None, 0):
        return None
    return {
        "time": event_time,
        "mint": row_mint(row),
        "source": "forward_entry_context_anchor",
        "price": price,
        "liquidity": safe_float(context.get("liquidity"), None),
        "market_cap": safe_float(context.get("market_cap"), None),
        "risk_label": context.get("risk_label"),
    }


def pending_window(mint: str, signal_time: float, label: str, seconds: int, generated_at: float) -> dict[str, Any]:
    return {
        "status": "pending_forward_window",
        "source": SOURCE,
        "mint": mint,
        "signal_time": signal_time,
        "window": label,
        "evaluation_horizon_seconds": seconds,
        "matures_at": signal_time + seconds,
        "generated_at": generated_at,
        "outcome_type": "unknown",
        "runner": False,
        "rug": False,
        "dead": False,
        "label_confidence": "low",
        "classification_reasons": ["window has not matured yet"],
    }


def unknown_window(mint: str, signal_time: float, label: str, seconds: int, reason: str) -> dict[str, Any]:
    row = empty_window_labels().get(label, {"outcome_type": "unknown", "runner": False, "rug": False, "dead": False})
    return {
        **row,
        "status": "unknown",
        "source": SOURCE,
        "mint": mint,
        "signal_time": signal_time,
        "window": label,
        "evaluation_horizon_seconds": seconds,
        "label_confidence": "low",
        "classification_reasons": [reason],
    }


def is_known(outcome: dict[str, Any]) -> bool:
    return str(as_dict(outcome).get("outcome_type") or "").lower() in KNOWN_OUTCOMES


def resolve_windows(
    *,
    mint: str,
    signal_time: float,
    entry: dict[str, Any],
    snapshots: list[dict[str, Any]],
    generated_at: float,
) -> dict[str, dict[str, Any]]:
    windows: dict[str, dict[str, Any]] = {}
    for label, seconds in DEFAULT_EVALUATION_WINDOWS:
        if generated_at < signal_time + seconds:
            windows[label] = pending_window(mint, signal_time, label, seconds, generated_at)
            continue
        end_time = signal_time + seconds
        later = [
            row for row in snapshots
            if (safe_float(row.get("time"), 0.0) or 0.0) >= signal_time
            and (safe_float(row.get("time"), 0.0) or 0.0) <= end_time
        ]
        if not later:
            windows[label] = unknown_window(mint, signal_time, label, seconds, "missing later forward market snapshots")
            continue
        outcome = build_later_outcome_from_snapshots(
            mint=mint,
            signal_time=signal_time,
            snapshots=[entry, *later],
            horizon_seconds=seconds,
        )
        outcome["source"] = SOURCE
        outcome["window"] = label
        outcome["forward_capture"] = True
        outcome["snapshot_sources"] = sorted({str(row.get("source") or "") for row in [entry, *later] if row.get("source")})
        windows[label] = outcome
    return windows


def select_overall_outcome(windows: dict[str, Any]) -> dict[str, Any]:
    fifteens = as_dict(windows.get("15m"))
    if is_known(fifteens):
        overall = dict(fifteens)
    else:
        known = next((as_dict(row) for row in windows.values() if is_known(as_dict(row))), {})
        overall = dict(known) if known else {"status": "unknown", "source": SOURCE, "outcome_type": "unknown"}
    overall["source"] = SOURCE
    overall["windows"] = windows
    return overall


def build_record(row: dict[str, Any], snapshots_for_mint: list[dict[str, Any]], *, generated_at: float) -> dict[str, Any]:
    mint = row_mint(row)
    signal_time = row_time(row)
    base = {
        "version": VERSION,
        "event_id": row_id(row),
        "wallet": row.get("wallet"),
        "token_mint": mint,
        "observed_action": row.get("observed_action"),
        "signal_time": signal_time,
        "transaction_signature": row.get("transaction_signature"),
        "status": "pending_forward_outcome_resolution",
        "decision_context": {
            "estimated_entry_context": as_dict(row.get("estimated_entry_context")),
            "risk_flags": list(row.get("risk_flags") or []),
            "collection_source": row.get("collection_source"),
            "forward_observation": bool(row.get("forward_observation")),
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
        "block_reasons": [],
    }
    if not mint or signal_time is None:
        base["status"] = "blocked_missing_signal_identity"
        base["block_reasons"] = ["missing_mint_or_signal_time"]
        base["outcome_window_labels"] = empty_window_labels()
        base["later_token_outcome"] = {"source": SOURCE, "outcome_type": "unknown", "windows": base["outcome_window_labels"]}
        return base
    entry = entry_anchor(row)
    if entry is None:
        base["status"] = "blocked_missing_forward_entry_context"
        base["block_reasons"] = ["missing_forward_entry_price"]
        base["outcome_window_labels"] = empty_window_labels()
        base["later_token_outcome"] = {"source": SOURCE, "outcome_type": "unknown", "windows": base["outcome_window_labels"]}
        return base

    windows = resolve_windows(
        mint=mint,
        signal_time=signal_time,
        entry=entry,
        snapshots=snapshots_for_mint,
        generated_at=generated_at,
    )
    base["outcome_window_labels"] = windows
    base["later_token_outcome"] = select_overall_outcome(windows)
    base["snapshots_available"] = len(snapshots_for_mint)
    if is_known(as_dict(windows.get("15m"))) or any(is_known(as_dict(window)) for window in windows.values()):
        base["status"] = "forward_outcome_labeled"
    elif any(str(as_dict(window).get("status") or "") == "pending_forward_window" for window in windows.values()):
        base["status"] = "pending_forward_outcome_windows"
    else:
        base["status"] = "forward_outcome_unknown"
    return base


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in records)
    window_counts = Counter()
    known_15m = 0
    pending_windows = 0
    for record in records:
        windows = as_dict(record.get("outcome_window_labels"))
        if is_known(as_dict(windows.get("15m"))):
            known_15m += 1
        for window in windows.values():
            window_row = as_dict(window)
            if str(window_row.get("status") or "") == "pending_forward_window":
                pending_windows += 1
            window_counts[str(window_row.get("outcome_type") or "unknown")] += 1
    return {
        "records_scanned": len(records),
        "known_15m_outcomes": known_15m,
        "records_with_any_known_window": sum(1 for row in records if any(is_known(as_dict(window)) for window in as_dict(row.get("outcome_window_labels")).values())),
        "pending_windows": pending_windows,
        "status_counts": dict(sorted(statuses.items())),
        "window_outcome_counts": dict(sorted(window_counts.items())),
        "wallets_affected": len({row.get("wallet") for row in records if row.get("wallet")}),
        "tokens_affected": len({row.get("token_mint") for row in records if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_daily_forward_calibration_report(
    *,
    records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records or []:
        timestamp = safe_float(row.get("signal_time"), None)
        if timestamp is None:
            day = "unknown"
        else:
            day = time.strftime("%Y-%m-%d", time.localtime(timestamp))
        grouped[day].append(row)
    days = []
    for day, rows in sorted(grouped.items()):
        counts = Counter(str(as_dict(as_dict(row.get("outcome_window_labels")).get("15m")).get("outcome_type") or "unknown") for row in rows)
        days.append(
            {
                "date": day,
                "records": len(rows),
                "known_15m_outcomes": sum(counts.get(label, 0) for label in KNOWN_OUTCOMES),
                "outcomes_15m": dict(sorted(counts.items())),
                "wallets": len({row.get("wallet") for row in rows if row.get("wallet")}),
                "tokens": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
            }
        )
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": "FORWARD_DAILY_CALIBRATION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "summary": {
            "days": len(days),
            "records": sum(day["records"] for day in days),
            "known_15m_outcomes": sum(day["known_15m_outcomes"] for day in days),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "days": days,
    }


def render_daily_forward_calibration_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MemeTraderPro Forward Calibration",
        "",
        "Review-only daily summary from current wallet activity and forward market-context snapshots.",
        "",
        "| Date | Records | Known 15m | 15m Outcomes | Wallets | Tokens |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in report.get("days") or []:
        outcomes = ", ".join(f"{key}: {value}" for key, value in as_dict(row.get("outcomes_15m")).items()) or "-"
        lines.append(
            f"| {row.get('date')} | {row.get('records')} | {row.get('known_15m_outcomes')} | {outcomes} | {row.get('wallets')} | {row.get('tokens')} |"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_forward_outcome_resolution_report(
    *,
    evidence_records: list[dict[str, Any]],
    market_snapshots: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped_snapshots = snapshots_by_mint(market_snapshots)
    forward_rows = [row for row in evidence_records or [] if isinstance(row, dict) and is_forward_evidence(row)]
    records = [
        build_record(row, grouped_snapshots.get(row_mint(row), []), generated_at=generated_at)
        for row in forward_rows
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(records),
        "records": records,
        "daily_calibration": build_daily_forward_calibration_report(records=records, generated_at=generated_at),
        "operator_note": (
            "Forward outcomes are evaluation-only. They use market snapshots collected after current wallet activity "
            "and must not be copied into decision-time context, wallet trust, or live execution logic."
        ),
    }
