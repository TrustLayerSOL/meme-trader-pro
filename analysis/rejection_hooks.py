"""Runtime hooks: persist no-trade rows for Phase A analysis (fail-open)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.settings_manager import parse_bool


def _settings_get(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return settings if isinstance(settings, dict) else {}


def rejection_log_enabled(settings: Optional[Dict[str, Any]] = None) -> bool:
    s = _settings_get(settings)
    return parse_bool(s.get("analysis_rejection_log_enabled"), True)


def _compact_market_radar_context(payload: Dict[str, Any], decision_summary: Dict[str, Any]) -> Dict[str, Any]:
    mi = payload.get("market_info") if isinstance(payload.get("market_info"), dict) else {}
    return {
        "mint": payload.get("mint"),
        "signal_type": payload.get("type") or "market_radar_hot",
        "total_score": payload.get("total_score"),
        "score_threshold": payload.get("score_threshold"),
        "hard_block": payload.get("hard_block"),
        "holder_concentration_risk": payload.get("holder_concentration_risk"),
        "skip_bucket": decision_summary.get("skip_bucket"),
        "market_info": {
            "liquidity": mi.get("liquidity"),
            "market_cap": mi.get("market_cap"),
            "price": mi.get("price"),
        },
        "score_reasons_tail": (payload.get("score_reasons") or [])[-6:]
        if isinstance(payload.get("score_reasons"), list)
        else [],
    }


def _pick_scanner_rejection_reason(decision: Dict[str, Any], payload: Dict[str, Any]) -> str:
    from analysis.rejection_reason_pick import pick_ranked_rejection_reason

    reasons = decision.get("reasons") if isinstance(decision.get("reasons"), list) else []
    return pick_ranked_rejection_reason(
        action_reason=None,
        scoring_reasons=reasons,
        hard_block=bool(payload.get("hard_block")),
        hard_block_reason=payload.get("hard_block_reason"),
        default="unknown_skip",
    )


def _compact_scanner_context(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    mi = payload.get("market_info") if isinstance(payload.get("market_info"), dict) else {}
    return {
        "mint": payload.get("mint"),
        "signal_type": payload.get("type"),
        "should_trade": decision.get("should_trade"),
        "score": decision.get("score"),
        "threshold": decision.get("threshold"),
        "mode": decision.get("mode"),
        "paper_lane": decision.get("paper_lane"),
        "hard_block": payload.get("hard_block"),
        "holder_concentration_risk": payload.get("holder_concentration_risk"),
        "risk_label": payload.get("risk_label"),
        "liquidity": mi.get("liquidity"),
        "market_cap": mi.get("market_cap"),
        "reasons_tail": (decision.get("reasons") or [])[-8:],
    }


def maybe_log_market_radar_skip(
    payload: Dict[str, Any],
    decision_summary: Dict[str, Any],
    decision_id: Optional[str],
    settings: Optional[Dict[str, Any]],
) -> None:
    if not rejection_log_enabled(settings):
        return
    try:
        from analysis.rejection_logger import record_rejection
    except Exception:
        return

    reason = decision_summary.get("skip_reason") or "market_radar_skip"
    ctx = _compact_market_radar_context(payload, decision_summary)
    try:
        record_rejection(
            str(reason)[:500],
            ctx,
            mint=payload.get("mint"),
            decision_id=decision_id,
            lane=payload.get("paper_lane") or "market_radar",
            source="market_radar",
        )
    except Exception:
        return


def maybe_log_scanner_strategy_skip(
    payload: Dict[str, Any],
    decision: Dict[str, Any],
    decision_id: Optional[str],
    settings: Optional[Dict[str, Any]],
) -> None:
    if not rejection_log_enabled(settings):
        return
    if decision.get("should_trade", False):
        return
    try:
        from analysis.rejection_logger import record_rejection
    except Exception:
        return

    reason = _pick_scanner_rejection_reason(decision, payload)
    ctx = _compact_scanner_context(payload, decision)
    try:
        record_rejection(
            reason,
            ctx,
            mint=payload.get("mint"),
            decision_id=decision_id,
            lane=decision.get("paper_lane") or "main",
            source="scanner",
        )
    except Exception:
        return


def maybe_log_scanner_runtime_skip(
    *,
    mint: str,
    decision_id: Optional[str],
    reason: str,
    decision: Dict[str, Any],
    settings: Optional[Dict[str, Any]],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not rejection_log_enabled(settings):
        return
    try:
        from analysis.rejection_logger import record_rejection
    except Exception:
        return
    ctx = {
        "mint": mint,
        "runtime_skip": True,
        "score": decision.get("score"),
        "threshold": decision.get("threshold"),
        "edge_score": extra.get("edge_score") if isinstance(extra, dict) else None,
    }
    if isinstance(extra, dict):
        ctx.update({k: v for k, v in extra.items() if k not in ctx})
    try:
        record_rejection(
            reason,
            ctx,
            mint=mint,
            decision_id=decision_id,
            lane=decision.get("paper_lane") or "main",
            source="scanner_runtime",
        )
    except Exception:
        return


def maybe_log_market_radar_runtime_skip(
    payload: Dict[str, Any],
    decision_id: Optional[str],
    reason: str,
    settings: Optional[Dict[str, Any]],
) -> None:
    if not rejection_log_enabled(settings):
        return
    try:
        from analysis.rejection_logger import record_rejection
    except Exception:
        return
    ctx = _compact_market_radar_context(
        payload,
        {"skip_reason": reason, "skip_bucket": "runtime_precheck"},
    )
    try:
        record_rejection(
            str(reason)[:500],
            ctx,
            mint=payload.get("mint"),
            decision_id=decision_id,
            lane="market_radar",
            source="market_radar_runtime",
        )
    except Exception:
        return
