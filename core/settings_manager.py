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
    "strategy_guard_enabled": True,
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
        "strategy_guard_enabled": parse_bool(current.get("strategy_guard_enabled"), True),
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
