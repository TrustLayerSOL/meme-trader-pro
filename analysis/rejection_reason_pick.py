"""Ranked selection of a human-useful rejection reason from ledger / decision text."""

from __future__ import annotations

from typing import Optional, Sequence

_GENERIC_ACTION_REASONS = frozenset(
    {
        "",
        "skip",
        "unknown_skip",
        "scanner_should_trade_false",
        "sqlite_should_trade_false",
    },
)

# Priority substrings (ties per line: first needle in this list that appears in the line wins).
# Across lines: document order — first scoring line that matches any needle wins.
_PRIORITY_SUBSTRINGS = (
    "hard block:",
    "hard block",
    "holder block:",
    "holder warn:",
    "block:",
    "market sanity",
    "buy quote",
    "exit liquidity",
    "swap quote",
    "sell_quote_not_checked",
    "strategy guard",
    "wallet main quality",
    "pre-score",
    "confirmation block",
    "market_radar_skip:",
    "rug",
)


def _action_reason_is_informative(action_reason: Optional[str]) -> bool:
    if action_reason is None:
        return False
    s = str(action_reason).strip()
    if len(s) < 2:
        return False
    low = s.lower()
    if low in _GENERIC_ACTION_REASONS:
        return False
    if low == "skip":
        return False
    return True


def pick_ranked_rejection_reason(
    *,
    action_reason: Optional[str],
    scoring_reasons: Optional[Sequence[str]],
    hard_block: bool = False,
    hard_block_reason: Optional[str] = None,
    default: str = "unknown_skip",
    max_len: int = 500,
) -> str:
    """
    Prefer causal / block wording over trailing narrative lines.

    Order: hard_block_reason → informative action_reason → first scoring line (document order)
    that contains any priority substring → last scoring line → default.
    """
    if hard_block and hard_block_reason:
        return str(hard_block_reason).strip()[:max_len]

    if _action_reason_is_informative(action_reason):
        return str(action_reason).strip()[:max_len]

    reasons = [str(r) for r in (scoring_reasons or []) if r is not None and str(r).strip()]
    if not reasons:
        return default[:max_len]

    # Document order: first line that matches any priority substring.
    for line in reasons:
        low = line.lower()
        for needle in _PRIORITY_SUBSTRINGS:
            if needle.lower() in low:
                return line[:max_len]

    return reasons[-1][:max_len]
