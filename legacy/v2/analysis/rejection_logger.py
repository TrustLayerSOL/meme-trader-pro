"""Append structured no-trade / rejection observations (Phase A).

Counterfactual fields are placeholders until replay prices are modeled.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_REJECT_PATH = Path("data/rejected_signals/rejections.jsonl")


def record_rejection(
    rejection_reason: str,
    signal_context: Dict[str, Any],
    hypothetical_outcome_if_traded: Optional[Dict[str, Any]] = None,
    *,
    mint: Optional[str] = None,
    decision_id: Optional[str] = None,
    lane: Optional[str] = None,
    path: Optional[Path] = None,
    source: Optional[str] = None,
) -> Path:
    """
    Persist one rejection row aligned with BUILD_PLAN storage contract:

        - rejection reason
        - signal context
        - what would have happened afterward if traded (explicitly speculative / TODO by default)

    hypothetical_outcome_if_traded defaults to placeholder ``status:unknown`` when omitted.
    """
    path = Path(path or DEFAULT_REJECT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    counterfactual = hypothetical_outcome_if_traded
    if counterfactual is None:
        counterfactual = {
            "note": "not yet computed — requires causal replay slice / price tape",
            "status": "unknown",
        }

    row = {
        "schema_version": 1,
        "recorded_at": time.time(),
        "rejection reason": rejection_reason,
        "signal context": dict(signal_context) if isinstance(signal_context, dict) else {"raw": signal_context},
        "what would have happened afterward if traded": counterfactual,
        "mint": mint or (signal_context or {}).get("mint"),
        "decision_id": decision_id or (signal_context or {}).get("decision_id"),
        "lane": lane or (signal_context or {}).get("paper_lane"),
        "source": source,
    }

    line = json.dumps(row, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path
