from __future__ import annotations

import time
from collections import Counter
from typing import Any


REVIEW_ACTIONS = {"PROMOTION_REVIEW", "DEMOTION_REVIEW", "KEEP_TRUSTED"}
MIN_LEDGER_KNOWN_OUTCOMES = 20


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_action(row: dict[str, Any] | None) -> str:
    recommendation = as_dict(as_dict(row).get("recommendation"))
    return str(recommendation.get("action") or "HOLD_MORE_DATA")


def quant_wallets(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("wallets") if isinstance(report.get("wallets"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            out[wallet] = row
    return out


def ledger_wallets(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("wallets")
    if isinstance(rows, dict):
        return {str(wallet): row for wallet, row in rows.items() if isinstance(row, dict)}
    if isinstance(rows, list):
        return {str(row.get("wallet")): row for row in rows if isinstance(row, dict) and row.get("wallet")}
    return {}


def compare_wallet_row(
    wallet: str,
    quant_row: dict[str, Any] | None,
    ledger_row: dict[str, Any] | None,
) -> dict[str, Any]:
    quant_row = quant_row if isinstance(quant_row, dict) else None
    ledger_row = ledger_row if isinstance(ledger_row, dict) else None
    quant_action = normalize_action(quant_row)
    ledger_action = normalize_action(ledger_row)
    known_outcomes = safe_int(as_dict(ledger_row).get("known_outcomes"))
    reasons: list[str] = []

    if quant_row is None:
        status = "LEDGER_ONLY"
        reasons.append("wallet exists in outcome ledger but not in wallet quant report")
    elif ledger_row is None:
        status = "QUANT_ONLY"
        reasons.append("wallet exists in wallet quant report but has no unified outcome ledger row")
    elif known_outcomes < MIN_LEDGER_KNOWN_OUTCOMES and quant_action in REVIEW_ACTIONS:
        status = "QUANT_SIGNAL_UNCONFIRMED"
        reasons.append("outcome ledger has too little known evidence")
    elif quant_action == "HOLD_MORE_DATA" and ledger_action == "HOLD_MORE_DATA":
        status = "HOLD_MORE_DATA"
        reasons.append("both sources lack decisive review evidence")
    elif quant_action == ledger_action:
        status = "AGREEMENT"
        reasons.append("quant report and outcome ledger recommend the same action")
    elif quant_action in REVIEW_ACTIONS and ledger_action in REVIEW_ACTIONS:
        status = "CONFLICT"
        reasons.append("quant report and outcome ledger recommend different review actions")
    elif ledger_action in REVIEW_ACTIONS and quant_action == "HOLD_MORE_DATA":
        status = "LEDGER_STRONGER_SIGNAL"
        reasons.append("outcome ledger has stronger review evidence than older quant report")
    elif quant_action in REVIEW_ACTIONS and ledger_action == "HOLD_MORE_DATA":
        status = "QUANT_SIGNAL_UNCONFIRMED"
        reasons.append("quant report has review signal but outcome ledger still says hold more data")
    else:
        status = "HOLD_MORE_DATA"
        reasons.append("both sources lack decisive review evidence")

    return {
        "wallet": wallet,
        "comparison_status": status,
        "review_only": True,
        "quant": {
            "present": quant_row is not None,
            "tier": as_dict(quant_row).get("tier"),
            "action": quant_action,
            "sample_quality": as_dict(quant_row).get("sample_quality"),
            "paper_watch_entries": safe_int(as_dict(quant_row).get("paper_watch_entries")),
            "paper_watch_closed": safe_int(as_dict(quant_row).get("paper_watch_closed")),
            "paper_watch_expectancy": as_dict(quant_row).get("paper_watch_expectancy"),
            "behavior_score": as_dict(as_dict(quant_row).get("behavior_score")).get("score"),
        },
        "ledger": {
            "present": ledger_row is not None,
            "action": ledger_action,
            "known_outcomes": known_outcomes,
            "runner_participation_rate": as_dict(ledger_row).get("runner_participation_rate"),
            "rug_participation_rate": as_dict(ledger_row).get("rug_participation_rate"),
            "average_pnl_after_signal": as_dict(ledger_row).get("average_pnl_after_signal"),
            "confidence": as_dict(ledger_row).get("confidence"),
        },
        "reasons": reasons,
    }


def compare_wallet_reports(
    quant_report: dict[str, Any],
    outcome_ledger: dict[str, Any],
) -> dict[str, Any]:
    quant = quant_wallets(as_dict(quant_report))
    ledger = ledger_wallets(as_dict(outcome_ledger))
    all_wallets = sorted(set(quant) | set(ledger))
    rows = [compare_wallet_row(wallet, quant.get(wallet), ledger.get(wallet)) for wallet in all_wallets]
    rows.sort(key=lambda row: (status_rank(row["comparison_status"]), row["wallet"]), reverse=True)
    comparison_counts = Counter(row["comparison_status"] for row in rows)

    return {
        "generated_at": time.time(),
        "mode": "WALLET_BASELINE_COMPARISON_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "wallets": len(all_wallets),
            "quant_wallets": len(quant),
            "ledger_wallets": len(ledger),
            "overlap": len(set(quant) & set(ledger)),
            "quant_only": len(set(quant) - set(ledger)),
            "ledger_only": len(set(ledger) - set(quant)),
        },
        "comparison_counts": dict(comparison_counts),
        "wallets": rows,
    }


def status_rank(status: str) -> int:
    return {
        "CONFLICT": 80,
        "QUANT_SIGNAL_UNCONFIRMED": 70,
        "LEDGER_STRONGER_SIGNAL": 60,
        "AGREEMENT": 50,
        "QUANT_ONLY": 40,
        "LEDGER_ONLY": 30,
        "HOLD_MORE_DATA": 20,
    }.get(str(status), 0)
