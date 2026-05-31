"""Offline helpers for inspecting price-return outliers in research datasets."""

from __future__ import annotations

from collections import Counter
from typing import Any

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def find_extreme_return_rows(
    rows: list[ResearchDatasetRow],
    threshold: float = 1.0,
    limit: int = 50,
) -> list[ResearchDatasetRow]:
    matches = [
        row for row in rows
        if row.forward_return is not None and row.forward_return >= threshold
    ]
    return sorted(matches, key=lambda row: (row.forward_return or 0.0), reverse=True)[:limit]


def find_extreme_runup_rows(
    rows: list[ResearchDatasetRow],
    threshold: float = 1.0,
    limit: int = 50,
) -> list[ResearchDatasetRow]:
    matches = [
        row for row in rows
        if row.max_runup is not None and row.max_runup >= threshold
    ]
    return sorted(matches, key=lambda row: (row.max_runup or 0.0), reverse=True)[:limit]


def summarize_price_outliers(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    extreme_returns = find_extreme_return_rows(rows, limit=len(rows))
    extreme_runups = find_extreme_runup_rows(rows, limit=len(rows))
    return {
        "row_count": len(rows),
        "extreme_forward_return_count": len(extreme_returns),
        "extreme_runup_count": len(extreme_runups),
        "token_concentration": group_outliers_by_token(extreme_returns + extreme_runups),
        "entry_price_source_counts": group_outliers_by_entry_source(extreme_returns + extreme_runups),
        "max_forward_return": max(
            (row.forward_return for row in rows if row.forward_return is not None),
            default=None,
        ),
        "max_runup": max(
            (row.max_runup for row in rows if row.max_runup is not None),
            default=None,
        ),
    }


def group_outliers_by_token(rows: list[ResearchDatasetRow]) -> dict[str, int]:
    return dict(sorted(Counter(row.token_mint for row in rows).items()))


def group_outliers_by_entry_source(rows: list[ResearchDatasetRow]) -> dict[str, int]:
    return dict(sorted(Counter(row.entry_price_source or "unknown" for row in rows).items()))
