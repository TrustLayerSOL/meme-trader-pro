"""Default exploratory rule definitions for v3 research backtests."""

from __future__ import annotations

from research.mtp_research.backtest.rule_backtest_models import (
    RuleCondition,
    RuleDefinition,
)


def default_rule_library() -> list[RuleDefinition]:
    return [
        RuleDefinition(
            rule_id="positive_flow_basic",
            name="Positive Flow Basic",
            description="Exploratory feature hypothesis only; not a live trading rule.",
            conditions=[
                RuleCondition("confidence_weighted_net_flow", "gt", 0),
                RuleCondition("possible_buy_count", "gte", 1),
            ],
        ),
        RuleDefinition(
            rule_id="buy_imbalance_basic",
            name="Buy Imbalance Basic",
            description="Exploratory feature hypothesis only; not a live trading rule.",
            conditions=[
                RuleCondition("buy_sell_imbalance", "gte", 0.5),
                RuleCondition("possible_buy_count", "gte", 2),
            ],
        ),
        RuleDefinition(
            rule_id="unique_actor_flow_basic",
            name="Unique Actor Flow Basic",
            description="Exploratory feature hypothesis only; not a live trading rule.",
            conditions=[
                RuleCondition("unique_actor_count", "gte", 3),
                RuleCondition("confidence_weighted_net_flow", "gt", 0),
            ],
        ),
        RuleDefinition(
            rule_id="volume_and_flow_basic",
            name="Volume and Flow Basic",
            description="Exploratory feature hypothesis only; not a live trading rule.",
            conditions=[
                RuleCondition("quote_volume", "gt", 0),
                RuleCondition("confidence_weighted_net_flow", "gt", 0),
            ],
        ),
        RuleDefinition(
            rule_id="low_sell_pressure_basic",
            name="Low Sell Pressure Basic",
            description="Exploratory feature hypothesis only; not a live trading rule.",
            conditions=[
                RuleCondition("possible_sell_count", "lte", 1),
                RuleCondition("possible_buy_count", "gte", 1),
            ],
        ),
    ]
