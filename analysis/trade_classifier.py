"""Heuristic classifier for closed paper trades. Tags are tentative until paired with richer context."""

from __future__ import annotations


from analysis.trade_reason_codes import EXIT_ATTRIBUTION, POSTMORTEM_CLASSIFICATION_TAGS


def safe_float(value, default=None):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _norm_txt(*parts: Optional[str]) -> str:
    return " ".join(str(p) for p in parts if p).lower()


def _pnl_positive(trade: dict) -> bool:
    pnl = safe_float(trade.get("total_pnl"), safe_float(trade.get("pnl")))
    return pnl is not None and pnl > 0


def classify_closed_trade(trade: dict, decision_hints: Optional[dict] = None) -> Tuple[List[str], Dict[str, object]]:
    """
    Return ([classification_tags...], auxiliary dict with exit_attribution, notes).

    Uses text heuristics on reasons and simple price/volume features; ambiguous cases get fewer tags.
    """
    decision_hints = decision_hints or {}
    notes: List[str] = []

    tags: List[str] = []
    outcome = "winner" if _pnl_positive(trade) else "loser"
    tags.append(outcome)

    entry_reason = trade.get("entry_reason") or trade.get("reason") or ""
    exit_reason = trade.get("exit_reason") or trade.get("close_reason") or ""

    sells = trade.get("sells") if isinstance(trade.get("sells"), list) else []
    combined = _norm_txt(entry_reason, exit_reason, *[str((s or {}).get("reason", "")) for s in sells])

    # Exit path
    xpct = classify_exit_paths(exit_reason, sells)
    tags.extend([t for t in xpct["classifications_from_exit"] if t in POSTMORTEM_CLASSIFICATION_TAGS])

    holder_note = classify_holder_issue(trade, decision_hints)
    if holder_note:
        tags.append("holder concentration issue")
        notes.append(holder_note)

    if "rug" in combined or "honeypot" in combined or "remove liquidity" in combined:
        tags.append("rug event")
        notes.append("rug-like keyword hit in textual reasons")

    wc = classify_weak_cluster(trade)
    if wc:
        tags.append("weak cluster")
        notes.append(wc)

    if "confirmation_block" in _norm_txt(entry_reason) or "past confirmation" in combined:
        tags.append("late signal")
        notes.append("confirmation/late wording in entry path")

    if _liquidity_collapse_candidate(trade, combined):
        tags.append("liquidity collapse")
        notes.append("material liquidity decline or wording")

    if _delayed_execution_estimate(trade) is True:
        tags.append("delayed execution issue")
        notes.append("wide quoted vs executed entry disparity")

    if _social_hype_miss(combined, outcome):
        tags.append("social hype failure")
        notes.append("strong social wording but losing outcome")

    if _volume_exhaustion(trade):
        tags.append("volume exhaustion")
        notes.append("thin volume / flat movement proxy")

    if _fake_breakout(trade):
        tags.append("fake breakout")
        notes.append("brief pump then hard stop-like exit")

    if _momentum_fade(trade):
        tags.append("momentum fade")
        notes.append("strong high vs close multiple")

    tags = sanitize_tags(dedupe_preserve(tags))

    return tags, {"exit_detail": xpct, "classification_notes": notes}


def classify_exit_paths(
    exit_reason: Optional[str],
    sells: Sequence[dict],
) -> Dict[str, object]:
    """Infer exit attribution plus post-mortem exit tags."""
    er = _norm_txt(exit_reason)

    classifications_from_exit: List[str] = []

    sells = sells or []
    sell_reason_text = [_norm_txt((s or {}).get("reason")) for s in sells]

    trailing = any("trail" in sr for sr in sell_reason_text)
    tp_touch = er.startswith("take_profit") or "take_profit" in er or any(
        "take_profit" in sr for sr in sell_reason_text
    )
    hard_stop = "hard_stop" in er or "stop_loss" in er or "manual" in er
    wd = "watchdog" in er

    if trailing:
        classifications_from_exit.extend(["take-profit exit", "trailing-stop exit"])
        primary = "trailing stop"
    elif tp_touch:
        classifications_from_exit.append("take-profit exit")
        primary = "fixed TP"
    elif hard_stop or wd:
        classifications_from_exit.append("stop-loss exit")
        primary = "emergency exit"
    else:
        primary = "timeout exit"

    return {
        "primary_exit_attribution": primary if primary in EXIT_ATTRIBUTION else "timeout exit",
        "classifications_from_exit": dedupe_preserve(classifications_from_exit),
    }


def classify_holder_issue(trade: dict, hints: dict) -> Optional[str]:
    rl = hints.get("holder_risk_label") if isinstance(hints, dict) else None
    if rl == "DANGER":
        return "decision_hints: holder_cluster DANGER"
    rr = hints.get("holder_concentration_risk") if isinstance(hints, dict) else None
    if rr == "DANGER":
        return "decision_hints: holder concentration DANGER"
    return None


def classify_weak_cluster(trade: dict) -> Optional[str]:
    wallets = trade.get("wallets") if isinstance(trade.get("wallets"), list) else []
    wc = trade.get("wallet_count")
    try:
        n = int(wc) if wc is not None else len(wallets)
    except (TypeError, ValueError):
        n = len(wallets)
    if n <= 1:
        return f"wallet_count={n}"
    return None


def _liquidity_collapse_candidate(trade: dict, combined: str) -> bool:
    entry_liq = safe_float(trade.get("entry_liquidity_usd"), safe_float(trade.get("liquidity_usd")))
    cur_liq = safe_float(trade.get("current_liquidity_usd"))
    if entry_liq and cur_liq and entry_liq > 0:
        pct = ((cur_liq - entry_liq) / entry_liq) * 100
        if pct <= -35:
            return True
    if "liquidity" in combined and ("drain" in combined or "-35" in combined or "drained" in combined):
        return True
    return False


def _delayed_execution_estimate(trade: dict) -> Optional[bool]:
    """True if simulated entry materially worse than quote reference."""
    q = safe_float(trade.get("quoted_entry_price"))
    e = safe_float(trade.get("entry_price"))
    if not q or not e or q <= 0:
        return None
    slip_pct = abs((e - q) / q) * 100
    return slip_pct > 5.0


def _social_hype_miss(combined: str, outcome: str) -> bool:
    social_hit = ("twitter" in combined or "x.com" in combined or "telegram" in combined or "social" in combined)
    return outcome == "loser" and social_hit


def _volume_exhaustion(trade: dict) -> bool:
    txs = trade.get("tx_count_m5") or trade.get("m5_tx")
    try:
        t = float(txs) if txs is not None else None
    except (TypeError, ValueError):
        t = None
    return bool(t is not None and t < 10)


def _fake_breakout(trade: dict) -> bool:
    hi = safe_float(trade.get("highest_price_seen"))
    cp = safe_float(trade.get("close_price"))
    ep = safe_float(trade.get("entry_price"))
    er = _norm_txt(trade.get("close_reason"))
    if hi and ep and cp and hi > ep * 1.4 and cp < hi * 0.75 and ("stop" in er or "loss" in er):
        return True
    return False


def _momentum_fade(trade: dict) -> bool:
    hi = safe_float(trade.get("highest_price_seen"))
    cp = safe_float(trade.get("close_price"))
    ep = safe_float(trade.get("entry_price"))
    if not hi or not cp or not ep:
        return False
    if hi <= ep:
        return False
    if (hi / ep) >= 1.35 and (cp / ep) <= 1.03:
        return True
    return False


def dedupe_preserve(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


ALLOWED_TAGS = frozenset(POSTMORTEM_CLASSIFICATION_TAGS)


def sanitize_tags(tags: Sequence[str]) -> List[str]:
    return [t for t in dedupe_preserve(tags) if t in ALLOWED_TAGS]
