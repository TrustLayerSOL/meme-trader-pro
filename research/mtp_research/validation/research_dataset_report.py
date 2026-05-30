"""Deterministic summaries for research dataset rows."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def summarize_rows(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    returns = [row.forward_return for row in rows if row.forward_return is not None]
    return {
        "row_count": len(rows),
        "token_count": len({row.token_mint for row in rows}),
        "window_counts": dict(sorted(Counter(row.window_name for row in rows).items())),
        "horizon_counts": dict(sorted(Counter(row.horizon_name for row in rows).items())),
        "label_quality_counts": summarize_by_label_quality(rows),
        "rows_with_forward_return": len(returns),
        "avg_forward_return": mean(returns) if returns else None,
        "median_forward_return": median(returns) if returns else None,
        "positive_forward_return_count": sum(1 for value in returns if value > 0),
        "negative_forward_return_count": sum(1 for value in returns if value < 0),
        "rug_like_drop_count": sum(1 for row in rows if row.rug_like_drop is True),
        "no_future_liquidity_count": sum(1 for row in rows if row.no_future_liquidity),
    }


def bucket_forward_returns(rows: list[ResearchDatasetRow]) -> dict[str, int]:
    buckets = {
        "lt_minus_50pct": 0,
        "minus_50_to_minus_10pct": 0,
        "minus_10_to_0pct": 0,
        "zero_to_10pct": 0,
        "ten_to_50pct": 0,
        "gte_50pct": 0,
        "missing": 0,
    }
    for row in rows:
        value = row.forward_return
        if value is None:
            buckets["missing"] += 1
        elif value < -0.5:
            buckets["lt_minus_50pct"] += 1
        elif value < -0.1:
            buckets["minus_50_to_minus_10pct"] += 1
        elif value < 0:
            buckets["minus_10_to_0pct"] += 1
        elif value < 0.1:
            buckets["zero_to_10pct"] += 1
        elif value < 0.5:
            buckets["ten_to_50pct"] += 1
        else:
            buckets["gte_50pct"] += 1
    return buckets


def summarize_by_horizon(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    return {
        horizon: summarize_rows([row for row in rows if row.horizon_name == horizon])
        for horizon in sorted({row.horizon_name for row in rows})
    }


def summarize_by_window(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    return {
        window: summarize_rows([row for row in rows if row.window_name == window])
        for window in sorted({row.window_name for row in rows})
    }


def summarize_by_label_quality(rows: list[ResearchDatasetRow]) -> dict[str, int]:
    return dict(sorted(Counter(row.label_quality for row in rows).items()))
