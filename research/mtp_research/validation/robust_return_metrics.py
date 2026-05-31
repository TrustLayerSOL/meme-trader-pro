"""Robust return metrics for diagnostic rule reports."""

from __future__ import annotations

from statistics import mean as _mean
from statistics import median as _median
from typing import Any


def winsorized_mean(
    values: list[float],
    lower_pct: float = 0.05,
    upper_pct: float = 0.95,
) -> float | None:
    clean = sorted(_clean_values(values))
    if not clean:
        return None
    lower_idx = _pct_index(len(clean), lower_pct)
    upper_idx = _pct_index(len(clean), upper_pct)
    lower = clean[lower_idx]
    upper = clean[upper_idx]
    return _mean(min(max(value, lower), upper) for value in clean)


def trimmed_mean(values: list[float], trim_pct: float = 0.1) -> float | None:
    clean = sorted(_clean_values(values))
    if not clean:
        return None
    trim_count = int(len(clean) * trim_pct)
    if trim_count <= 0:
        return _mean(clean)
    trimmed = clean[trim_count:-trim_count]
    if not trimmed:
        return _mean(clean)
    return _mean(trimmed)


def median(values: list[float]) -> float | None:
    clean = _clean_values(values)
    if not clean:
        return None
    return _median(clean)


def positive_rate(values: list[float]) -> float | None:
    clean = _clean_values(values)
    if not clean:
        return None
    return sum(1 for value in clean if value > 0) / len(clean)


def summarize_robust_returns(values: list[float]) -> dict[str, Any]:
    clean = _clean_values(values)
    sorted_positive = sorted((value for value in clean if value > 0), reverse=True)
    total_positive = sum(sorted_positive)
    return {
        "count": len(clean),
        "mean": _mean(clean) if clean else None,
        "median": median(clean),
        "trimmed_mean": trimmed_mean(clean, trim_pct=0.2),
        "winsorized_mean": winsorized_mean(clean),
        "positive_rate": positive_rate(clean),
        "top_1_outlier_contribution": _outlier_contribution(sorted_positive, total_positive, 1),
        "top_5_outlier_contribution": _outlier_contribution(sorted_positive, total_positive, 5),
        "top_10_outlier_contribution": _outlier_contribution(sorted_positive, total_positive, 10),
    }


def _clean_values(values: list[float]) -> list[float]:
    return [float(value) for value in values if value is not None]


def _pct_index(length: int, pct: float) -> int:
    if length <= 1:
        return 0
    bounded = min(max(pct, 0.0), 1.0)
    return min(length - 1, max(0, int(round((length - 1) * bounded))))


def _outlier_contribution(values: list[float], total: float, count: int) -> float | None:
    if total <= 0:
        return None
    return sum(values[:count]) / total
