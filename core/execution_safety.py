import os

from execution.execution_config import EXECUTION_CONFIG


LIVE_ACK_VALUE = "I_UNDERSTAND_REAL_FUNDS"


class ExecutionSafetyGate:
    """Hard gate for future live execution paths."""

    def report(self, config=None):
        config = dict(EXECUTION_CONFIG if config is None else config)
        live_enabled = bool(config.get("live_trading_enabled"))
        paper_enabled = bool(config.get("paper_trading_enabled", True))
        ack = os.getenv("MEMETRADER_ALLOW_LIVE") == LIVE_ACK_VALUE
        has_key_material = bool(os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("SOLANA_KEYPAIR_FILE"))
        max_position = self.safe_float(config.get("max_position_usd"))
        max_buy_impact = self.safe_float(config.get("max_buy_price_impact_pct"))
        max_sell_impact = self.safe_float(config.get("max_sell_price_impact_pct"))

        checks = [
            {
                "check": "paper_trading_enabled",
                "status": "OK" if paper_enabled else "WARN",
                "detail": "paper mode available" if paper_enabled else "paper mode disabled",
            },
            {
                "check": "live_trading_enabled",
                "status": "WARN" if live_enabled else "OK",
                "detail": "requested in config" if live_enabled else "off",
            },
            {
                "check": "explicit_live_ack",
                "status": "OK" if ack else "BLOCK",
                "detail": f"requires MEMETRADER_ALLOW_LIVE={LIVE_ACK_VALUE}",
            },
            {
                "check": "key_material",
                "status": "OK" if has_key_material else "BLOCK",
                "detail": "present" if has_key_material else "no private key or keypair env configured",
            },
            {
                "check": "max_position_usd",
                "status": "OK" if 0 < max_position <= 100 else "BLOCK",
                "detail": f"${max_position:.2f}",
            },
            {
                "check": "buy_price_impact_cap",
                "status": "OK" if 0 < max_buy_impact <= 10 else "BLOCK",
                "detail": f"{max_buy_impact:.2f}%",
            },
            {
                "check": "sell_price_impact_cap",
                "status": "OK" if 0 < max_sell_impact <= 15 else "BLOCK",
                "detail": f"{max_sell_impact:.2f}%",
            },
        ]

        blockers = [row for row in checks if row["status"] == "BLOCK"]
        warnings = [row for row in checks if row["status"] == "WARN"]
        live_allowed = live_enabled and not blockers

        if live_allowed:
            overall = "LIVE_READY"
        elif live_enabled and blockers:
            overall = "LIVE_BLOCKED"
        elif warnings:
            overall = "PAPER_WARN"
        else:
            overall = "PAPER_SAFE"

        return {
            "overall": overall,
            "live_allowed": live_allowed,
            "live_enabled": live_enabled,
            "paper_enabled": paper_enabled,
            "checks": checks,
            "blockers": len(blockers),
            "warnings": len(warnings),
        }

    def assert_live_allowed(self, config=None):
        report = self.report(config)
        if not report["live_allowed"]:
            details = "; ".join(
                f"{row['check']}: {row['detail']}"
                for row in report["checks"]
                if row["status"] == "BLOCK"
            )
            raise RuntimeError(f"Live execution blocked by safety gate. {details}")
        return True

    def safe_float(self, value, default=0.0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default
