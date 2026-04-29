from collections import Counter

from core.edge_analyzer import EdgeAnalyzer
from core.strategy_guard import StrategyGuard


class ReplayAnalyzer:
    def __init__(self):
        self.edge_analyzer = EdgeAnalyzer()
        self.strategy_guard = StrategyGuard()

    def replay_alert(self, alert, paper_state=None):
        market_info = alert.get("market_info") or {}
        edge = self.edge_analyzer.analyze(
            wallet_count=alert.get("wallet_count", 0),
            weighted_wallet_score=alert.get("weighted_wallet_score", 0),
            repeated_buys=0,
            wallet_quality=alert.get("wallet_quality") or {},
            wallet_performance=alert.get("wallet_performance") or {},
            liquidity_usd=market_info.get("liquidity", 0),
            volume_usd=market_info.get("volume", 0),
            true_launch_age_seconds=alert.get("true_launch_age_seconds"),
            token_age_seconds=alert.get("token_age_seconds"),
            social_match=alert.get("social_match") or {},
            rug_result={
                "risk_score": alert.get("risk_score", 0),
                "risk_label": alert.get("risk_label", "UNKNOWN"),
                "hard_block": alert.get("hard_block", False),
            },
            decision_score=alert.get("total_score", 0),
        )

        guard = {
            "action": "ALLOW",
            "reason": "No paper state supplied",
            "stats": None,
        }
        if paper_state is not None:
            guard = self.strategy_guard.evaluate_family(alert.get("type"), paper_state)

        action = "IGNORE"
        if edge["paper_trade_worthy"]:
            action = "PAPER_TRADE"
        elif edge["quote_worthy"]:
            action = "QUOTE_CHECK"
        elif edge["edge_verdict"] == "WATCHLIST":
            action = "WATCHLIST"

        if guard["action"] == "BLOCK" and action in ["PAPER_TRADE", "QUOTE_CHECK"]:
            action = "GUARD_BLOCKED"

        return {
            "mint": alert.get("mint"),
            "type": alert.get("type"),
            "action": action,
            "edge_score": edge["edge_score"],
            "edge_verdict": edge["edge_verdict"],
            "quote_worthy": edge["quote_worthy"],
            "paper_trade_worthy": edge["paper_trade_worthy"],
            "positives": edge["positives"],
            "risks": edge["risks"],
            "strategy_guard_action": guard["action"],
            "strategy_guard_reason": guard["reason"],
            "risk_label": alert.get("risk_label"),
            "wallet_count": alert.get("wallet_count"),
            "weighted_wallet_score": alert.get("weighted_wallet_score"),
            "liquidity": market_info.get("liquidity"),
            "volume": market_info.get("volume"),
            "true_launch_age_seconds": alert.get("true_launch_age_seconds"),
            "total_score": alert.get("total_score"),
        }

    def replay(self, alerts, paper_state=None):
        results = [self.replay_alert(alert, paper_state) for alert in alerts]
        actions = Counter(row["action"] for row in results)
        verdicts = Counter(row["edge_verdict"] for row in results)
        guard_actions = Counter(row["strategy_guard_action"] for row in results)

        ranked = sorted(
            results,
            key=lambda row: (
                row["action"] == "PAPER_TRADE",
                row["action"] == "QUOTE_CHECK",
                row["edge_score"],
                row.get("liquidity") or 0,
            ),
            reverse=True,
        )

        return {
            "total_alerts": len(results),
            "actions": actions,
            "verdicts": verdicts,
            "guard_actions": guard_actions,
            "ranked": ranked,
            "calibration": self.calibrate(results),
        }

    def calibrate(self, results):
        rows = []

        for threshold in [20, 28, 35, 45, 55, 62, 75]:
            candidates = [
                row for row in results
                if row["edge_score"] >= threshold
                and row["strategy_guard_action"] != "BLOCK"
            ]
            high_risk = [row for row in candidates if row.get("risk_label") == "HIGH_RISK"]

            rows.append({
                "edge_threshold": threshold,
                "candidates": len(candidates),
                "high_risk": len(high_risk),
                "quote_ready": len([
                    row for row in candidates
                    if row.get("liquidity") and row.get("liquidity") >= 5000
                ]),
            })

        return rows
