def safe_float(value, default=0.0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _with_exploration(decision, enabled, allowed, reason, threshold, size_usd):
    updated = dict(decision or {})
    updated.setdefault("reasons", [])
    updated["paper_lane"] = "main"
    updated["main_strategy_should_trade"] = bool(updated.get("should_trade"))
    updated["live_should_trade"] = bool(updated.get("should_trade"))
    updated["exploration"] = {
        "enabled": bool(enabled),
        "allowed": bool(allowed),
        "reason": reason,
        "threshold": threshold,
        "size_usd": size_usd,
    }
    return updated


def evaluate_paper_exploration(
    decision,
    settings,
    rug_result,
    market_sanity,
    buy_quote_analysis,
    sell_quote_analysis,
    edge_result,
    position_size_usd,
):
    settings = settings if isinstance(settings, dict) else {}
    decision = dict(decision or {})
    decision["reasons"] = list(decision.get("reasons") or [])

    threshold = safe_float(settings.get("paper_exploration_score_threshold"), 52.0)
    edge_threshold = safe_float(settings.get("paper_exploration_min_edge_score"), 55.0)
    exploration_size = safe_float(settings.get("paper_exploration_size_usd"), 10.0)
    enabled = safe_bool(settings.get("paper_exploration_enabled"), False)
    score = safe_float(decision.get("score"), 0.0)
    edge_score = safe_float((edge_result or {}).get("edge_score"), 0.0)

    if decision.get("should_trade"):
        return {
            "decision": _with_exploration(decision, enabled, False, "main_strategy_passed", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if not enabled:
        return {
            "decision": _with_exploration(decision, enabled, False, "disabled", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if (rug_result or {}).get("hard_block"):
        return {
            "decision": _with_exploration(decision, enabled, False, "hard_risk_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if (decision.get("strategy_guard") or {}).get("action") == "BLOCK":
        return {
            "decision": _with_exploration(decision, enabled, False, "strategy_guard_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if decision.get("confirmation") and not (decision.get("confirmation") or {}).get("allow", True):
        return {
            "decision": _with_exploration(decision, enabled, False, "confirmation_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if isinstance(market_sanity, dict) and not market_sanity.get("allow", True):
        return {
            "decision": _with_exploration(decision, enabled, False, "market_sanity_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if not (buy_quote_analysis or {}).get("pass", False):
        return {
            "decision": _with_exploration(decision, enabled, False, "buy_quote_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if not (sell_quote_analysis or {}).get("pass", False):
        return {
            "decision": _with_exploration(decision, enabled, False, "exit_liquidity_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if safe_float(position_size_usd, 0.0) <= 0:
        return {
            "decision": _with_exploration(decision, enabled, False, "zero_position_size", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    score_eligible = score >= threshold
    edge_eligible = (
        bool((edge_result or {}).get("paper_trade_worthy"))
        or edge_score >= edge_threshold
    )
    if not (score_eligible or edge_eligible):
        return {
            "decision": _with_exploration(decision, enabled, False, "below_exploration_threshold", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    size = max(0.0, min(safe_float(position_size_usd, exploration_size), exploration_size))
    updated = _with_exploration(decision, enabled, True, "safe_near_miss", threshold, size)
    updated["should_trade"] = True
    updated["paper_should_trade"] = True
    updated["live_should_trade"] = False
    updated["paper_lane"] = "exploration"
    updated["reasons"].append(
        f"PAPER EXPLORATION: safe near-miss paper sample at score {round(score, 2)} / {round(threshold, 2)}"
    )
    return {
        "decision": updated,
        "position_size_usd": size,
    }
