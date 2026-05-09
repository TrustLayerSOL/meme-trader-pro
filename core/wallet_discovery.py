import time
from collections import defaultdict


DEFAULT_REVIEW_POLICY = {
    "mode": "REVIEW_ONLY",
    "paper_watch": {
        "min_score": 70,
        "min_early_buy_events": 3,
        "min_winner_mints": 1,
        "max_sell_ratio": 0.65,
    },
    "promotion_review": {
        "min_score": 82,
        "min_early_buy_events": 3,
        "min_winner_mints": 2,
        "min_unique_mints": 2,
        "max_sell_ratio": 0.55,
    },
    "hold_review": {
        "min_score": 50,
        "min_early_buy_events": 1,
        "min_winner_mints": 1,
    },
    "demote_review": {
        "max_score": 42,
        "sell_heavy_ratio": 0.8,
    },
}


def candidate_number(candidate, key, default=0):
    try:
        value = candidate.get(key, default) if isinstance(candidate, dict) else default
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def evaluate_candidate_wallet(candidate, policy=None):
    policy = policy or DEFAULT_REVIEW_POLICY
    candidate = candidate if isinstance(candidate, dict) else {}
    score = candidate_number(candidate, "score")
    early_buy_events = candidate_number(candidate, "early_buy_events")
    winner_mints = candidate_number(candidate, "winner_mints")
    unique_mints = candidate_number(candidate, "unique_mints")
    buy_events = candidate_number(candidate, "buy_events")
    sell_ratio = candidate_number(candidate, "sell_ratio")
    already_tracked = bool(candidate.get("already_tracked"))

    reasons = []
    blockers = []
    action = "REJECT"

    if already_tracked:
        demote = policy["demote_review"]
        if score <= demote["max_score"] or (sell_ratio >= demote["sell_heavy_ratio"] and buy_events == 0):
            action = "DEMOTE_REVIEW"
            blockers.append("tracked wallet has weak current evidence")
        else:
            action = "TRACKED_REVIEW"
            reasons.append("already tracked; review performance before changing status")
        return {
            "action": action,
            "mode": "REVIEW_ONLY",
            "mutates_tracked_wallets": False,
            "reasons": reasons,
            "blockers": blockers,
        }

    promotion = policy["promotion_review"]
    if (
        score >= promotion["min_score"]
        and early_buy_events >= promotion["min_early_buy_events"]
        and winner_mints >= promotion["min_winner_mints"]
        and unique_mints >= promotion["min_unique_mints"]
        and sell_ratio <= promotion["max_sell_ratio"]
    ):
        return {
            "action": "PROMOTION_REVIEW",
            "mode": "REVIEW_ONLY",
            "mutates_tracked_wallets": False,
            "reasons": [
                f"score >= {promotion['min_score']}",
                f"winner mints >= {promotion['min_winner_mints']}",
                f"unique mints >= {promotion['min_unique_mints']}",
            ],
            "blockers": [],
        }

    paper_watch = policy["paper_watch"]
    if score >= paper_watch["min_score"]:
        reasons.append(f"score >= {paper_watch['min_score']}")
    else:
        blockers.append(f"score below {paper_watch['min_score']}")
    if early_buy_events >= paper_watch["min_early_buy_events"]:
        reasons.append(f"early buys >= {paper_watch['min_early_buy_events']}")
    else:
        blockers.append("needs more repeat early-buy evidence")
    if winner_mints >= paper_watch["min_winner_mints"]:
        reasons.append(f"winner mints >= {paper_watch['min_winner_mints']}")
    else:
        blockers.append("needs winner overlap")
    if sell_ratio <= paper_watch["max_sell_ratio"]:
        reasons.append(f"sell ratio <= {paper_watch['max_sell_ratio']}")
    else:
        blockers.append("sell-heavy activity")

    if not blockers:
        action = "PAPER_WATCH"
    else:
        hold = policy["hold_review"]
        if score >= hold["min_score"] and (early_buy_events >= hold["min_early_buy_events"] or winner_mints >= hold["min_winner_mints"]):
            action = "HOLD_REVIEW"
            blockers.append("needs more mints or repeat evidence")
        elif score <= policy["demote_review"]["max_score"]:
            action = "REJECT"
            blockers.append("score too weak for review queue")
        else:
            action = "HOLD_REVIEW"

    return {
        "action": action,
        "mode": "REVIEW_ONLY",
        "mutates_tracked_wallets": False,
        "reasons": reasons,
        "blockers": blockers,
    }


def apply_review_policy(report, policy=None):
    policy = policy or DEFAULT_REVIEW_POLICY
    report = dict(report or {})
    candidates = []
    summary = {
        "promotion_review": 0,
        "paper_watch": 0,
        "hold_review": 0,
        "tracked_review": 0,
        "demote_review": 0,
        "reject": 0,
    }
    for candidate in report.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        row = dict(candidate)
        row["review"] = evaluate_candidate_wallet(row, policy=policy)
        action_key = str(row["review"]["action"]).lower()
        if action_key in summary:
            summary[action_key] += 1
        candidates.append(row)
    report["review_policy"] = policy
    report["review_summary"] = summary
    report["candidates"] = candidates
    return report


def normalize_tracked_wallets(rows):
    wallets = {}
    if isinstance(rows, dict):
        for address, value in rows.items():
            if address:
                wallets[str(address)] = value if isinstance(value, dict) else {"name": str(value)}
        return wallets
    if not isinstance(rows, list):
        return wallets
    for row in rows:
        if not isinstance(row, dict):
            continue
        address = row.get("trackedWalletAddress") or row.get("address") or row.get("wallet")
        if address:
            wallets[str(address)] = row
    return wallets


def token_amount(balance):
    amount = (balance.get("uiTokenAmount") or {}).get("uiAmount")
    if amount is None:
        amount = (balance.get("uiTokenAmount") or {}).get("uiAmountString")
    try:
        return float(amount or 0)
    except Exception:
        return 0.0


def balance_map(balances):
    result = {}
    for row in balances or []:
        if not isinstance(row, dict):
            continue
        owner = row.get("owner")
        mint = row.get("mint")
        if owner and mint:
            result[(owner, mint)] = token_amount(row)
    return result


def extract_owner_deltas(tx, mint):
    meta = tx.get("meta") if isinstance(tx, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    pre = balance_map(meta.get("preTokenBalances"))
    post = balance_map(meta.get("postTokenBalances"))
    rows = []
    for owner, token_mint in sorted(set(pre) | set(post)):
        if token_mint != mint:
            continue
        delta = post.get((owner, token_mint), 0) - pre.get((owner, token_mint), 0)
        if abs(delta) < 1e-12:
            continue
        rows.append({
            "wallet": owner,
            "mint": mint,
            "delta": delta,
            "side": "buy" if delta > 0 else "sell",
            "time": tx.get("blockTime"),
        })
    return rows


class CandidateWalletDiscovery:
    def __init__(self, tracked_wallets=None, existing_performance=None):
        self.tracked_wallets = tracked_wallets or {}
        self.existing_performance = existing_performance if isinstance(existing_performance, dict) else {}

    def build_report(self, local_events=None, mint_evidence=None, generated_at=None):
        generated_at = generated_at or time.time()
        stats = defaultdict(self.default_stats)
        for event in local_events or []:
            self.add_local_event(stats, event)
        for evidence in mint_evidence or []:
            self.add_mint_evidence(stats, evidence)

        candidates = [self.score_wallet(wallet, row) for wallet, row in stats.items()]
        candidates.sort(key=lambda row: (row["score"], row["winner_mints"], row["early_buy_events"]), reverse=True)
        return apply_review_policy({
            "generated_at": generated_at,
            "mode": "WATCH_ONLY_REVIEW",
            "source": "wallet_discovery",
            "summary": {
                "candidate_wallets": len(candidates),
                "untracked_wallets": len([row for row in candidates if not row["already_tracked"]]),
                "tracked_wallets": len([row for row in candidates if row["already_tracked"]]),
            },
            "candidates": candidates,
        })

    def default_stats(self):
        return {
            "buy_events": 0,
            "sell_events": 0,
            "early_buy_events": 0,
            "unique_mints": set(),
            "winner_mints": set(),
            "evidence": [],
            "first_seen": None,
            "last_seen": None,
        }

    def add_local_event(self, stats, event):
        if not isinstance(event, dict):
            return
        wallet = event.get("wallet")
        mint = event.get("mint")
        if not wallet or not mint:
            return
        row = stats[str(wallet)]
        event_type = str(event.get("event_type") or event.get("type") or "").lower()
        if "buy" in event_type:
            row["buy_events"] += 1
        elif "sell" in event_type:
            row["sell_events"] += 1
        else:
            return
        row["unique_mints"].add(str(mint))
        self.touch_times(row, event.get("time") or event.get("timestamp"))

    def add_mint_evidence(self, stats, evidence):
        if not isinstance(evidence, dict):
            return
        mint = evidence.get("mint")
        winner = bool(evidence.get("winner", True))
        for item in evidence.get("early_buyers") or []:
            if not isinstance(item, dict):
                continue
            wallet = item.get("wallet")
            if not wallet:
                continue
            row = stats[str(wallet)]
            row["early_buy_events"] += 1
            if mint:
                row["unique_mints"].add(str(mint))
                if winner:
                    row["winner_mints"].add(str(mint))
            row["evidence"].append({
                "mint": mint,
                "side": "early_buy",
                "delta": item.get("delta"),
                "time": item.get("time"),
            })
            self.touch_times(row, item.get("time"))

    def touch_times(self, row, timestamp):
        try:
            timestamp = float(timestamp)
        except Exception:
            timestamp = None
        if timestamp is None:
            return
        row["first_seen"] = timestamp if row["first_seen"] is None else min(row["first_seen"], timestamp)
        row["last_seen"] = timestamp if row["last_seen"] is None else max(row["last_seen"], timestamp)

    def score_wallet(self, wallet, row):
        buy_events = int(row["buy_events"])
        sell_events = int(row["sell_events"])
        early_buy_events = int(row["early_buy_events"])
        unique_mints = len(row["unique_mints"])
        winner_mints = len(row["winner_mints"])
        total_events = buy_events + sell_events
        sell_ratio = sell_events / total_events if total_events else 0

        score = 35
        reasons = []
        if early_buy_events:
            gain = min(30, early_buy_events * 8)
            score += gain
            reasons.append(f"{early_buy_events} early buy event(s)")
        if winner_mints:
            gain = min(25, winner_mints * 10)
            score += gain
            reasons.append(f"{winner_mints} winner mint overlap(s)")
        if buy_events:
            gain = min(12, buy_events * 2)
            score += gain
            reasons.append(f"{buy_events} local buy event(s)")
        if unique_mints >= 3:
            score += min(12, unique_mints * 2)
            reasons.append(f"{unique_mints} unique mints")
        if sell_ratio > 0.8 and buy_events == 0:
            score -= 25
            reasons.append("seller-only/noisy in local window")
        elif sell_ratio > 0.7:
            score -= 12
            reasons.append("sell-heavy local activity")

        existing = self.existing_performance.get("wallets", {}).get(wallet, {})
        existing_score = existing.get("score")
        if existing_score is not None:
            score = (score * 0.75) + (float(existing_score) * 0.25)
            reasons.append(f"existing performance score {existing_score}")

        score = max(0, min(100, round(score, 2)))
        already_tracked = wallet in self.tracked_wallets
        return {
            "wallet": wallet,
            "already_tracked": already_tracked,
            "score": score,
            "recommended_tier": self.recommended_tier(score, already_tracked),
            "buy_events": buy_events,
            "sell_events": sell_events,
            "early_buy_events": early_buy_events,
            "unique_mints": unique_mints,
            "winner_mints": winner_mints,
            "sell_ratio": round(sell_ratio, 4),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "reasons": reasons or ["low evidence wallet"],
            "evidence": row["evidence"][:12],
        }

    def recommended_tier(self, score, already_tracked):
        if score >= 82:
            return "tier_1_candidate" if not already_tracked else "tracked_review"
        if score >= 62:
            return "tier_2_confirm" if not already_tracked else "tracked_review"
        if score >= 42:
            return "watch_only"
        return "avoid"
