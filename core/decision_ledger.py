import time
import uuid


def new_decision_id():
    return f"dec_{uuid.uuid4().hex}"


def first_reason(value):
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return ""


def build_decision_record(payload):
    payload = payload if isinstance(payload, dict) else {}
    now = payload.get("timestamp") or payload.get("time") or time.time()
    decision_id = payload.get("decision_id") or new_decision_id()
    should_trade = bool(payload.get("should_trade"))
    paper_lane = payload.get("paper_lane") or "main"
    action = "paper_open_attempt" if should_trade else "skip"
    reasons = payload.get("score_reasons") or payload.get("reasons") or []

    return {
        "decision_id": decision_id,
        "created_at": now,
        "updated_at": now,
        "mint": payload.get("mint") or payload.get("token_mint"),
        "signal_type": payload.get("type") or payload.get("signal_type"),
        "scanner_stage": "signal_evaluation",
        "final_action": action,
        "action_reason": first_reason(reasons),
        "paper_lane": paper_lane,
        "should_trade": should_trade,
        "total_score": payload.get("total_score"),
        "threshold": payload.get("score_threshold") or payload.get("threshold"),
        "edge_score": payload.get("edge_score"),
        "edge_verdict": payload.get("edge_verdict"),
        "risk_label": payload.get("risk_label"),
        "risk_score": payload.get("risk_score"),
        "buy_quote_pass": payload.get("buy_quote_pass"),
        "sell_quote_pass": payload.get("sell_quote_pass"),
        "position_size_usd": payload.get("position_size_usd"),
        "payload": {
            "decision_id": decision_id,
            "candidate": {
                "mint": payload.get("mint") or payload.get("token_mint"),
                "signal_type": payload.get("type") or payload.get("signal_type"),
                "timestamp": now,
            },
            "inputs": {
                "wallets": payload.get("wallets") or [],
                "wallet_count": payload.get("wallet_count"),
                "weighted_wallet_score": payload.get("weighted_wallet_score"),
                "wallet_quality": payload.get("wallet_quality"),
                "wallet_performance": payload.get("wallet_performance"),
                "social_match": payload.get("social_match"),
                "dev_wallet": payload.get("dev_wallet"),
                "dev_score": payload.get("dev_score"),
                "market_info": payload.get("market_info"),
                "launch_info": payload.get("launch_info"),
                "token_inspection": payload.get("token_inspection"),
            },
            "rule_outcomes": {
                "scoring": {
                    "score": payload.get("total_score"),
                    "threshold": payload.get("score_threshold"),
                    "mode": payload.get("mode"),
                    "reasons": reasons,
                },
                "risk": {
                    "risk_label": payload.get("risk_label"),
                    "risk_score": payload.get("risk_score"),
                    "warnings": payload.get("risk_warnings") or [],
                    "hard_block": payload.get("hard_block"),
                    "hard_block_reason": payload.get("hard_block_reason"),
                },
                "edge": {
                    "edge_score": payload.get("edge_score"),
                    "edge_verdict": payload.get("edge_verdict"),
                    "quote_worthy": payload.get("edge_quote_worthy"),
                    "paper_trade_worthy": payload.get("edge_paper_trade_worthy"),
                    "positives": payload.get("edge_positives") or [],
                    "risks": payload.get("edge_risks") or [],
                },
                "confirmation": {
                    "allow": payload.get("confirmation_allow"),
                    "reasons": payload.get("confirmation_reasons") or [],
                    "warnings": payload.get("confirmation_warnings") or [],
                },
                "strategy_guard": {
                    "action": payload.get("strategy_guard_action"),
                    "reason": payload.get("strategy_guard_reason"),
                    "stats": payload.get("strategy_guard_stats"),
                },
                "exploration": payload.get("exploration_result"),
            },
            "quotes": {
                "buy": {
                    "pass": payload.get("buy_quote_pass"),
                    "reason": payload.get("buy_quote_reason"),
                    "price_impact_pct": payload.get("buy_quote_price_impact_pct"),
                },
                "sell": {
                    "pass": payload.get("sell_quote_pass"),
                    "reason": payload.get("sell_quote_reason"),
                    "price_impact_pct": payload.get("sell_quote_price_impact_pct"),
                },
            },
            "action": {
                "should_trade": should_trade,
                "final_action": action,
                "position_size_usd": payload.get("position_size_usd"),
                "paper_lane": paper_lane,
                "reasons": reasons,
            },
            "result": None,
        },
    }


def build_trade_result(trade, context, extra=None):
    trade = trade if isinstance(trade, dict) else {}
    signal_metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    result = {
        "context": context,
        "mint": trade.get("mint") or trade.get("token_mint"),
        "trade_status": trade.get("status"),
        "trade_id": trade.get("trade_id") or signal_metadata.get("trade_id"),
        "entry_time": trade.get("entry_time"),
        "close_time": trade.get("close_time"),
        "pnl": trade.get("total_pnl", trade.get("pnl")),
        "pnl_pct": trade.get("total_pnl_pct", trade.get("pnl_pct")),
        "failure_reason": trade.get("failure_reason"),
        "exit_reason": trade.get("exit_reason") or trade.get("close_reason"),
        "updated_at": time.time(),
    }
    if isinstance(extra, dict):
        result.update(extra)
    return result
