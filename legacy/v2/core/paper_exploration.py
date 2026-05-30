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


def _quote_passed(quote_analysis):
    return bool((quote_analysis or {}).get("pass", False))


def _quote_reason(quote_analysis, default):
    if not isinstance(quote_analysis, dict):
        return default
    return quote_analysis.get("reason") or default


def _quote_was_checked(quote_analysis):
    reason = str(_quote_reason(quote_analysis, "")).lower()
    if not reason:
        return False
    skipped_markers = (
        "not_checked",
        "budget",
        "below_swap_quote_quality_gate",
        "cooldown",
    )
    return not any(marker in reason for marker in skipped_markers)


def _risk_label(decision, rug_result):
    for source in (decision or {}, rug_result or {}):
        if not isinstance(source, dict):
            continue
        for key in ("risk_label", "token_risk_label", "mechanics_risk_label"):
            value = source.get(key)
            if value:
                return str(value).upper()
    return ""


def _market_metric(decision, market_sanity, *keys):
    sources = []
    if isinstance(decision, dict):
        sources.extend([
            decision,
            decision.get("market_info"),
            decision.get("token_info"),
            decision.get("scanner_market_info"),
        ])
    sources.append(market_sanity)

    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return safe_float(source.get(key), None)
    return None


def _suppressed_exploration(decision, enabled, reason, threshold, detail):
    updated = _with_exploration(decision, enabled, False, reason, threshold, 0)
    updated["should_trade"] = False
    updated["paper_should_trade"] = False
    updated["live_should_trade"] = False
    updated["exploration"]["suppression"] = detail
    updated["reasons"].append(
        "PAPER EXPLORATION SUPPRESSED: repeat bad-sample pattern blocked from opening another paper trade"
    )
    return {
        "decision": updated,
        "position_size_usd": 0,
    }


def summarize_exploration_performance(paper_state):
    closed = []
    for trade in (paper_state or {}).get("closed_trades", []) or []:
        if not isinstance(trade, dict):
            continue
        lane = trade.get("paper_lane") or (trade.get("signal_metadata") or {}).get("paper_lane")
        if lane != "exploration":
            continue
        pnl_pct = safe_float(trade.get("total_pnl_pct", trade.get("pnl_pct")), None)
        if pnl_pct is None:
            continue
        closed.append(pnl_pct)

    if not closed:
        return {
            "closed": 0,
            "wins": 0,
            "losses": 0,
            "avg_pnl_pct": 0,
            "win_rate_pct": 0,
        }

    wins = len([pnl for pnl in closed if pnl > 0])
    return {
        "closed": len(closed),
        "wins": wins,
        "losses": len(closed) - wins,
        "avg_pnl_pct": round(sum(closed) / len(closed), 4),
        "win_rate_pct": round((wins / len(closed)) * 100, 4),
    }


def exploration_auto_pause_reason(settings, paper_state):
    if not safe_bool(settings.get("paper_exploration_auto_pause_enabled"), True):
        return None

    stats = summarize_exploration_performance(paper_state)
    min_closed = int(safe_float(settings.get("paper_exploration_auto_pause_min_closed"), 5))
    max_avg_pnl = safe_float(settings.get("paper_exploration_auto_pause_max_avg_pnl_pct"), -10)
    max_win_rate = safe_float(settings.get("paper_exploration_auto_pause_max_win_rate_pct"), 20)

    if stats["closed"] < min_closed:
        return None

    if stats["avg_pnl_pct"] <= max_avg_pnl and stats["win_rate_pct"] <= max_win_rate:
        return {
            "reason": "auto_paused_negative_sample",
            "stats": stats,
            "min_closed": min_closed,
            "max_avg_pnl_pct": max_avg_pnl,
            "max_win_rate_pct": max_win_rate,
        }
    return None


def _route_failed_observation(
    decision,
    settings,
    buy_quote_analysis,
    sell_quote_analysis,
    edge_result,
):
    enabled = safe_bool(settings.get("paper_exploration_route_failed_enabled"), False)
    score = safe_float(decision.get("score"), 0.0)
    edge_score = safe_float((edge_result or {}).get("edge_score"), 0.0)
    score_threshold = safe_float(settings.get("paper_exploration_route_failed_score_threshold"), 70.0)
    edge_threshold = safe_float(settings.get("paper_exploration_route_failed_min_edge_score"), 65.0)
    size = safe_float(settings.get("paper_exploration_route_failed_size_usd"), 5.0)
    buy_pass = _quote_passed(buy_quote_analysis)
    sell_pass = _quote_passed(sell_quote_analysis)

    if buy_pass and sell_pass:
        return None

    if not (_quote_was_checked(buy_quote_analysis) or _quote_was_checked(sell_quote_analysis)):
        return None

    score_eligible = score >= score_threshold
    edge_eligible = (
        bool((edge_result or {}).get("paper_trade_worthy"))
        or edge_score >= edge_threshold
    )
    if not (enabled and size > 0 and (score_eligible or edge_eligible)):
        return None

    updated = _with_exploration(
        decision,
        enabled,
        True,
        "route_failed_observation",
        score_threshold,
        size,
    )
    updated["should_trade"] = True
    updated["paper_should_trade"] = True
    updated["live_should_trade"] = False
    updated["paper_lane"] = "exploration"
    updated["exploration"].update({
        "route_observation_only": True,
        "route_feasibility_passed": False,
        "buy_quote_pass": buy_pass,
        "sell_quote_pass": sell_pass,
        "buy_quote_reason": _quote_reason(buy_quote_analysis, "buy_quote_failed"),
        "sell_quote_reason": _quote_reason(sell_quote_analysis, "sell_quote_failed"),
        "edge_threshold": edge_threshold,
    })
    updated["reasons"].append(
        "PAPER EXPLORATION ROUTE OBSERVATION: strong signal sampled with failed route checks; live execution remains blocked"
    )
    return {
        "decision": updated,
        "position_size_usd": size,
    }


def _confirmation_block_observation(
    decision,
    settings,
    rug_result,
    market_sanity,
    buy_quote_analysis,
    sell_quote_analysis,
    edge_result,
):
    confirmation = decision.get("confirmation") if isinstance(decision, dict) else {}
    if not (confirmation and not confirmation.get("allow", True)):
        return None

    enabled = safe_bool(settings.get("paper_exploration_confirmation_blocked_enabled"), False)
    if not enabled:
        return None

    if isinstance(market_sanity, dict) and not market_sanity.get("allow", True):
        return None

    buy_pass = _quote_passed(buy_quote_analysis)
    sell_pass = _quote_passed(sell_quote_analysis)
    if not (buy_pass and sell_pass):
        return None

    score = safe_float(decision.get("score"), 0.0)
    edge_score = safe_float((edge_result or {}).get("edge_score"), 0.0)
    score_threshold = safe_float(settings.get("paper_exploration_confirmation_score_threshold"), 70.0)
    edge_threshold = safe_float(settings.get("paper_exploration_confirmation_min_edge_score"), 60.0)
    size = safe_float(settings.get("paper_exploration_confirmation_size_usd"), 5.0)
    score_eligible = score >= score_threshold
    edge_eligible = (
        bool((edge_result or {}).get("paper_trade_worthy"))
        or edge_score >= edge_threshold
    )
    if not (size > 0 and (score_eligible or edge_eligible)):
        return None

    if safe_bool(settings.get("paper_exploration_bad_sample_suppression_enabled"), True):
        risk_label = _risk_label(decision, rug_result)
        medium_score_floor = safe_float(
            settings.get("paper_exploration_confirmation_medium_risk_min_score"),
            68.0,
        )
        medium_edge_floor = safe_float(
            settings.get("paper_exploration_confirmation_medium_risk_min_edge_score"),
            60.0,
        )
        liquidity = _market_metric(
            decision,
            market_sanity,
            "liquidity",
            "liquidity_usd",
            "entry_liquidity_usd",
        )
        market_cap = _market_metric(decision, market_sanity, "market_cap", "marketCap", "fdv")
        min_liquidity = safe_float(
            settings.get("paper_exploration_confirmation_min_liquidity_usd"),
            25_000.0,
        )
        min_market_cap = safe_float(
            settings.get("paper_exploration_confirmation_min_market_cap_usd"),
            50_000.0,
        )

        if risk_label and risk_label not in {"LOW_RISK", "PASS", "SAFE"}:
            if score < medium_score_floor and edge_score < medium_edge_floor:
                return _suppressed_exploration(
                    decision,
                    enabled,
                    "bad_sample_suppressed_medium_risk_confirmation",
                    score_threshold,
                    {
                        "risk_label": risk_label,
                        "score": score,
                        "edge_score": edge_score,
                        "min_score": medium_score_floor,
                        "min_edge_score": medium_edge_floor,
                    },
                )

        if liquidity is not None and liquidity < min_liquidity:
            return _suppressed_exploration(
                decision,
                enabled,
                "bad_sample_suppressed_thin_confirmation",
                score_threshold,
                {
                    "liquidity": liquidity,
                    "min_liquidity": min_liquidity,
                    "market_cap": market_cap,
                    "min_market_cap": min_market_cap,
                },
            )

        if market_cap is not None and market_cap < min_market_cap:
            return _suppressed_exploration(
                decision,
                enabled,
                "bad_sample_suppressed_small_cap_confirmation",
                score_threshold,
                {
                    "liquidity": liquidity,
                    "min_liquidity": min_liquidity,
                    "market_cap": market_cap,
                    "min_market_cap": min_market_cap,
                },
            )

    updated = _with_exploration(
        decision,
        enabled,
        True,
        "confirmation_block_observation",
        score_threshold,
        size,
    )
    updated["should_trade"] = True
    updated["paper_should_trade"] = True
    updated["live_should_trade"] = False
    updated["paper_lane"] = "exploration"
    updated["exploration"].update({
        "confirmation_observation_only": True,
        "confirmation_reasons": confirmation.get("reasons", []),
        "route_feasibility_passed": True,
        "buy_quote_pass": buy_pass,
        "sell_quote_pass": sell_pass,
        "buy_quote_reason": _quote_reason(buy_quote_analysis, "quote_passed"),
        "sell_quote_reason": _quote_reason(sell_quote_analysis, "quote_passed"),
        "edge_threshold": edge_threshold,
    })
    updated["reasons"].append(
        "PAPER EXPLORATION CONFIRMATION OBSERVATION: strong quote-pass signal sampled despite confirmation block; live execution remains blocked"
    )
    return {
        "decision": updated,
        "position_size_usd": size,
    }


def evaluate_paper_exploration(
    decision,
    settings,
    rug_result,
    market_sanity,
    buy_quote_analysis,
    sell_quote_analysis,
    edge_result,
    position_size_usd,
    paper_state=None,
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

    auto_pause = exploration_auto_pause_reason(settings, paper_state)
    if auto_pause:
        updated = _with_exploration(
            decision,
            enabled,
            False,
            auto_pause["reason"],
            threshold,
            position_size_usd,
        )
        updated["exploration"]["auto_pause"] = auto_pause
        updated["should_trade"] = False
        updated["live_should_trade"] = False
        updated["reasons"].append(
            "PAPER EXPLORATION AUTO-PAUSED: exploration lane paper sample has negative expectancy"
        )
        return {
            "decision": updated,
            "position_size_usd": 0,
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

    if decision.get("wallet_main_quality_block"):
        return {
            "decision": _with_exploration(decision, enabled, False, "wallet_main_quality_block", threshold, position_size_usd),
            "position_size_usd": 0,
        }

    if decision.get("confirmation") and not (decision.get("confirmation") or {}).get("allow", True):
        confirmation_observation = _confirmation_block_observation(
            decision=decision,
            settings=settings,
            rug_result=rug_result,
            market_sanity=market_sanity,
            buy_quote_analysis=buy_quote_analysis,
            sell_quote_analysis=sell_quote_analysis,
            edge_result=edge_result,
        )
        if confirmation_observation:
            return confirmation_observation

        return {
            "decision": _with_exploration(decision, enabled, False, "confirmation_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    if isinstance(market_sanity, dict) and not market_sanity.get("allow", True):
        return {
            "decision": _with_exploration(decision, enabled, False, "market_sanity_block", threshold, position_size_usd),
            "position_size_usd": position_size_usd,
        }

    route_observation = _route_failed_observation(
        decision=decision,
        settings=settings,
        buy_quote_analysis=buy_quote_analysis,
        sell_quote_analysis=sell_quote_analysis,
        edge_result=edge_result,
    )
    if route_observation:
        return route_observation

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
