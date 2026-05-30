# execution_config.py

EXECUTION_CONFIG = {
    # Safety
    "paper_trading_enabled": True,
    "live_trading_enabled": False,

    # Trade sizing
    "base_position_usd": 10,
    "max_position_usd": 25,

    # Jupiter / execution
    "buy_slippage_bps": 1500,
    "sell_slippage_bps": 2000,
    "max_buy_price_impact_pct": 8,
    "max_sell_price_impact_pct": 10,

    # Signal gates
    "min_score_to_quote": 60,
    "min_score_to_trade": 75,

    # Token filters
    "max_token_age_seconds": 3600,
    "min_liquidity_usd": 1000,

    # Cooldowns
    "same_token_signal_cooldown_seconds": 45,
}