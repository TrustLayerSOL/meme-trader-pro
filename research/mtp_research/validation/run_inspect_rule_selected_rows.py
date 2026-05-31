"""Inspect diagnostic rows selected by a default exploratory rule."""

from __future__ import annotations

import argparse

from research.mtp_research.backtest.rule_backtest_models import CostAssumptions
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    rule = next((item for item in default_rule_library() if item.rule_id == args.rule_id), None)
    if rule is None:
        raise SystemExit(f"Unknown rule-id: {args.rule_id}")
    backtester = RuleBacktester()
    selected = [row for row in rows if backtester.row_passes_rule(row, rule)]
    total_selected_count = len(selected)
    selected = sorted(selected, key=lambda row: _sort_value(row, args.sort_by))
    if args.sort_by in {"net_return", "forward_return", "max_drawdown"}:
        selected.reverse()
    selected = selected[: args.limit]

    print(f"rule_id={args.rule_id}")
    print(f"selected_count={len(selected)}")
    print(f"total_selected_count={total_selected_count}")
    for index, row in enumerate(selected, start=1):
        print(
            "selected_row "
            f"index={index} "
            f"token_mint={row.token_mint} "
            f"snapshot_ts={row.snapshot_ts} "
            f"window={row.window_name} "
            f"horizon={row.horizon_name} "
            f"entry_price_source={row.entry_price_source} "
            f"label_quality={row.label_quality} "
            f"forward_return={row.forward_return} "
            f"net_return={_net_return(row)} "
            f"max_runup={row.max_runup} "
            f"max_drawdown={row.max_drawdown} "
            f"buy_sell_imbalance={row.buy_sell_imbalance} "
            f"possible_buy_count={row.possible_buy_count} "
            f"possible_sell_count={row.possible_sell_count} "
            f"unique_actor_count={row.unique_actor_count} "
            f"confidence_weighted_net_flow={row.confidence_weighted_net_flow}"
        )
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect rows selected by an exploratory rule.")
    parser.add_argument("--rule-id", default="buy_imbalance_basic")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--sort-by",
        choices=["snapshot_ts", "net_return", "forward_return", "max_drawdown"],
        default="snapshot_ts",
    )
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    return parser.parse_args()


def _net_return(row: ResearchDatasetRow) -> float | None:
    if row.forward_return is None:
        return None
    return row.forward_return - CostAssumptions().total_cost_return_drag()


def _sort_value(row: ResearchDatasetRow, sort_by: str):
    if sort_by == "snapshot_ts":
        return (row.snapshot_ts, row.row_id)
    if sort_by == "net_return":
        return (_net_return(row) if _net_return(row) is not None else -999, row.snapshot_ts)
    if sort_by == "forward_return":
        return (row.forward_return if row.forward_return is not None else -999, row.snapshot_ts)
    if sort_by == "max_drawdown":
        return (row.max_drawdown if row.max_drawdown is not None else -999, row.snapshot_ts)
    return (row.snapshot_ts, row.row_id)


if __name__ == "__main__":
    raise SystemExit(main())
