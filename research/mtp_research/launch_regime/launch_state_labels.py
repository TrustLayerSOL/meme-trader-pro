"""First-two-hour launch-state label stubs.

These models reserve the output schema for the launch census research lane.
They do not infer labels, run backtests, or promote theses.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FirstTwoHourLifecycleLabel:
    token_mint: str
    launch_signature: str
    launch_ts: int
    created_no_trade: bool | None = None
    traded_on_curve_no_graduation: bool | None = None
    graduated: bool | None = None
    survived_30m: bool | None = None
    survived_2h: bool | None = None
    liquidity_disappeared: bool | None = None
    holder_count_collapsed: bool | None = None
    max_2h_runup: float | None = None
    max_2h_drawdown: float | None = None
    return_2h: float | None = None
    price_quality_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
