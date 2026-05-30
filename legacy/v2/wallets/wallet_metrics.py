from __future__ import annotations

from typing import Any


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def dict_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return None


def data_completeness(profile: dict[str, Any]) -> dict[str, int]:
    measured_keys = [
        "wallet_roi",
        "win_rate",
        "average_hold_duration",
        "average_entry_timing_quality",
        "average_pnl_multiple",
        "preferred_token_age",
        "average_conviction_sizing",
    ]
    known = len([key for key in measured_keys if profile.get(key) is not None])
    return {"known_fields": known, "tracked_fields": len(measured_keys)}


def build_wallet_behavior_profile(
    performance: dict[str, Any] | None,
    behavior: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build explicit wallet behavior metrics without inventing missing data."""
    performance = performance if isinstance(performance, dict) else {}
    behavior = behavior if isinstance(behavior, dict) else {}

    entries = safe_int(dict_value(performance, "paper_entries", "trades", "signals"), 0)
    wins = safe_int(dict_value(performance, "wins", "paper_wins"), 0)
    total_pnl = safe_float(dict_value(performance, "total_pnl", "pnl"), 0.0) or 0.0
    rolling = behavior.get("rolling") if isinstance(behavior.get("rolling"), dict) else {}
    rolling_30d = rolling.get("30d") if isinstance(rolling.get("30d"), dict) else {}
    postmortem = behavior.get("postmortem") if isinstance(behavior.get("postmortem"), dict) else {}
    entry_timing = behavior.get("entry_timing") if isinstance(behavior.get("entry_timing"), dict) else {}
    preferred_liquidity = behavior.get("preferred_liquidity") if isinstance(behavior.get("preferred_liquidity"), dict) else {}

    rug_hits = list_len(behavior.get("rug_mints")) + safe_int(behavior.get("rug_count"), 0)
    runner_hits = list_len(behavior.get("runner_mints")) + safe_int(behavior.get("runner_count"), 0)
    total_participations = runner_hits + rug_hits
    rug_score = round(rug_hits / total_participations, 4) if total_participations else 0.0

    avg_pnl_multiple = safe_float(dict_value(performance, "avg_pnl_multiple", "average_pnl_multiple"), None)
    if avg_pnl_multiple is None:
        avg_pnl_multiple = safe_float(dict_value(rolling_30d, "avg_pnl_multiple", "average_pnl_multiple"), None)

    preferred_token_age = dict_value(
        behavior,
        "preferred_token_age",
        "preferred_token_age_seconds",
    )
    if preferred_token_age is None:
        preferred_token_age = entry_timing.get("avg_seconds_after_launch")

    profile = {
        "wallet_roi": round(total_pnl / entries, 6) if entries else None,
        "win_rate": round(wins / entries * 100.0, 2) if entries else None,
        "average_hold_duration": safe_float(
            dict_value(postmortem, "avg_hold_seconds", "average_hold_seconds"),
            None,
        ),
        "rug_association_score": rug_score,
        "average_entry_timing_quality": safe_float(
            dict_value(entry_timing, "quality", "avg_quality", "average_quality"),
            None,
        ),
        "average_entry_seconds_after_launch": safe_float(
            dict_value(entry_timing, "avg_seconds_after_launch", "average_seconds_after_launch"),
            None,
        ),
        "average_pnl_multiple": avg_pnl_multiple,
        "participation_frequency_in_runners": runner_hits,
        "participation_frequency_in_rugs": rug_hits,
        "preferred_token_age": safe_float(preferred_token_age, None),
        "preferred_liquidity_range": {
            "min": safe_float(dict_value(preferred_liquidity, "min", "min_usd"), None),
            "max": safe_float(dict_value(preferred_liquidity, "max", "max_usd"), None),
        },
        "average_conviction_sizing": safe_float(
            dict_value(behavior, "avg_conviction_size_usd", "average_conviction_sizing", "avg_size_usd"),
            None,
        ),
    }
    profile["data_completeness"] = data_completeness(profile)
    return profile

