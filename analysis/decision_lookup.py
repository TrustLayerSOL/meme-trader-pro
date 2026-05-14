"""Load canonical decision payload fragments from SQLite for post-mortems / analysis."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.storage import EventStore


def fetch_stored_decision_payload(decision_id: str, store: Optional[EventStore] = None) -> Optional[Dict[str, Any]]:
    """Return the JSON object stored in `decision_records.payload_json` (rule_outcomes, inputs, etc.)."""
    if not decision_id:
        return None
    store = store or EventStore()
    try:
        with store.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM decision_records WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    raw = row[0]
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def hints_from_stored_payload(inner: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map stored ledger payloadJson into classifier/post-mortem hint keys."""
    inner = inner if isinstance(inner, dict) else {}
    hints: Dict[str, Any] = {}
    ro = inner.get("rule_outcomes") if isinstance(inner.get("rule_outcomes"), dict) else {}
    hc = ro.get("holder_cluster") if isinstance(ro.get("holder_cluster"), dict) else {}
    hr = hc.get("holder_risk_label")
    if hr:
        hints["holder_risk_label"] = hr
    reasons = hc.get("holder_reasons")
    if isinstance(reasons, list) and reasons:
        hints["holder_concentration_reasons"] = reasons

    ins = inner.get("inputs") if isinstance(inner.get("inputs"), dict) else {}
    mc = ins.get("market_context") if isinstance(ins.get("market_context"), dict) else {}
    if mc.get("risk_regime") is not None:
        hints["market_risk_regime"] = mc.get("risk_regime")
    if mc.get("broader_crypto"):
        hints["broader_crypto_context"] = mc.get("broader_crypto")

    return hints
