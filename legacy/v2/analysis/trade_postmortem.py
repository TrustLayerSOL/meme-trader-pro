"""Structured trade post-mortem records (Phase A): JSON payloads + JSONL append."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Set

from analysis.trade_classifier import classify_closed_trade, safe_float
from core.paper_trade_decision_ids import trade_decision_id


DEFAULT_POSTMORTEM_PATH = Path("data/postmortems/paper_closed.jsonl")


def trade_fingerprint(trade: Dict[str, Any]) -> str:
    mint = trade.get("token_mint") or trade.get("mint") or ""
    ct = trade.get("close_time") or trade.get("exit_time") or ""
    et = trade.get("entry_time") or trade.get("time") or ""
    pnl = trade.get("total_pnl") or trade.get("pnl") or ""
    blob = "{}|{}|{}|{}".format(mint, ct, et, pnl)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
    return digest


def build_postmortem_record(
    trade: Dict[str, Any],
    decision_hints: Optional[Dict[str, Any]] = None,
    *,
    enrich_from_sqlite: bool = True,
    store: Any = None,
) -> Dict[str, Any]:
    """
    Compose one JSON-serializable post-mortem for a terminal trade dict (normally closed).

    decision_hints optional: merged metadata from SQLite decision_row or ledger payload shards.
    When enrich_from_sqlite is True and `decision_id` is present, holder/regime hints are merged
    from `decision_records.payload_json` (fail-open if DB missing).
    """
    decision_hints = dict(decision_hints) if isinstance(decision_hints, dict) else {}
    merged_hints = dict(decision_hints)

    did_early = trade_decision_id(trade)
    metadata_pre = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    if not did_early:
        did_early = metadata_pre.get("decision_id")

    if enrich_from_sqlite and did_early:
        try:
            from analysis.decision_lookup import fetch_stored_decision_payload, hints_from_stored_payload
        except Exception:
            pass
        else:
            inner = fetch_stored_decision_payload(did_early, store)
            if inner:
                for k, v in hints_from_stored_payload(inner).items():
                    if v in (None, "", [], {}):
                        continue
                    if k not in merged_hints or merged_hints.get(k) in (None, "", [], {}):
                        merged_hints[k] = v

    classifications, aux = classify_closed_trade(trade, merged_hints)

    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    wallets = trade.get("wallets") if isinstance(trade.get("wallets"), list) else []

    quoted = safe_float(trade.get("quoted_entry_price"))
    entry_px = safe_float(trade.get("entry_price"))
    slip_pct = None
    if quoted and entry_px and quoted > 0:
        slip_pct = round(abs((entry_px - quoted) / quoted) * 100, 4)

    liquidity_entry = safe_float(trade.get("entry_liquidity_usd"))
    if liquidity_entry is None:
        liquidity_entry = safe_float(trade.get("liquidity_usd"))

    token_age_seconds = metadata.get("token_age_seconds")
    if token_age_seconds is None:
        mi = metadata.get("market_info") if isinstance(metadata.get("market_info"), dict) else {}
        token_age_seconds = mi.get("pair_age_seconds") or mi.get("launch_age_seconds")

    if isinstance(metadata.get("holder_cluster"), dict):
        hc = dict(metadata["holder_cluster"])
    else:
        hc = {}
    for k in ("holder_risk_label", "holder_concentration_reasons"):
        if k in merged_hints and merged_hints[k] not in (None, "", [], {}):
            hc[k] = merged_hints[k]

    social_tags = []
    cid = metadata.get("catalyst_card_ids") or metadata.get("social_event_ids")
    if isinstance(cid, list):
        social_tags.extend([str(x) for x in cid[:20]])

    fp = trade_fingerprint(trade)
    did = trade_decision_id(trade) or metadata.get("decision_id")

    record = {
        "schema_version": 1,
        "postmortem_id": "pm_" + fp,
        "trade_fingerprint": fp,
        "generated_at": time.time(),
        "mint": trade.get("token_mint") or trade.get("mint"),
        "decision_id": did,
        "paper_lane": trade.get("paper_lane") or metadata.get("paper_lane"),
        "status": trade.get("status"),
        "ledger_enriched": bool(enrich_from_sqlite and did_early),
        "tracked": {
            "entry reason": trade.get("entry_reason") or trade.get("reason"),
            "exit reason": trade.get("exit_reason") or trade.get("close_reason"),
            "wallet cluster composition": list(wallets),
            "wallet quality score": _avg_wallet_quality(wallets),
            "token age": token_age_seconds,
            "liquidity at entry": liquidity_entry,
            "holder concentration": hc or None,
            "social signal tags if available": social_tags,
            "market regime": _market_regime_from_hints(merged_hints, metadata),
            "entry delay estimate": None,
            "slippage estimate": slip_pct,
        },
        "classifications": classifications,
        "exit_analysis": aux.get("exit_detail"),
        "primary_exit_attribution": (aux.get("exit_detail") or {}).get("primary_exit_attribution"),
        "classification_notes": aux.get("classification_notes", []),
    }
    return record


def _avg_wallet_quality(wallets: list) -> Optional[float]:
    if not wallets:
        return None
    path = Path("data/wallet_performance.json")
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    wm = blob.get("wallets") if isinstance(blob.get("wallets"), dict) else {}
    scores = []
    for w in wallets:
        row = wm.get(w) if isinstance(wm.get(w), dict) else {}
        s = safe_float(row.get("score"))
        if s is not None:
            scores.append(s)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _market_regime_from_hints(decision_hints: dict, metadata: dict) -> Optional[str]:
    if decision_hints.get("market_risk_regime") is not None:
        return str(decision_hints["market_risk_regime"])
    ctx = metadata.get("broader_crypto_context") or decision_hints.get("broader_crypto_context")
    if isinstance(ctx, dict):
        reg = ctx.get("market_risk_regime") or ctx.get("regime")
        if reg:
            return str(reg)
    return None


def append_postmortem_jsonl(record: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = Path(path or DEFAULT_POSTMORTEM_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


def load_postmortem_ids(path: Optional[Path] = None) -> Set[str]:
    path = Path(path or DEFAULT_POSTMORTEM_PATH)
    if not path.exists():
        return set()
    ids: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            pid = payload.get("postmortem_id") or payload.get("trade_fingerprint")
            if pid:
                ids.add(str(pid))
        except json.JSONDecodeError:
            continue
    return ids


def iter_closed_trades(paper_blob: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    for row in paper_blob.get("closed_trades") or []:
        if isinstance(row, dict):
            yield row


def snapshot_from_paper_file(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}
