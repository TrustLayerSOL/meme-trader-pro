"""Models for deterministic rule-based backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class RuleCondition:
    field_name: str
    operator: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleCondition":
        return cls(
            field_name=payload["field_name"],
            operator=payload["operator"],
            value=payload.get("value"),
        )


@dataclass
class RuleDefinition:
    rule_id: str
    name: str
    description: str = ""
    conditions: list[RuleCondition] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "metadata_json": dict(self.metadata_json),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleDefinition":
        return cls(
            rule_id=payload["rule_id"],
            name=payload["name"],
            description=payload.get("description", ""),
            conditions=[
                RuleCondition.from_dict(condition)
                for condition in payload.get("conditions", [])
            ],
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class CostAssumptions:
    entry_fee_bps: float = 125.0
    exit_fee_bps: float = 125.0
    slippage_bps: float = 200.0
    priority_fee_bps: float = 0.0
    failure_penalty_bps: float = 0.0

    def total_cost_bps(self) -> float:
        return (
            self.entry_fee_bps
            + self.exit_fee_bps
            + self.slippage_bps
            + self.priority_fee_bps
            + self.failure_penalty_bps
        )

    def total_cost_return_drag(self) -> float:
        return self.total_cost_bps() / 10_000

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CostAssumptions":
        return cls(
            entry_fee_bps=payload.get("entry_fee_bps", 125.0),
            exit_fee_bps=payload.get("exit_fee_bps", 125.0),
            slippage_bps=payload.get("slippage_bps", 200.0),
            priority_fee_bps=payload.get("priority_fee_bps", 0.0),
            failure_penalty_bps=payload.get("failure_penalty_bps", 0.0),
        )


@dataclass
class RuleBacktestConfig:
    config_id: str
    horizon_name: str | None = None
    window_name: str | None = None
    min_label_quality: str = "sparse"
    require_entry_price: bool = True
    require_forward_return: bool = True
    min_rows: int = 10
    cost_assumptions: CostAssumptions = field(default_factory=CostAssumptions)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "horizon_name": self.horizon_name,
            "window_name": self.window_name,
            "min_label_quality": self.min_label_quality,
            "require_entry_price": self.require_entry_price,
            "require_forward_return": self.require_forward_return,
            "min_rows": self.min_rows,
            "cost_assumptions": self.cost_assumptions.to_dict(),
            "metadata_json": dict(self.metadata_json),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleBacktestConfig":
        return cls(
            config_id=payload["config_id"],
            horizon_name=payload.get("horizon_name"),
            window_name=payload.get("window_name"),
            min_label_quality=payload.get("min_label_quality", "sparse"),
            require_entry_price=payload.get("require_entry_price", True),
            require_forward_return=payload.get("require_forward_return", True),
            min_rows=payload.get("min_rows", 10),
            cost_assumptions=CostAssumptions.from_dict(payload.get("cost_assumptions", {})),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class SelectedTrade:
    row_id: str
    token_mint: str
    snapshot_ts: int
    window_name: str
    horizon_name: str
    entry_price: float | None
    end_price: float | None
    gross_forward_return: float | None
    net_forward_return: float | None
    max_runup: float | None
    max_drawdown: float | None
    rug_like_drop: bool | None
    no_future_liquidity: bool
    label_quality: str
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SelectedTrade":
        return cls(
            row_id=payload["row_id"],
            token_mint=payload["token_mint"],
            snapshot_ts=payload["snapshot_ts"],
            window_name=payload["window_name"],
            horizon_name=payload["horizon_name"],
            entry_price=payload.get("entry_price"),
            end_price=payload.get("end_price"),
            gross_forward_return=payload.get("gross_forward_return"),
            net_forward_return=payload.get("net_forward_return"),
            max_runup=payload.get("max_runup"),
            max_drawdown=payload.get("max_drawdown"),
            rug_like_drop=payload.get("rug_like_drop"),
            no_future_liquidity=payload.get("no_future_liquidity", False),
            label_quality=payload.get("label_quality", "unknown"),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class RuleBacktestSummary:
    selected_count: int = 0
    token_count: int = 0
    rows_with_return: int = 0
    avg_gross_return: float | None = None
    median_gross_return: float | None = None
    avg_net_return: float | None = None
    median_net_return: float | None = None
    win_count: int = 0
    loss_count: int = 0
    win_rate: float | None = None
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float | None = None
    cumulative_net_return: float | None = None
    max_equity_drawdown: float | None = None
    avg_max_runup: float | None = None
    avg_max_drawdown: float | None = None
    rug_like_drop_count: int = 0
    rug_like_drop_rate: float | None = None
    no_future_liquidity_count: int = 0
    no_future_liquidity_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleBacktestSummary":
        return cls(**payload)


@dataclass
class RuleBacktestResult:
    result_id: str
    created_at: str
    rule: RuleDefinition
    config: RuleBacktestConfig
    summary: RuleBacktestSummary
    selected_trades: list[SelectedTrade] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "created_at": self.created_at,
            "rule": self.rule.to_dict(),
            "config": self.config.to_dict(),
            "summary": self.summary.to_dict(),
            "selected_trades": [trade.to_dict() for trade in self.selected_trades],
            "warning_flags": list(self.warning_flags),
            "metadata_json": dict(self.metadata_json),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleBacktestResult":
        return cls(
            result_id=payload["result_id"],
            created_at=payload["created_at"],
            rule=RuleDefinition.from_dict(payload["rule"]),
            config=RuleBacktestConfig.from_dict(payload["config"]),
            summary=RuleBacktestSummary.from_dict(payload.get("summary", {})),
            selected_trades=[
                SelectedTrade.from_dict(trade)
                for trade in payload.get("selected_trades", [])
            ],
            warning_flags=list(payload.get("warning_flags", [])),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


def make_rule_id(name: str) -> str:
    normalized = "_".join(name.strip().lower().replace("-", "_").split())
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{normalized}-{digest}"


def make_backtest_result_id(rule_id: str, config_id: str) -> str:
    digest = sha256(f"{rule_id}|{config_id}".encode("utf-8")).hexdigest()[:16]
    return f"rule-backtest-{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
