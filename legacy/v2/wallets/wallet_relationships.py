from __future__ import annotations

from typing import Any


def summarize_wallet_relationships(behavior: dict[str, Any] | None) -> dict[str, Any]:
    behavior = behavior if isinstance(behavior, dict) else {}
    clusters = behavior.get("clusters") if isinstance(behavior.get("clusters"), list) else []
    coordinated = behavior.get("coordinated_entries") if isinstance(behavior.get("coordinated_entries"), list) else []
    related = behavior.get("related_wallets") if isinstance(behavior.get("related_wallets"), list) else []

    return {
        "cluster_count": len(clusters),
        "coordinated_entry_count": len(coordinated),
        "related_wallets": [str(wallet) for wallet in related[:25]],
        "repeated_coordinated_entries": [
            row for row in coordinated[:25] if isinstance(row, dict)
        ],
    }

