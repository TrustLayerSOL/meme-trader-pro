SETTINGS = {
    "mode": "SNIPER",

    # Paper-learning mode.
    # 55 lets the bot collect trade data.
    # Later, move this back to 70-75 after we have enough results.
    "sniper_score_threshold": 55,
    "safe_score_threshold": 85,

    # Paper account / sizing
    "starting_balance": 10000,
    "risk_per_trade": 100,

    # Scoring / quote gates
    "jupiter_prescore_threshold": 40,
    "weighted_wallet_trigger": 1.8,
    "weighted_wallet_strong_bonus": 3.0,

    # SNIPER exits
    "sniper_stop_loss_pct": -30,
    "sniper_trailing_stop_pct": 35,
    "sniper_confirmed_high_window": 20,
    "sniper_confirmed_high_tolerance_pct": 12,
    "sniper_take_profits": [
        {"multiple": 2.5, "sell_pct": 35},
        {"multiple": 6.0, "sell_pct": 35}
    ],

    # SAFE exits
    "safe_stop_loss_pct": -18,
    "safe_trailing_stop_pct": 22,
    "safe_confirmed_high_window": 15,
    "safe_confirmed_high_tolerance_pct": 8,
    "safe_take_profits": [
        {"multiple": 1.7, "sell_pct": 40},
        {"multiple": 3.0, "sell_pct": 35}
    ]
}