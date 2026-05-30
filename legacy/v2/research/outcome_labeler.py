from __future__ import annotations

from typing import Any


RUNNER_PNL_PCT = 25.0
RUNNER_MFE_PCT = 50.0
RUG_PNL_PCT = -80.0
RUG_LIQUIDITY_CHANGE_PCT = -70.0
DEAD_PNL_PCT = -25.0


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def percent_change(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return round(((end - start) / start) * 100.0, 6)


def lower_blob(*values: Any) -> str:
    return " ".join(str(value).lower() for value in values if value not in (None, ""))


def label_later_token_outcome(
    outcome: dict[str, Any] | None = None,
    trade: dict[str, Any] | None = None,
    signal_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify later outcome evidence without feeding it into decision-time fields."""
    labeled = dict(outcome) if isinstance(outcome, dict) else {}
    trade = as_dict(trade)
    signal_context = as_dict(signal_context)

    if not labeled:
        labeled = {"status": "unknown"}

    status_value = first_present(labeled.get("status"), trade.get("status"), "unknown")
    if str(status_value).lower() == "unknown" and str(trade.get("status") or "").lower() in {"open", "pending"}:
        status_value = trade.get("status")
    status = str(status_value).lower()
    labeled["status"] = status_value

    entry_price = safe_float(first_present(labeled.get("entry_price"), trade.get("entry_price")), None)
    exit_price = safe_float(
        first_present(labeled.get("exit_price"), trade.get("close_price"), trade.get("exit_price"), trade.get("current_price")),
        None,
    )
    high_price = safe_float(
        first_present(
            labeled.get("highest_price_seen"),
            labeled.get("high_price"),
            trade.get("highest_price_seen"),
            trade.get("high_price"),
        ),
        None,
    )
    pnl_pct = safe_float(first_present(labeled.get("pnl_pct"), trade.get("total_pnl_pct"), trade.get("pnl_pct")), None)
    entry_liquidity = safe_float(
        first_present(
            labeled.get("entry_liquidity_usd"),
            trade.get("entry_liquidity_usd"),
            as_dict(signal_context.get("market")).get("liquidity"),
        ),
        None,
    )
    exit_liquidity = safe_float(
        first_present(labeled.get("exit_liquidity_usd"), trade.get("exit_liquidity_usd"), trade.get("close_liquidity_usd")),
        None,
    )

    liquidity_change_pct = percent_change(entry_liquidity, exit_liquidity)
    max_favorable_excursion_pct = percent_change(entry_price, high_price)
    exit_price_change_pct = percent_change(entry_price, exit_price)
    if pnl_pct is None:
        pnl_pct = exit_price_change_pct

    if entry_price is not None:
        labeled.setdefault("entry_price", entry_price)
    if exit_price is not None:
        labeled.setdefault("exit_price", exit_price)
    if pnl_pct is not None:
        labeled["pnl_pct"] = round(pnl_pct, 6)
    if liquidity_change_pct is not None:
        labeled["liquidity_change_pct"] = liquidity_change_pct
    if max_favorable_excursion_pct is not None:
        labeled["max_favorable_excursion_pct"] = max_favorable_excursion_pct

    if status in {"open", "pending"}:
        return with_label(labeled, "open", "low", ["outcome still open or pending"])

    reasons: list[str] = []
    text = lower_blob(
        labeled.get("status"),
        labeled.get("close_reason"),
        labeled.get("exit_reason"),
        trade.get("close_reason"),
        trade.get("exit_reason"),
        trade.get("failure_reason"),
    )

    rug_text = any(word in text for word in ("rug", "drain", "drained", "honeypot", "frozen", "blacklist"))
    runner = False
    rug = False
    dead = False

    if pnl_pct is not None and pnl_pct >= RUNNER_PNL_PCT:
        runner = True
        reasons.append("profit exceeded runner threshold")
    if max_favorable_excursion_pct is not None and max_favorable_excursion_pct >= RUNNER_MFE_PCT:
        runner = True
        reasons.append("high watermark exceeded runner threshold")

    if rug_text:
        rug = True
        reasons.append("exit text indicates rug or hostile mechanics")
    if liquidity_change_pct is not None and liquidity_change_pct <= RUG_LIQUIDITY_CHANGE_PCT:
        rug = True
        reasons.append("liquidity collapse exceeded rug threshold")
    if pnl_pct is not None and pnl_pct <= RUG_PNL_PCT:
        rug = True
        reasons.append("loss exceeded rug threshold")

    if not rug and pnl_pct is not None and pnl_pct <= DEAD_PNL_PCT:
        dead = True
        reasons.append("loss exceeded dead-token threshold")
    if not rug and "dead" in text:
        dead = True
        reasons.append("exit text indicates dead token")

    if rug:
        outcome_type = "rug"
        confidence = "high" if rug_text or liquidity_change_pct is not None else "medium"
    elif runner:
        outcome_type = "runner"
        confidence = "high" if pnl_pct is not None or max_favorable_excursion_pct is not None else "medium"
    elif dead:
        outcome_type = "dead"
        confidence = "medium"
    elif pnl_pct is not None and pnl_pct < 0:
        outcome_type = "loser"
        confidence = "medium"
        reasons.append("negative outcome without rug/dead evidence")
    elif pnl_pct is not None:
        outcome_type = "flat"
        confidence = "medium"
        reasons.append("evaluated outcome stayed below runner threshold")
    elif status in {"unknown", ""} and pnl_pct is None:
        outcome_type = "unknown"
        confidence = "low"
        reasons.append("no later outcome evidence")
    else:
        outcome_type = "unknown"
        confidence = "low"
        reasons.append("outcome evidence did not meet a classification threshold")

    return with_label(labeled, outcome_type, confidence, reasons)


def with_label(row: dict[str, Any], outcome_type: str, confidence: str, reasons: list[str]) -> dict[str, Any]:
    row["outcome_type"] = outcome_type
    row["runner"] = outcome_type == "runner"
    row["rug"] = outcome_type == "rug"
    row["dead"] = outcome_type == "dead"
    row["label_confidence"] = confidence
    row["classification_reasons"] = reasons
    return row
