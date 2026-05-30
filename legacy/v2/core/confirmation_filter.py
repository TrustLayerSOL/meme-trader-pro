class ConfirmationFilter:
    def __init__(self, settings):
        self.settings = settings or {}

    def evaluate(
        self,
        signal_type,
        wallet_count,
        repeated_buys,
        liquidity_usd,
        true_launch_age_seconds,
        token_age_seconds=None,
    ):
        mode = str(self.settings.get("mode", "CONFIRMATION")).upper()
        if mode != "CONFIRMATION":
            return {
                "mode": mode,
                "allow": True,
                "reasons": [],
                "warnings": [],
            }

        reasons = []
        warnings = []

        min_age = self.safe_float(self.settings.get("confirmation_min_launch_age_seconds"), 30)
        max_age = self.safe_float(self.settings.get("confirmation_max_launch_age_seconds"), 180)
        min_liquidity = self.safe_float(self.settings.get("confirmation_min_liquidity_usd"), 10000)
        min_wallets = int(self.safe_float(self.settings.get("confirmation_min_wallets"), 3))
        min_repeated = int(self.safe_float(self.settings.get("confirmation_min_repeated_buys"), 1))
        require_momentum = bool(self.settings.get("confirmation_require_momentum", True))

        age = self.safe_float(true_launch_age_seconds, None)
        bot_age = self.safe_float(token_age_seconds, None)
        liquidity = self.safe_float(liquidity_usd)
        wallet_count = int(wallet_count or 0)
        repeated_buys = int(repeated_buys or 0)

        allow = True

        if age is not None:
            if age < min_age:
                allow = False
                reasons.append(f"Launch age {age:.0f}s is inside initial snipe window (<{min_age:.0f}s)")
            elif age > max_age:
                allow = False
                reasons.append(f"Launch age {age:.0f}s is past confirmation window (>{max_age:.0f}s)")
            else:
                warnings.append(f"Launch age {age:.0f}s is in confirmation window")
        elif bot_age is not None and bot_age < min_age:
            allow = False
            reasons.append(f"Bot-seen age {bot_age:.0f}s is inside initial snipe window")
        else:
            warnings.append("True launch age unavailable; using wallet/liquidity confirmation only")

        if liquidity < min_liquidity:
            allow = False
            reasons.append(f"Liquidity ${liquidity:,.0f} below confirmation minimum ${min_liquidity:,.0f}")

        if require_momentum:
            has_wallet_confirmation = wallet_count >= min_wallets
            has_repeat_confirmation = repeated_buys >= min_repeated
            if not has_wallet_confirmation and not has_repeat_confirmation:
                allow = False
                reasons.append(
                    f"Momentum not confirmed: wallets={wallet_count}/{min_wallets}, repeated_buys={repeated_buys}/{min_repeated}"
                )

        if signal_type == "early_signal" and require_momentum:
            allow = False
            reasons.append("Early signal blocked in confirmation mode")

        return {
            "mode": mode,
            "allow": allow,
            "reasons": reasons,
            "warnings": warnings,
            "min_age": min_age,
            "max_age": max_age,
            "min_liquidity": min_liquidity,
        }

    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default
