from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


class ProtectionExitPlanner:
    """
    Builds simulation-only exit intents for manually protected positions.

    This module never executes trades. It only records what the protection
    layer would prepare if live execution were eventually armed and allowed.
    """

    def plan(self, protected_item):
        alert_level = str(
            protected_item.get("alert_level")
            or protected_item.get("risk_level")
            or "unknown"
        ).lower()
        status = str(protected_item.get("status") or "UNKNOWN").upper()
        risk_level = str(protected_item.get("risk_level") or "UNKNOWN").upper()
        token_mint = protected_item.get("token_mint")

        price_from_peak = safe_float(protected_item.get("price_from_peak_pct"))
        liquidity_from_peak = safe_float(protected_item.get("liquidity_from_peak_pct"))
        current_liquidity = safe_float(protected_item.get("current_liquidity"))

        action = "HOLD"
        urgency = "normal"
        suggested_sell_pct = 0
        reasons = []

        if alert_level == "emergency" or status == "EMERGENCY" or risk_level == "EMERGENCY":
            action = "PREPARE_FULL_EXIT"
            urgency = "emergency"
            suggested_sell_pct = 100
            reasons.append("Emergency protection state")
        elif alert_level == "danger" or status == "DANGER" or risk_level == "DANGER":
            action = "PREPARE_PARTIAL_EXIT"
            urgency = "high"
            suggested_sell_pct = 50
            reasons.append("Danger protection state")
        elif alert_level == "warning" or status in ["WARNING", "NO_DATA"]:
            action = "WATCH_CLOSELY"
            urgency = "elevated"
            suggested_sell_pct = 0
            reasons.append("Warning protection state")

        if price_from_peak <= -55:
            action = "PREPARE_FULL_EXIT"
            urgency = "emergency"
            suggested_sell_pct = 100
            reasons.append(f"Price down {abs(price_from_peak):.1f}% from peak")
        elif price_from_peak <= -35 and suggested_sell_pct < 75:
            action = "PREPARE_PARTIAL_EXIT"
            urgency = "high"
            suggested_sell_pct = max(suggested_sell_pct, 75)
            reasons.append(f"Price down {abs(price_from_peak):.1f}% from peak")

        if liquidity_from_peak <= -45:
            action = "PREPARE_FULL_EXIT"
            urgency = "emergency"
            suggested_sell_pct = 100
            reasons.append(f"Liquidity down {abs(liquidity_from_peak):.1f}% from peak")
        elif liquidity_from_peak <= -30 and suggested_sell_pct < 75:
            action = "PREPARE_PARTIAL_EXIT"
            urgency = "high"
            suggested_sell_pct = max(suggested_sell_pct, 75)
            reasons.append(f"Liquidity down {abs(liquidity_from_peak):.1f}% from peak")

        if current_liquidity > 0 and current_liquidity < 3000 and suggested_sell_pct < 50:
            action = "PREPARE_PARTIAL_EXIT"
            urgency = "high"
            suggested_sell_pct = 50
            reasons.append(f"Liquidity critically thin: ${current_liquidity:,.0f}")

        if protected_item.get("token_inspection", {}).get("hard_block"):
            action = "PREPARE_FULL_EXIT"
            urgency = "emergency"
            suggested_sell_pct = 100
            reasons.append("Token mechanics hard block")

        if not reasons:
            reasons.append("No simulated exit trigger active")

        quote_required = suggested_sell_pct > 0
        timestamp = utc_now()

        return {
            "intent_type": "manual_protection_exit",
            "token_mint": token_mint,
            "action": action,
            "urgency": urgency,
            "suggested_sell_pct": suggested_sell_pct,
            "execution_mode": "SIMULATION_ONLY",
            "live_action_allowed": False,
            "quote_required": quote_required,
            "quote_status": "not_checked" if quote_required else "not_required",
            "reasons": reasons,
            "source_status": status,
            "source_risk_level": risk_level,
            "source_alert_level": alert_level,
            "created_at": protected_item.get("prepared_exit", {}).get("created_at") or timestamp,
            "updated_at": timestamp,
            "safety_note": "Prepared intent only. No live sell is executed.",
        }


if __name__ == "__main__":
    import json

    sample = {
        "token_mint": "ExampleMint111111111111111111111111111111111",
        "status": "EMERGENCY",
        "risk_level": "EMERGENCY",
        "alert_level": "emergency",
        "price_from_peak_pct": -61.2,
        "liquidity_from_peak_pct": -38.8,
        "current_liquidity": 1902,
    }
    print(json.dumps(ProtectionExitPlanner().plan(sample), indent=2))
