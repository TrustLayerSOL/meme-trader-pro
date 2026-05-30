import time
from collections import Counter

from core.execution_safety import ExecutionSafetyGate
from core.performance_analyzer import PerformanceAnalyzer
from core.token_console import TokenConsole
from core.wallet_copy_engine import WalletCopyEngine


class OperatorBrief:
    def build(self, state, paper_state, wallet_perf, watchlist, runtime_status, candidate_ledger):
        token_rows = TokenConsole().rows(state, paper_state, watchlist, candidate_ledger)
        action_counts = Counter(row.get("recommended_action") or "REVIEW" for row in token_rows)
        performance = PerformanceAnalyzer().analyze(paper_state)
        copy_counts = Counter(row["recommendation"] for row in WalletCopyEngine().wallet_rows(wallet_perf, limit=200))
        safety = ExecutionSafetyGate().report()
        runtime = self.runtime_summary(runtime_status)

        highlights = [
            {
                "label": "Execution Mode",
                "value": safety["overall"],
                "status": "OK" if not safety["live_allowed"] else "WARN",
                "detail": "Live trading locked" if not safety["live_allowed"] else "Live gate open",
            },
            {
                "label": "Paper PnL",
                "value": round(float(performance.get("total_pnl", 0) or 0), 2),
                "status": "OK" if float(performance.get("total_pnl", 0) or 0) >= 0 else "WARN",
                "detail": f"Win rate {performance.get('win_rate', 0)}%",
            },
            {
                "label": "Token Actions",
                "value": len(token_rows),
                "status": "OK",
                "detail": self.action_detail(action_counts),
            },
            {
                "label": "Copy Engine",
                "value": copy_counts.get("COPY", 0) + copy_counts.get("PAPER_COPY", 0),
                "status": "OK" if copy_counts.get("COPY", 0) or copy_counts.get("PAPER_COPY", 0) else "WATCH",
                "detail": f"{copy_counts.get('FADE', 0)} fade wallets",
            },
        ]

        tasks = self.tasks(action_counts, runtime, performance, copy_counts)

        return {
            "highlights": highlights,
            "tasks": tasks,
            "runtime": runtime,
            "action_counts": dict(action_counts),
            "copy_counts": dict(copy_counts),
        }

    def runtime_summary(self, runtime_status):
        runtime_status = runtime_status or {}
        stale = []
        missing = []
        now = time.time()

        for name in ["bot", "websocket", "scanner", "market", "quotes", "watchdog"]:
            component = runtime_status.get(name, {})
            updated_at = self.safe_float(component.get("updated_at"), None)
            if updated_at is None:
                missing.append(name)
            elif now - updated_at > 180:
                stale.append(name)

        if missing:
            status = "MISSING"
        elif stale:
            status = "STALE"
        else:
            status = "OK"

        return {
            "status": status,
            "missing": missing,
            "stale": stale,
        }

    def tasks(self, action_counts, runtime, performance, copy_counts):
        tasks = []

        if runtime["missing"] or runtime["stale"]:
            tasks.append({
                "priority": "HIGH",
                "task": "Start or inspect stale runtime components",
                "why": ", ".join(runtime["missing"] + runtime["stale"]),
            })

        if action_counts.get("REVIEW_EXIT", 0) or action_counts.get("PROTECTION_ALERT", 0):
            tasks.append({
                "priority": "HIGH",
                "task": "Review protected/open token exits",
                "why": f"{action_counts.get('REVIEW_EXIT', 0)} exit reviews, {action_counts.get('PROTECTION_ALERT', 0)} protection alerts",
            })

        expectancy = float(performance.get("expectancy", 0) or 0)
        if expectancy < 0:
            tasks.append({
                "priority": "MEDIUM",
                "task": "Keep strategy guard strict",
                "why": f"Paper expectancy is {expectancy:.2f}",
            })

        if not copy_counts.get("COPY", 0) and not copy_counts.get("PAPER_COPY", 0):
            tasks.append({
                "priority": "MEDIUM",
                "task": "Continue paper-copy observation",
                "why": "No wallet has enough profitable sample yet",
            })

        if not tasks:
            tasks.append({
                "priority": "LOW",
                "task": "System is in observation mode",
                "why": "No urgent operator action detected",
            })

        return tasks[:6]

    def action_detail(self, counts):
        interesting = ["MONITOR_POSITION", "CONSIDER_PAPER_TRADE", "QUOTE_CHECK", "WATCH", "AVOID"]
        parts = [f"{name}:{counts.get(name, 0)}" for name in interesting if counts.get(name, 0)]
        return ", ".join(parts) or "No urgent token actions"

    def safe_float(self, value, default=0.0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default
