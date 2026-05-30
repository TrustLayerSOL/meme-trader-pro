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


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def route_plan_summary(route_plan):
    rows = []
    for item in as_list(route_plan)[:4]:
        item = as_dict(item)
        swap_info = as_dict(item.get("swapInfo") or item.get("swap_info"))
        rows.append({
            "label": first_present(
                swap_info.get("label"),
                item.get("label"),
                item.get("marketLabel"),
            ),
            "amm_key": first_present(swap_info.get("ammKey"), swap_info.get("amm_key")),
            "input_mint": first_present(swap_info.get("inputMint"), swap_info.get("input_mint")),
            "output_mint": first_present(swap_info.get("outputMint"), swap_info.get("output_mint")),
            "in_amount": first_present(swap_info.get("inAmount"), swap_info.get("in_amount")),
            "out_amount": first_present(swap_info.get("outAmount"), swap_info.get("out_amount")),
            "percent": item.get("percent"),
        })
    return rows


def quote_details(payload, side):
    quote = as_dict(payload.get(f"{side}_quote"))
    analysis = as_dict(payload.get(f"{side}_quote_analysis"))
    route_plan = first_present(
        payload.get(f"{side}_quote_route_plan"),
        quote.get("route_plan"),
        quote.get("routePlan"),
    )
    route_plan_rows = route_plan_summary(route_plan)
    return {
        "pass": first_present(payload.get(f"{side}_quote_pass"), analysis.get("pass")),
        "reason": first_present(payload.get(f"{side}_quote_reason"), analysis.get("reason"), quote.get("reason")),
        "price_impact_pct": first_present(
            payload.get(f"{side}_quote_price_impact_pct"),
            analysis.get("price_impact_pct"),
            quote.get("price_impact_pct"),
            quote.get("priceImpactPct"),
        ),
        "route_count": first_present(payload.get(f"{side}_quote_route_count"), quote.get("route_count"), len(route_plan_rows) if route_plan_rows else None),
        "input_mint": first_present(payload.get(f"{side}_quote_input_mint"), quote.get("input_mint")),
        "output_mint": first_present(payload.get(f"{side}_quote_output_mint"), quote.get("output_mint")),
        "in_amount_raw": first_present(payload.get(f"{side}_quote_in_amount_raw"), quote.get("in_amount_raw")),
        "out_amount": first_present(payload.get(f"{side}_quote_out_amount"), quote.get("out_amount")),
        "slippage_bps": payload.get(f"{side}_quote_slippage_bps"),
        "max_price_impact_pct": payload.get(f"{side}_quote_max_price_impact_pct"),
        "route_plan": route_plan_rows,
    }


def social_catalyst_evidence(payload):
    social_match = as_dict(payload.get("social_match"))
    event_ids = as_list(first_present(
        payload.get("social_event_ids"),
        social_match.get("event_ids"),
        social_match.get("signal_ids"),
        social_match.get("event_id"),
    ))
    evidence_urls = as_list(first_present(
        payload.get("social_evidence_urls"),
        social_match.get("evidence_urls"),
        social_match.get("url"),
        social_match.get("link"),
    ))
    return {
        "matched": first_present(payload.get("social_matched"), social_match.get("matched")),
        "reason": first_present(payload.get("social_reason"), social_match.get("reason")),
        "score_bonus": first_present(payload.get("social_bonus"), social_match.get("score_bonus")),
        "score": first_present(payload.get("catalyst_score"), social_match.get("catalyst_score")),
        "match_confidence": first_present(
            payload.get("social_match_confidence"),
            payload.get("catalyst_match_confidence"),
            social_match.get("match_confidence"),
        ),
        "event_ids": event_ids,
        "catalyst_card_ids": as_list(payload.get("catalyst_card_ids")),
        "account": first_present(
            payload.get("social_account"),
            social_match.get("matched_account"),
            social_match.get("account"),
        ),
        "keywords": as_list(first_present(
            payload.get("social_keywords"),
            social_match.get("matched_keywords"),
            social_match.get("keywords"),
        )),
        "source_platform": first_present(payload.get("social_platform"), social_match.get("platform")),
        "collector": payload.get("social_collector"),
        "evidence_urls": evidence_urls,
    }


def holder_cluster_outcome(payload):
    metrics = as_dict(first_present(
        payload.get("holder_concentration_metrics"),
        as_dict(payload.get("holder_concentration")).get("metrics"),
    ))
    return {
        "holder_risk_label": first_present(
            payload.get("holder_concentration_risk"),
            as_dict(payload.get("holder_concentration")).get("risk_label"),
        ),
        "holder_reasons": as_list(first_present(
            payload.get("holder_concentration_reasons"),
            as_dict(payload.get("holder_concentration")).get("warnings"),
        )),
        "holder_count": first_present(payload.get("holder_count"), metrics.get("holder_count")),
        "top_1_pct": metrics.get("top_1_pct"),
        "top_5_pct": metrics.get("top_5_pct"),
        "top_10_pct": metrics.get("top_10_pct"),
        "top_20_pct": metrics.get("top_20_pct"),
        "top_holder_address": metrics.get("top_holder_address"),
        "linked_wallet_risk": first_present(
            payload.get("linked_wallet_risk"),
            payload.get("cluster_risk"),
            payload.get("linked_cluster_risk"),
        ),
    }


def market_context(payload):
    return {
        "broader_crypto": payload.get("broader_crypto_context"),
        "stablecoin": payload.get("stablecoin_context"),
        "risk_regime": payload.get("market_risk_regime"),
        "sol_price_change_pct": payload.get("sol_price_change_pct"),
        "stablecoin_depeg_warning": payload.get("stablecoin_depeg_warning"),
    }


def paper_outcome_details(trade, signal_metadata, context):
    return {
        "context": context,
        "paper_lane": first_present(trade.get("paper_lane"), signal_metadata.get("paper_lane")),
        "exploration": first_present(trade.get("exploration"), signal_metadata.get("exploration")),
        "exploration_result": first_present(
            trade.get("exploration_result"),
            signal_metadata.get("exploration_result"),
        ),
        "entry_price": trade.get("entry_price"),
        "exit_price": first_present(trade.get("exit_price"), trade.get("close_price"), trade.get("current_price")),
        "entry_liquidity_usd": trade.get("entry_liquidity_usd"),
        "exit_liquidity_usd": first_present(trade.get("exit_liquidity_usd"), trade.get("current_liquidity_usd")),
        "entry_market_cap": trade.get("entry_market_cap"),
        "exit_market_cap": first_present(trade.get("exit_market_cap"), trade.get("current_market_cap")),
        "position_size_usd": first_present(trade.get("position_size_usd"), trade.get("size_usd")),
        "remaining_pct": trade.get("remaining_pct"),
        "fees_usd": first_present(trade.get("fees_usd"), trade.get("total_fees_usd")),
        "entry_reason": trade.get("entry_reason") or trade.get("reason"),
        "exit_reason": trade.get("exit_reason") or trade.get("close_reason"),
    }


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
                "social_catalyst": social_catalyst_evidence(payload),
                "dev_wallet": payload.get("dev_wallet"),
                "dev_score": payload.get("dev_score"),
                "market_info": payload.get("market_info"),
                "market_context": market_context(payload),
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
                "wallet_main_quality": payload.get("wallet_main_quality_gate"),
                "holder_cluster": holder_cluster_outcome(payload),
                "exploration": payload.get("exploration_result"),
            },
            "quotes": {
                "buy": quote_details(payload, "buy"),
                "sell": quote_details(payload, "sell"),
            },
            "route_feasibility": {
                "buy": quote_details(payload, "buy"),
                "sell": quote_details(payload, "sell"),
            },
            "market_radar": payload.get("market_radar"),
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
    decision_id = trade.get("decision_id") or signal_metadata.get("decision_id")
    result = {
        "decision_id": decision_id,
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
        "paper_outcome": paper_outcome_details(trade, signal_metadata, context),
        "updated_at": time.time(),
    }
    if isinstance(extra, dict):
        result.update(extra)
    return result
