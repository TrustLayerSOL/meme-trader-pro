from __future__ import annotations

import time
from typing import Any


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def summarize_triggering_wallets(
    wallets: Any,
    wallet_performance: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    perf = as_dict(wallet_performance)
    scores = perf.get("wallet_scores") if isinstance(perf.get("wallet_scores"), list) else []
    by_wallet = {}
    for row in scores:
        row = as_dict(row)
        wallet = row.get("wallet")
        if wallet:
            by_wallet[str(wallet)] = row

    output = []
    for wallet in safe_list(wallets):
        if isinstance(wallet, dict):
            wallet_id = first_present(wallet.get("wallet"), wallet.get("address"), wallet.get("trackedWalletAddress"))
            source_row = wallet
        else:
            wallet_id = wallet
            source_row = {}
        wallet_id = str(wallet_id or "").strip()
        if not wallet_id:
            continue
        score_row = by_wallet.get(wallet_id, {})
        output.append(
            {
                "wallet": wallet_id,
                "score": first_present(source_row.get("score"), score_row.get("score")),
                "label": first_present(source_row.get("label"), score_row.get("label")),
                "tier": first_present(source_row.get("tier"), score_row.get("tier")),
            }
        )
    return output


def extract_market(payload: dict[str, Any]) -> dict[str, Any]:
    mi = as_dict(payload.get("market_info"))
    launch = as_dict(payload.get("launch_info"))
    return {
        "liquidity": first_present(mi.get("liquidity"), payload.get("liquidity"), payload.get("liquidity_usd")),
        "market_cap": first_present(mi.get("market_cap"), payload.get("market_cap")),
        "price": first_present(mi.get("price"), payload.get("price")),
        "volume": first_present(mi.get("volume"), mi.get("volume_usd"), payload.get("volume_usd")),
        "buy_velocity": first_present(mi.get("buy_velocity"), payload.get("buy_velocity")),
        "sell_velocity": first_present(mi.get("sell_velocity"), payload.get("sell_velocity")),
        "token_age_seconds": first_present(
            payload.get("token_age_seconds"),
            payload.get("true_launch_age_seconds"),
            mi.get("pair_age_seconds"),
            mi.get("launch_age_seconds"),
            launch.get("age_seconds"),
        ),
        "holder_count": first_present(payload.get("holder_count"), mi.get("holder_count")),
        "holder_concentration_risk": first_present(
            payload.get("holder_concentration_risk"),
            as_dict(payload.get("holder_concentration")).get("risk_label"),
        ),
        "price_change_pct": first_present(
            payload.get("price_change_pct"),
            mi.get("price_change_pct"),
            mi.get("price_change_5m_pct"),
        ),
    }


def build_cluster(payload: dict[str, Any], wallet_count: int) -> dict[str, Any]:
    start = safe_float(first_present(payload.get("cluster_start_time"), payload.get("first_wallet_time")), None)
    end = safe_float(first_present(payload.get("cluster_end_time"), payload.get("last_wallet_time")), None)
    duration = None
    if start is not None and end is not None and end >= start:
        duration = round(end - start, 4)
    return {
        "wallet_count": first_present(payload.get("wallet_count"), wallet_count),
        "start_time": start,
        "end_time": end,
        "duration_seconds": duration,
        "repeated_coordinated_entries": safe_list(payload.get("coordinated_entries"))[:25],
    }


def classify_market_regime(context: dict[str, Any]) -> dict[str, Any]:
    market = as_dict(context.get("market"))
    risk = as_dict(context.get("risk"))
    tags: list[str] = []
    reasons: list[str] = []

    liquidity = safe_float(market.get("liquidity"), 0.0) or 0.0
    volume = safe_float(market.get("volume"), 0.0) or 0.0
    buy_velocity = safe_float(market.get("buy_velocity"), 0.0) or 0.0
    price_change = abs(safe_float(market.get("price_change_pct"), 0.0) or 0.0)

    if liquidity and liquidity < 2_500:
        tags.append("low_liquidity_market")
        reasons.append("liquidity below 2500")
    if bool(risk.get("hard_block")) or str(risk.get("holder_concentration_risk") or "").upper() in {"DANGER", "HIGH_RISK"}:
        tags.append("rug_heavy_environment")
        reasons.append("hard risk or holder concentration warning")
    if volume >= 25_000 or buy_velocity >= 6:
        tags.append("strong_runner_environment")
        reasons.append("high volume or buy velocity")
    if volume and volume < 1_000 and buy_velocity <= 1:
        tags.append("dead_market")
        reasons.append("low volume and low buy velocity")
    if price_change >= 25:
        tags.append("high_volatility")
        reasons.append("large recent price change")
    if not tags:
        tags.append("unknown")
        reasons.append("not enough market data")
    return {"tags": tags, "reasons": reasons}


def build_signal_context(
    payload: dict[str, Any] | None,
    decision: dict[str, Any] | None = None,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    wallets = safe_list(first_present(payload.get("wallets"), decision.get("wallets")))
    wallet_performance = first_present(payload.get("wallet_performance"), decision.get("wallet_performance"))
    triggering_wallets = summarize_triggering_wallets(wallets, as_dict(wallet_performance))
    market = extract_market(payload)
    risk = {
        "risk_label": first_present(payload.get("risk_label"), decision.get("risk_label")),
        "risk_score": first_present(payload.get("risk_score"), decision.get("risk_score")),
        "hard_block": first_present(payload.get("hard_block"), decision.get("hard_block")),
        "hard_block_reason": first_present(payload.get("hard_block_reason"), decision.get("hard_block_reason")),
        "holder_concentration_risk": market.get("holder_concentration_risk"),
    }
    context = {
        "schema_version": 2,
        "captured_at": time.time(),
        "source": source,
        "mint": first_present(payload.get("mint"), payload.get("token_mint"), decision.get("mint")),
        "decision_id": first_present(payload.get("decision_id"), decision.get("decision_id")),
        "signal_type": first_present(payload.get("type"), payload.get("signal_type"), decision.get("signal_type")),
        "paper_lane": first_present(payload.get("paper_lane"), decision.get("paper_lane")),
        "entry_timestamp": first_present(payload.get("timestamp"), payload.get("time"), decision.get("timestamp")),
        "triggering_wallets": triggering_wallets,
        "wallet_quality": {
            "weighted_wallet_score": first_present(payload.get("weighted_wallet_score"), decision.get("weighted_wallet_score")),
            "wallet_quality": first_present(payload.get("wallet_quality"), decision.get("wallet_quality")),
            "wallet_performance": wallet_performance,
        },
        "cluster": build_cluster(payload, len(triggering_wallets)),
        "market": market,
        "risk": risk,
        "execution_assumptions": {
            "estimated_slippage_pct": first_present(
                payload.get("estimated_slippage_pct"),
                payload.get("slippage_estimate_pct"),
                payload.get("buy_quote_price_impact_pct"),
            ),
            "buy_quote_pass": payload.get("buy_quote_pass"),
            "sell_quote_pass": payload.get("sell_quote_pass"),
            "delay_seconds": first_present(payload.get("execution_delay_seconds"), decision.get("execution_delay_seconds")),
        },
        "scoring": {
            "score": first_present(decision.get("score"), payload.get("total_score")),
            "threshold": first_present(decision.get("threshold"), payload.get("score_threshold")),
            "reasons_tail": safe_list(first_present(decision.get("reasons"), payload.get("score_reasons")))[-12:],
        },
    }
    context["market_regime"] = classify_market_regime(context)
    return context

