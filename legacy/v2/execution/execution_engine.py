import random


class ExecutionEngine:
    def __init__(self):
        self.config = {
            "buy_slippage_pct": 20,
            "sell_slippage_pct": 25,
            "priority_fee_sol": 0.0005,
            "jito_tip_sol": 0.0002,
            "base_fee_sol": 0.000005,
            "sol_price_usd": 150,
            "max_price_impact_pct": 8,
            "failed_fill_penalty_usd": 0.05,
            "simulate_failed_fills": True,
            "failed_fill_chance_pct": 8,
        }

    # ------------------------
    # FEE CALCULATION
    # ------------------------
    def sol_fee_usd(self):
        sol_price = float(self.config["sol_price_usd"])

        total_sol = (
            self.config["priority_fee_sol"]
            + self.config["jito_tip_sol"]
            + self.config["base_fee_sol"]
        )

        return total_sol * sol_price

    # ------------------------
    # FAIL SIMULATION
    # ------------------------
    def should_fail(self):
        if not self.config["simulate_failed_fills"]:
            return False

        chance = float(self.config["failed_fill_chance_pct"])
        return random.uniform(0, 100) < chance

    # ------------------------
    # BUY SIMULATION
    # ------------------------
    def simulate_buy_fill(self, quoted_price, size_usd, liquidity_usd=10000):
        quoted_price = float(quoted_price)
        size_usd = float(size_usd)

        if quoted_price <= 0 or size_usd <= 0:
            return {"success": False, "reason": "invalid_buy"}

        if self.should_fail():
            return {
                "success": False,
                "reason": "failed_buy_simulation",
                "fee_usd": self.config["failed_fill_penalty_usd"],
            }

        slippage = self.config["buy_slippage_pct"]

        price_impact = min(
            self.config["max_price_impact_pct"],
            (size_usd / liquidity_usd) * 100 if liquidity_usd > 0 else 0,
        )

        effective_price = quoted_price * (1 + (slippage + price_impact) / 100)

        fee_usd = self.sol_fee_usd()

        tokens = (size_usd - fee_usd) / effective_price

        return {
            "success": True,
            "effective_price": effective_price,
            "tokens": tokens,
            "fee_usd": fee_usd,
            "slippage_pct": slippage,
            "price_impact_pct": price_impact,
        }

    # ------------------------
    # SELL SIMULATION
    # ------------------------
    def simulate_sell_fill(self, quoted_price, tokens_to_sell, liquidity_usd=10000):
        quoted_price = float(quoted_price)
        tokens_to_sell = float(tokens_to_sell)

        if quoted_price <= 0 or tokens_to_sell <= 0:
            return {"success": False, "reason": "invalid_sell"}

        if self.should_fail():
            return {
                "success": False,
                "reason": "failed_sell_simulation",
                "fee_usd": self.config["failed_fill_penalty_usd"],
            }

        slippage = self.config["sell_slippage_pct"]

        notional = quoted_price * tokens_to_sell

        price_impact = min(
            self.config["max_price_impact_pct"],
            (notional / liquidity_usd) * 100 if liquidity_usd > 0 else 0,
        )

        effective_price = quoted_price * (1 - (slippage + price_impact) / 100)
        effective_price = max(effective_price, 0)

        gross = tokens_to_sell * effective_price
        fee_usd = self.sol_fee_usd()
        net = gross - fee_usd

        return {
            "success": True,
            "effective_price": effective_price,
            "gross_proceeds": gross,
            "net_proceeds": net,
            "fee_usd": fee_usd,
            "slippage_pct": slippage,
            "price_impact_pct": price_impact,
        }