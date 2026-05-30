import json
from pathlib import Path

from core.json_store import atomic_write_json


SETTINGS_FILE = Path("data/bot_settings.json")


DEFAULT_SETTINGS = {
    "mode": "CONFIRMATION",
    "sniper_score_threshold": 55,
    "confirmation_score_threshold": 68,
    "safe_score_threshold": 85,
    "jupiter_prescore_threshold": 40,
    "weighted_wallet_trigger": 1.8,
    "weighted_wallet_strong_bonus": 3.0,
    "cluster_threshold": 3,
    "cluster_window": 90,
    "confirmation_min_launch_age_seconds": 30,
    "confirmation_max_launch_age_seconds": 180,
    "confirmation_min_liquidity_usd": 10000,
    "confirmation_require_momentum": True,
    "confirmation_min_wallets": 3,
    "confirmation_min_repeated_buys": 1,
    "paper_base_position_usd": 30,
    "paper_strong_position_usd": 60,
    "paper_medium_position_usd": 45,
    "paper_exploration_enabled": True,
    "paper_exploration_score_threshold": 52,
    "paper_exploration_min_edge_score": 55,
    "paper_exploration_size_usd": 10,
    "paper_exploration_route_failed_enabled": True,
    "paper_exploration_route_failed_score_threshold": 70,
    "paper_exploration_route_failed_min_edge_score": 65,
    "paper_exploration_route_failed_size_usd": 5,
    "paper_exploration_confirmation_blocked_enabled": True,
    "paper_exploration_confirmation_score_threshold": 70,
    "paper_exploration_confirmation_min_edge_score": 60,
    "paper_exploration_confirmation_size_usd": 5,
    "paper_exploration_bad_sample_suppression_enabled": True,
    "paper_exploration_confirmation_medium_risk_min_score": 68,
    "paper_exploration_confirmation_medium_risk_min_edge_score": 60,
    "paper_exploration_confirmation_min_liquidity_usd": 25000,
    "paper_exploration_confirmation_min_market_cap_usd": 50000,
    "paper_exploration_auto_pause_enabled": True,
    "paper_exploration_auto_pause_min_closed": 5,
    "paper_exploration_auto_pause_max_avg_pnl_pct": -10,
    "paper_exploration_auto_pause_max_win_rate_pct": 20,
    "market_radar_enabled": True,
    "market_radar_interval_seconds": 120,
    "market_radar_max_candidates_per_cycle": 8,
    "market_radar_scan_candidates_per_cycle": 120,
    "market_radar_max_entries_per_cycle": 1,
    "market_radar_max_quotes_per_cycle": 1,
    "market_radar_quote_cooldown_seconds": 300,
    "market_radar_mint_cooldown_seconds": 21600,
    "market_radar_position_size_usd": 5,
    "market_radar_min_score": 70,
    "market_radar_min_liquidity_usd": 25000,
    "market_radar_min_market_cap_usd": 75000,
    "market_radar_max_market_cap_usd": 10000000,
    "market_radar_min_m5_tx_count": 40,
    "market_radar_min_h1_volume_usd": 100000,
    "market_radar_min_buy_ratio": 0.48,
    "market_radar_quality_gate_enabled": True,
    "market_radar_entry_min_liquidity_usd": 100000,
    "market_radar_entry_min_market_cap_usd": 250000,
    "market_radar_min_liquidity_to_market_cap": 0.03,
    "market_radar_max_volume_liquidity_ratio": 8.0,
    "market_radar_holder_check_enabled": False,
    "market_radar_holder_check_timeout_seconds": 3,
    "market_radar_max_holder_checks_per_cycle": 2,
    "market_radar_min_m5_price_change_pct": -12.0,
    "market_radar_min_h1_price_change_pct": -25.0,
    "market_radar_max_buy_ratio": 0.88,
    "market_radar_max_sell_ratio": 0.70,
    "market_radar_min_avg_tx_usd": 50.0,
    "market_radar_require_social_or_site": True,
    "market_radar_min_pair_age_seconds": 1800,
    "market_radar_max_pair_age_seconds": 86400,
    "wallet_main_quality_gate_enabled": True,
    "wallet_main_min_liquidity_usd": 100000,
    "wallet_main_min_market_cap_usd": 250000,
    "wallet_main_solo_min_score": 90,
    "wallet_main_solo_min_wallet_quality": 90,
    "wallet_main_two_wallet_min_avg_quality": 80,
    "wallet_main_two_wallet_min_max_quality": 85,
    "wallet_main_max_rapid_flips": 0,
    "paper_activity_evaluation_enabled": True,
    "paper_activity_evaluation_weighted_trigger": 0.8,
    "paper_activity_evaluation_min_combined_wallet_score": 45,
    "swap_quote_budget_enabled": True,
    "swap_quote_score_threshold": 68,
    "swap_quote_min_edge_score": 65,
    "swap_quote_max_requests_per_minute": 18,
    "swap_quote_budget_window_seconds": 60,
    "strategy_guard_enabled": True,
    "scanner_holder_check_enabled": True,
    "scanner_holder_check_timeout_seconds": 3,
    "analysis_rejection_log_enabled": True,
}


def load_legacy_python_settings():
    try:
        from bot_settings import SETTINGS
        return SETTINGS if isinstance(SETTINGS, dict) else {}
    except Exception:
        return {}


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def flatten_json_settings(data):
    data = data or {}
    mode = str(data.get("mode", DEFAULT_SETTINGS["mode"])).upper()
    mode_block = data.get(mode.lower(), {}) if isinstance(data.get(mode.lower()), dict) else {}

    flattened = {}
    flattened.update(data)

    if "cluster_wallets" in mode_block:
        flattened["cluster_threshold"] = mode_block.get("cluster_wallets")
    if "cluster_window_seconds" in mode_block:
        flattened["cluster_window"] = mode_block.get("cluster_window_seconds")

    return flattened


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    settings.update(load_legacy_python_settings())

    try:
        with open(SETTINGS_FILE, "r") as f:
            json_settings = json.load(f)
        settings.update(flatten_json_settings(json_settings))
    except Exception:
        pass

    settings["mode"] = str(settings.get("mode", "SNIPER")).upper()
    return settings


def save_settings(updates):
    current = load_settings()
    current.update(updates)
    current["mode"] = str(current.get("mode", "SNIPER")).upper()

    payload = {
        "mode": current["mode"],
        "sniper_score_threshold": float(current["sniper_score_threshold"]),
        "confirmation_score_threshold": float(current["confirmation_score_threshold"]),
        "safe_score_threshold": float(current["safe_score_threshold"]),
        "jupiter_prescore_threshold": float(current["jupiter_prescore_threshold"]),
        "weighted_wallet_trigger": float(current["weighted_wallet_trigger"]),
        "weighted_wallet_strong_bonus": float(current["weighted_wallet_strong_bonus"]),
        "cluster_threshold": int(current["cluster_threshold"]),
        "cluster_window": int(current["cluster_window"]),
        "confirmation_min_launch_age_seconds": int(current["confirmation_min_launch_age_seconds"]),
        "confirmation_max_launch_age_seconds": int(current["confirmation_max_launch_age_seconds"]),
        "confirmation_min_liquidity_usd": float(current["confirmation_min_liquidity_usd"]),
        "confirmation_require_momentum": parse_bool(current.get("confirmation_require_momentum"), True),
        "confirmation_min_wallets": int(current["confirmation_min_wallets"]),
        "confirmation_min_repeated_buys": int(current["confirmation_min_repeated_buys"]),
        "paper_base_position_usd": float(current["paper_base_position_usd"]),
        "paper_medium_position_usd": float(current["paper_medium_position_usd"]),
        "paper_strong_position_usd": float(current["paper_strong_position_usd"]),
        "paper_exploration_enabled": parse_bool(current.get("paper_exploration_enabled"), True),
        "paper_exploration_score_threshold": float(current.get("paper_exploration_score_threshold", 52)),
        "paper_exploration_min_edge_score": float(current.get("paper_exploration_min_edge_score", 55)),
        "paper_exploration_size_usd": float(current.get("paper_exploration_size_usd", 10)),
        "paper_exploration_route_failed_enabled": parse_bool(current.get("paper_exploration_route_failed_enabled"), True),
        "paper_exploration_route_failed_score_threshold": float(current.get("paper_exploration_route_failed_score_threshold", 70)),
        "paper_exploration_route_failed_min_edge_score": float(current.get("paper_exploration_route_failed_min_edge_score", 65)),
        "paper_exploration_route_failed_size_usd": float(current.get("paper_exploration_route_failed_size_usd", 5)),
        "paper_exploration_confirmation_blocked_enabled": parse_bool(current.get("paper_exploration_confirmation_blocked_enabled"), True),
        "paper_exploration_confirmation_score_threshold": float(current.get("paper_exploration_confirmation_score_threshold", 70)),
        "paper_exploration_confirmation_min_edge_score": float(current.get("paper_exploration_confirmation_min_edge_score", 60)),
        "paper_exploration_confirmation_size_usd": float(current.get("paper_exploration_confirmation_size_usd", 5)),
        "paper_exploration_bad_sample_suppression_enabled": parse_bool(current.get("paper_exploration_bad_sample_suppression_enabled"), True),
        "paper_exploration_confirmation_medium_risk_min_score": float(current.get("paper_exploration_confirmation_medium_risk_min_score", 68)),
        "paper_exploration_confirmation_medium_risk_min_edge_score": float(current.get("paper_exploration_confirmation_medium_risk_min_edge_score", 60)),
        "paper_exploration_confirmation_min_liquidity_usd": float(current.get("paper_exploration_confirmation_min_liquidity_usd", 25000)),
        "paper_exploration_confirmation_min_market_cap_usd": float(current.get("paper_exploration_confirmation_min_market_cap_usd", 50000)),
        "paper_exploration_auto_pause_enabled": parse_bool(current.get("paper_exploration_auto_pause_enabled"), True),
        "paper_exploration_auto_pause_min_closed": int(current.get("paper_exploration_auto_pause_min_closed", 5)),
        "paper_exploration_auto_pause_max_avg_pnl_pct": float(current.get("paper_exploration_auto_pause_max_avg_pnl_pct", -10)),
        "paper_exploration_auto_pause_max_win_rate_pct": float(current.get("paper_exploration_auto_pause_max_win_rate_pct", 20)),
        "market_radar_enabled": parse_bool(current.get("market_radar_enabled"), True),
        "market_radar_interval_seconds": float(current.get("market_radar_interval_seconds", 120)),
        "market_radar_max_candidates_per_cycle": int(current.get("market_radar_max_candidates_per_cycle", 8)),
        "market_radar_scan_candidates_per_cycle": int(current.get("market_radar_scan_candidates_per_cycle", 120)),
        "market_radar_max_entries_per_cycle": int(current.get("market_radar_max_entries_per_cycle", 1)),
        "market_radar_max_quotes_per_cycle": int(current.get("market_radar_max_quotes_per_cycle", 1)),
        "market_radar_quote_cooldown_seconds": float(current.get("market_radar_quote_cooldown_seconds", 300)),
        "market_radar_mint_cooldown_seconds": float(current.get("market_radar_mint_cooldown_seconds", 21600)),
        "market_radar_position_size_usd": float(current.get("market_radar_position_size_usd", 5)),
        "market_radar_min_score": float(current.get("market_radar_min_score", 70)),
        "market_radar_min_liquidity_usd": float(current.get("market_radar_min_liquidity_usd", 25000)),
        "market_radar_min_market_cap_usd": float(current.get("market_radar_min_market_cap_usd", 75000)),
        "market_radar_max_market_cap_usd": float(current.get("market_radar_max_market_cap_usd", 10000000)),
        "market_radar_min_m5_tx_count": int(current.get("market_radar_min_m5_tx_count", 40)),
        "market_radar_min_h1_volume_usd": float(current.get("market_radar_min_h1_volume_usd", 100000)),
        "market_radar_min_buy_ratio": float(current.get("market_radar_min_buy_ratio", 0.48)),
        "market_radar_quality_gate_enabled": parse_bool(current.get("market_radar_quality_gate_enabled"), True),
        "market_radar_entry_min_liquidity_usd": float(current.get("market_radar_entry_min_liquidity_usd", 100000)),
        "market_radar_entry_min_market_cap_usd": float(current.get("market_radar_entry_min_market_cap_usd", 250000)),
        "market_radar_min_liquidity_to_market_cap": float(current.get("market_radar_min_liquidity_to_market_cap", 0.03)),
        "market_radar_max_volume_liquidity_ratio": float(current.get("market_radar_max_volume_liquidity_ratio", 8.0)),
        "market_radar_min_m5_price_change_pct": float(current.get("market_radar_min_m5_price_change_pct", -12.0)),
        "market_radar_min_h1_price_change_pct": float(current.get("market_radar_min_h1_price_change_pct", -25.0)),
        "market_radar_max_buy_ratio": float(current.get("market_radar_max_buy_ratio", 0.88)),
        "market_radar_max_sell_ratio": float(current.get("market_radar_max_sell_ratio", 0.70)),
        "market_radar_min_avg_tx_usd": float(current.get("market_radar_min_avg_tx_usd", 50.0)),
        "market_radar_require_social_or_site": parse_bool(current.get("market_radar_require_social_or_site"), True),
        "market_radar_min_pair_age_seconds": float(current.get("market_radar_min_pair_age_seconds", 1800)),
        "market_radar_max_pair_age_seconds": float(current.get("market_radar_max_pair_age_seconds", 86400)),
        "wallet_main_quality_gate_enabled": parse_bool(current.get("wallet_main_quality_gate_enabled"), True),
        "wallet_main_min_liquidity_usd": float(current.get("wallet_main_min_liquidity_usd", 100000)),
        "wallet_main_min_market_cap_usd": float(current.get("wallet_main_min_market_cap_usd", 250000)),
        "wallet_main_solo_min_score": float(current.get("wallet_main_solo_min_score", 90)),
        "wallet_main_solo_min_wallet_quality": float(current.get("wallet_main_solo_min_wallet_quality", 90)),
        "wallet_main_two_wallet_min_avg_quality": float(current.get("wallet_main_two_wallet_min_avg_quality", 80)),
        "wallet_main_two_wallet_min_max_quality": float(current.get("wallet_main_two_wallet_min_max_quality", 85)),
        "wallet_main_max_rapid_flips": int(current.get("wallet_main_max_rapid_flips", 0)),
        "paper_activity_evaluation_enabled": parse_bool(current.get("paper_activity_evaluation_enabled"), True),
        "paper_activity_evaluation_weighted_trigger": float(current.get("paper_activity_evaluation_weighted_trigger", 0.8)),
        "paper_activity_evaluation_min_combined_wallet_score": float(current.get("paper_activity_evaluation_min_combined_wallet_score", 45)),
        "swap_quote_budget_enabled": parse_bool(current.get("swap_quote_budget_enabled"), True),
        "swap_quote_score_threshold": float(current.get("swap_quote_score_threshold", 68)),
        "swap_quote_min_edge_score": float(current.get("swap_quote_min_edge_score", 65)),
        "swap_quote_max_requests_per_minute": int(current.get("swap_quote_max_requests_per_minute", 18)),
        "swap_quote_budget_window_seconds": float(current.get("swap_quote_budget_window_seconds", 60)),
        "strategy_guard_enabled": parse_bool(current.get("strategy_guard_enabled"), True),
        "scanner_holder_check_enabled": parse_bool(current.get("scanner_holder_check_enabled"), True),
        "scanner_holder_check_timeout_seconds": float(current.get("scanner_holder_check_timeout_seconds", 3)),
        "market_radar_holder_check_enabled": parse_bool(current.get("market_radar_holder_check_enabled"), False),
        "market_radar_holder_check_timeout_seconds": float(current.get("market_radar_holder_check_timeout_seconds", 3)),
        "market_radar_max_holder_checks_per_cycle": int(current.get("market_radar_max_holder_checks_per_cycle", 2)),
        "sniper": {
            "cluster_wallets": int(current["cluster_threshold"]),
            "cluster_window_seconds": int(current["cluster_window"]),
            "min_liquidity": 5000,
            "take_profit_pct": 0.5,
            "stop_loss_pct": 0.25,
            "risk_per_trade": 0.05,
        },
        "safe": {
            "cluster_wallets": 4,
            "cluster_window_seconds": 180,
            "min_liquidity": 20000,
            "take_profit_pct": 0.35,
            "stop_loss_pct": 0.15,
            "risk_per_trade": 0.03,
        },
        "confirmation": {
            "cluster_wallets": int(current["confirmation_min_wallets"]),
            "cluster_window_seconds": int(current["cluster_window"]),
            "min_launch_age_seconds": int(current["confirmation_min_launch_age_seconds"]),
            "max_launch_age_seconds": int(current["confirmation_max_launch_age_seconds"]),
            "min_liquidity": float(current["confirmation_min_liquidity_usd"]),
            "min_repeated_buys": int(current["confirmation_min_repeated_buys"]),
            "take_profit_pct": 0.35,
            "stop_loss_pct": 0.18,
            "risk_per_trade": 0.03,
        },
    }

    atomic_write_json(SETTINGS_FILE, payload)

    return payload
