"""Models for walk-forward fold sufficiency diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


FOLD_SUFFICIENCY_WARNING = "Fold sufficiency is diagnostic only. It is not strategy optimization."


@dataclass
class FoldConfigCandidate:
    name: str
    train_window_seconds: int
    test_window_seconds: int
    step_seconds: int
    gap_seconds: int = 0
    min_train_rows: int = 10
    min_test_rows: int = 5
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleFoldSufficiency:
    rule_id: str
    rule_name: str
    rows_selected_total: int = 0
    folds_with_train_rows: int = 0
    folds_with_test_rows: int = 0
    folds_with_selected_train_trades: int = 0
    folds_with_selected_test_trades: int = 0
    valid_test_fold_count: int = 0
    total_test_selected_count: int = 0
    avg_test_selected_count: float | None = None
    max_test_selected_count: int = 0
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class FoldConfigSufficiencyResult:
    config_name: str
    train_window_seconds: int
    test_window_seconds: int
    step_seconds: int
    gap_seconds: int
    min_train_rows: int
    min_test_rows: int
    fold_count: int = 0
    valid_fold_count: int = 0
    row_count: int = 0
    token_count: int = 0
    time_span_seconds: int | None = None
    rule_sufficiency: list[RuleFoldSufficiency] = field(default_factory=list)
    recommended: bool = False
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class FoldSufficiencyReport:
    report_id: str
    created_at: str
    dataset_path: str
    row_count: int
    token_count: int
    time_min: int | None = None
    time_max: int | None = None
    time_span_seconds: int | None = None
    config_results: list[FoldConfigSufficiencyResult] = field(default_factory=list)
    best_config_name: str | None = None
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_fold_sufficiency_report_id(prefix: str = "fold_sufficiency") -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
