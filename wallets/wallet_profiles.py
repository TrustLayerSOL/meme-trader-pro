from __future__ import annotations

from typing import Any

from wallets.wallet_metrics import build_wallet_behavior_profile
from wallets.wallet_relationships import summarize_wallet_relationships


def build_wallet_profile(
    wallet: str,
    performance: dict[str, Any] | None = None,
    behavior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "wallet": wallet,
        "metrics": build_wallet_behavior_profile(performance, behavior),
        "relationships": summarize_wallet_relationships(behavior),
    }

