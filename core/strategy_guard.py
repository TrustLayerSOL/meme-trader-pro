from core.performance_analyzer import PerformanceAnalyzer


class StrategyGuard:
    def __init__(self, min_trades_for_block=5):
        self.min_trades_for_block = min_trades_for_block
        self.analyzer = PerformanceAnalyzer()

    def build_family_stats(self, paper_state):
        performance = self.analyzer.analyze(paper_state)
        return {
            row["signal"]: row
            for row in performance.get("signal_rows", [])
        }

    def evaluate_family(self, signal_type, paper_state):
        family_stats = self.build_family_stats(paper_state)
        row = family_stats.get(signal_type)

        if not row:
            return {
                "action": "ALLOW",
                "reason": "No family history yet",
                "stats": None,
            }

        trades = int(row.get("trades", 0) or 0)
        avg_pnl = float(row.get("avg_pnl", 0) or 0)
        total_pnl = float(row.get("total_pnl", 0) or 0)
        win_rate = float(row.get("win_rate", 0) or 0)

        if trades >= self.min_trades_for_block and avg_pnl <= -8 and win_rate < 35:
            return {
                "action": "BLOCK",
                "reason": f"{signal_type} has negative paper expectancy",
                "stats": row,
            }

        if trades >= 3 and total_pnl < 0:
            return {
                "action": "REDUCE_SIZE",
                "reason": f"{signal_type} is currently underperforming",
                "stats": row,
            }

        return {
            "action": "ALLOW",
            "reason": f"{signal_type} performance is acceptable",
            "stats": row,
        }
