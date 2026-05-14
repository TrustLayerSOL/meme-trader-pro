"""Stable decision_id derivation and synthetic ledger rows for paper trades."""

import hashlib

from core.decision_ledger import build_decision_record


def trade_decision_id(trade):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    return trade.get("decision_id") or metadata.get("decision_id")


def trade_paper_lane(trade):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    if trade.get("exploration") is True:
        return "exploration"
    return trade.get("paper_lane") or metadata.get("paper_lane") or "main"


def synthetic_trade_decision_id(trade, bucket):
    trade = trade if isinstance(trade, dict) else {}
    parts = [
        bucket,
        str(trade.get("mint") or trade.get("token_mint") or ""),
        str(trade.get("entry_time") or trade.get("time") or ""),
        str(trade.get("close_time") or trade.get("exit_time") or ""),
        str(trade.get("entry_reason") or trade.get("reason") or ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"dec_legacy_paper_{digest}"


def synthetic_decision_payload_from_trade(trade, bucket, decision_id):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    timestamp = trade.get("entry_time") or trade.get("time") or trade.get("close_time")
    should_trade = bucket in {"open_trades", "closed_trades"}
    reason = (
        trade.get("entry_reason")
        or trade.get("reason")
        or trade.get("failure_reason")
        or trade.get("close_reason")
        or "legacy paper trade"
    )
    buy_quote_pass = "quote_ok" in str(reason)
    return build_decision_record({
        "decision_id": decision_id,
        "timestamp": timestamp,
        "mint": trade.get("mint") or trade.get("token_mint"),
        "type": metadata.get("signal_type") or "legacy_paper_trade",
        "paper_lane": trade_paper_lane(trade),
        "should_trade": should_trade,
        "wallets": trade.get("wallets") or [],
        "wallet_count": len(trade.get("wallets") or []),
        "position_size_usd": trade.get("position_size_usd") or trade.get("size_usd"),
        "buy_quote_pass": buy_quote_pass,
        "sell_quote_pass": buy_quote_pass,
        "risk_label": metadata.get("risk_label"),
        "risk_score": metadata.get("risk_score"),
        "total_score": metadata.get("score") or metadata.get("total_score"),
        "threshold": metadata.get("threshold"),
        "edge_score": (
            (metadata.get("edge_result") or {}).get("edge_score")
            if isinstance(metadata.get("edge_result"), dict)
            else metadata.get("edge_score")
        ),
        "edge_verdict": (
            (metadata.get("edge_result") or {}).get("edge_verdict")
            if isinstance(metadata.get("edge_result"), dict)
            else metadata.get("edge_verdict")
        ),
        "score_reasons": [reason, "synthetic legacy paper decision backfill"],
    })
