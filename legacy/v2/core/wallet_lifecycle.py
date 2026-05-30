import time


DEFAULT_LIFECYCLE_POLICY = {
    "trusted_review": {
        "min_entries": 5,
        "min_score": 78,
        "min_win_rate": 0.6,
        "min_avg_pnl": 8,
    },
    "keep_trusted": {
        "min_score": 55,
        "min_avg_pnl": -4,
    },
    "demote_review": {
        "min_entries": 3,
        "max_score": 35,
        "max_avg_pnl": -8,
    },
    "paper_watch": {
        "candidate_actions": {"PAPER_WATCH", "PROMOTION_REVIEW"},
    },
}


def safe_number(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def wallet_key(row):
    if isinstance(row, dict):
        return row.get("wallet") or row.get("address") or row.get("trackedWalletAddress")
    return row


def performance_metrics(performance):
    performance = performance if isinstance(performance, dict) else {}
    entries = int(safe_number(performance.get("paper_entries"), 0))
    wins = int(safe_number(performance.get("wins"), 0))
    losses = int(safe_number(performance.get("losses"), 0))
    score = safe_number(performance.get("score"), 50)
    avg_pnl = safe_number(performance.get("avg_pnl"), 0)
    total_pnl = safe_number(performance.get("total_pnl"), 0)
    win_rate = wins / entries if entries else 0
    return {
        "entries": entries,
        "wins": wins,
        "losses": losses,
        "score": score,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
        "win_rate": round(win_rate, 4),
    }


def behavior_for_wallet(behavior, wallet):
    behavior = behavior if isinstance(behavior, dict) else {}
    wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    row = wallets.get(wallet) if isinstance(wallets.get(wallet), dict) else {}
    return {
        "labels": row.get("labels") if isinstance(row.get("labels"), list) else [],
        "rolling": row.get("rolling") if isinstance(row.get("rolling"), dict) else {},
        "postmortem": row.get("postmortem") if isinstance(row.get("postmortem"), dict) else {},
    }


def with_behavior(decision, behavior, wallet):
    detail = behavior_for_wallet(behavior, wallet)
    decision["labels"] = detail["labels"]
    decision["rolling"] = detail["rolling"]
    decision["postmortem"] = detail["postmortem"]
    return decision


def evaluate_wallet_lifecycle(wallet, performance=None, current_source="candidate", policy=None, behavior=None):
    policy = policy or DEFAULT_LIFECYCLE_POLICY
    metrics = performance_metrics(performance)
    reasons = []
    blockers = []
    source = str(current_source or "candidate")

    demote = policy["demote_review"]
    if metrics["entries"] >= demote["min_entries"] and (
        metrics["score"] <= demote["max_score"] or metrics["avg_pnl"] <= demote["max_avg_pnl"]
    ):
        if metrics["score"] <= demote["max_score"]:
            blockers.append("low wallet performance score")
        if metrics["avg_pnl"] <= demote["max_avg_pnl"]:
            blockers.append("negative average paper PnL")
        return with_behavior({
            "wallet": wallet,
            "action": "DEMOTE_OFF_WATCH_REVIEW",
            "target_tier": "demote_review",
            "current_source": source,
            "mutates_live_tracking": False,
            "live_trade_driver": False,
            "metrics": metrics,
            "reasons": reasons,
            "blockers": blockers,
        }, behavior, wallet)

    trusted = policy["trusted_review"]
    if (
        metrics["entries"] >= trusted["min_entries"]
        and metrics["score"] >= trusted["min_score"]
        and metrics["win_rate"] >= trusted["min_win_rate"]
        and metrics["avg_pnl"] >= trusted["min_avg_pnl"]
    ):
        reasons.extend([
            f"paper entries >= {trusted['min_entries']}",
            f"score >= {trusted['min_score']}",
            f"win rate >= {trusted['min_win_rate']}",
            f"avg pnl >= {trusted['min_avg_pnl']}",
        ])
        return with_behavior({
            "wallet": wallet,
            "action": "PROMOTE_TO_TRUSTED_REVIEW",
            "target_tier": "trusted_review",
            "current_source": source,
            "mutates_live_tracking": False,
            "live_trade_driver": False,
            "metrics": metrics,
            "reasons": reasons,
            "blockers": blockers,
        }, behavior, wallet)

    keep = policy["keep_trusted"]
    if source == "tracked" and metrics["score"] >= keep["min_score"] and metrics["avg_pnl"] >= keep["min_avg_pnl"]:
        return with_behavior({
            "wallet": wallet,
            "action": "KEEP_TRUSTED",
            "target_tier": "tracked",
            "current_source": source,
            "mutates_live_tracking": False,
            "live_trade_driver": False,
            "metrics": metrics,
            "reasons": ["tracked wallet remains above demotion threshold"],
            "blockers": blockers,
        }, behavior, wallet)

    if source == "paper_watch":
        return with_behavior({
            "wallet": wallet,
            "action": "KEEP_PAPER_WATCH",
            "target_tier": "paper_watch",
            "current_source": source,
            "mutates_live_tracking": False,
            "live_trade_driver": False,
            "metrics": metrics,
            "reasons": ["still collecting paper sample"],
            "blockers": blockers,
        }, behavior, wallet)

    return with_behavior({
        "wallet": wallet,
        "action": "OBSERVE",
        "target_tier": "candidate",
        "current_source": source,
        "mutates_live_tracking": False,
        "live_trade_driver": False,
        "metrics": metrics,
        "reasons": ["not enough paper outcome evidence"],
        "blockers": blockers,
    }, behavior, wallet)


def candidate_should_enter_paper_watch(candidate, policy=None):
    policy = policy or DEFAULT_LIFECYCLE_POLICY
    review = candidate.get("review") if isinstance(candidate, dict) else {}
    action = review.get("action") if isinstance(review, dict) else None
    return action in policy["paper_watch"]["candidate_actions"]


def normalize_wallet_set(rows):
    wallets = set()
    for row in rows or []:
        wallet = wallet_key(row)
        if wallet:
            wallets.add(str(wallet))
    return wallets


def sync_paper_watch_wallets(current_wallets=None, candidate_report=None, performance=None, generated_at=None, policy=None, bad_wallets=None):
    policy = policy or DEFAULT_LIFECYCLE_POLICY
    generated_at = generated_at or time.time()
    performance = performance if isinstance(performance, dict) else {}
    perf_wallets = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    blocked_wallets = normalize_wallet_set(bad_wallets)

    rows = {}
    for row in current_wallets or []:
        wallet = wallet_key(row)
        if not wallet:
            continue
        next_row = dict(row) if isinstance(row, dict) else {"wallet": str(wallet)}
        if str(wallet) in blocked_wallets:
            next_row["status"] = "demote_review"
            next_row["live_trade_driver"] = False
            next_row.setdefault("blocked_reason", "bad_wallet_list")
        rows[str(wallet)] = next_row

    for candidate in (candidate_report or {}).get("candidates") or []:
        if not isinstance(candidate, dict) or not candidate_should_enter_paper_watch(candidate, policy=policy):
            continue
        wallet = candidate.get("wallet")
        if not wallet:
            continue
        if str(wallet) in blocked_wallets:
            rows.setdefault(str(wallet), {
                "wallet": str(wallet),
                "status": "demote_review",
                "source": "bad_wallet_list",
                "added_at": generated_at,
                "score_at_add": candidate.get("score"),
                "review_action_at_add": (candidate.get("review") or {}).get("action"),
                "live_trade_driver": False,
                "blocked_reason": "bad_wallet_list",
            })
            continue
        rows.setdefault(str(wallet), {
            "wallet": str(wallet),
            "status": "paper_watch",
            "source": "candidate_wallet_discovery",
            "added_at": generated_at,
            "score_at_add": candidate.get("score"),
            "review_action_at_add": (candidate.get("review") or {}).get("action"),
            "live_trade_driver": False,
        })

    wallet_rows = []
    for wallet, row in rows.items():
        lifecycle = evaluate_wallet_lifecycle(
            wallet,
            performance=perf_wallets.get(wallet, {}),
            current_source=row.get("status") or "paper_watch",
            policy=policy,
        )
        next_row = dict(row)
        next_row.setdefault("wallet", wallet)
        next_row.setdefault("status", "paper_watch")
        if wallet in blocked_wallets:
            next_row["status"] = "demote_review"
            next_row.setdefault("blocked_reason", "bad_wallet_list")
        next_row["live_trade_driver"] = False
        next_row["lifecycle"] = lifecycle
        wallet_rows.append(next_row)

    wallet_rows.sort(key=lambda row: (
        row.get("lifecycle", {}).get("metrics", {}).get("score", 0),
        row.get("score_at_add") or 0,
        row.get("added_at") or 0,
    ), reverse=True)
    return {
        "generated_at": generated_at,
        "mode": "PAPER_WATCH_ONLY",
        "live_execution_locked": True,
        "summary": {
            "paper_watch_wallets": len(wallet_rows),
            "active_paper_watch_wallets": len([row for row in wallet_rows if row.get("status") != "demote_review"]),
            "blocked_bad_wallets": len([row for row in wallet_rows if row.get("blocked_reason") == "bad_wallet_list"]),
            "promotion_review": len([row for row in wallet_rows if row["lifecycle"]["action"] == "PROMOTE_TO_TRUSTED_REVIEW"]),
            "demote_review": len([row for row in wallet_rows if row["lifecycle"]["action"] == "DEMOTE_OFF_WATCH_REVIEW"]),
        },
        "wallets": wallet_rows,
    }


def build_wallet_lifecycle_report(tracked_wallets=None, paper_watch_wallets=None, candidate_report=None, performance=None, generated_at=None, behavior=None):
    generated_at = generated_at or time.time()
    performance = performance if isinstance(performance, dict) else {}
    perf_wallets = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    rows = []
    seen = set()

    tracked = tracked_wallets if isinstance(tracked_wallets, dict) else {}
    for wallet in tracked:
        seen.add(wallet)
        rows.append({
            "wallet": wallet,
            "source": "tracked",
            "lifecycle": evaluate_wallet_lifecycle(wallet, perf_wallets.get(wallet, {}), current_source="tracked", behavior=behavior),
        })

    for row in paper_watch_wallets or []:
        wallet = wallet_key(row)
        if not wallet or wallet in seen:
            continue
        seen.add(wallet)
        rows.append({
            "wallet": wallet,
            "source": "paper_watch",
            "lifecycle": evaluate_wallet_lifecycle(wallet, perf_wallets.get(wallet, {}), current_source="paper_watch", behavior=behavior),
        })

    for candidate in (candidate_report or {}).get("candidates") or []:
        wallet = wallet_key(candidate)
        if not wallet or wallet in seen:
            continue
        seen.add(wallet)
        rows.append({
            "wallet": wallet,
            "source": "candidate",
            "lifecycle": evaluate_wallet_lifecycle(wallet, perf_wallets.get(wallet, {}), current_source="candidate", behavior=behavior),
        })

    rows.sort(key=lambda row: (
        row["lifecycle"]["target_tier"] != "demote_review",
        row["lifecycle"]["metrics"]["score"],
    ), reverse=True)
    return {
        "generated_at": generated_at,
        "mode": "REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {
            "wallets": len(rows),
            "promotion_review": len([row for row in rows if row["lifecycle"]["action"] == "PROMOTE_TO_TRUSTED_REVIEW"]),
            "demote_review": len([row for row in rows if row["lifecycle"]["action"] == "DEMOTE_OFF_WATCH_REVIEW"]),
        },
        "wallets": rows,
    }
