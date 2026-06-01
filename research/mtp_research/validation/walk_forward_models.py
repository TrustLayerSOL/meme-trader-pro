"""Models for chronological walk-forward validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class WalkForwardFold:
    fold_id: str
    fold_index: int
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    gap_seconds: int = 0
    train_row_count: int = 0
    test_row_count: int = 0
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WalkForwardFold":
        return cls(
            fold_id=payload["fold_id"],
            fold_index=payload["fold_index"],
            train_start_ts=payload["train_start_ts"],
            train_end_ts=payload["train_end_ts"],
            test_start_ts=payload["test_start_ts"],
            test_end_ts=payload["test_end_ts"],
            gap_seconds=payload.get("gap_seconds", 0),
            train_row_count=payload.get("train_row_count", 0),
            test_row_count=payload.get("test_row_count", 0),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class WalkForwardConfig:
    config_id: str
    train_window_seconds: int
    test_window_seconds: int
    step_seconds: int
    gap_seconds: int = 0
    min_train_rows: int = 25
    min_test_rows: int = 10
    horizon_name: str | None = None
    window_name: str | None = None
    min_label_quality: str = "sparse"
    require_entry_price: bool = True
    require_forward_return: bool = True
    max_folds: int | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WalkForwardConfig":
        return cls(
            config_id=payload["config_id"],
            train_window_seconds=payload["train_window_seconds"],
            test_window_seconds=payload["test_window_seconds"],
            step_seconds=payload["step_seconds"],
            gap_seconds=payload.get("gap_seconds", 0),
            min_train_rows=payload.get("min_train_rows", 25),
            min_test_rows=payload.get("min_test_rows", 10),
            horizon_name=payload.get("horizon_name"),
            window_name=payload.get("window_name"),
            min_label_quality=payload.get("min_label_quality", "sparse"),
            require_entry_price=payload.get("require_entry_price", True),
            require_forward_return=payload.get("require_forward_return", True),
            max_folds=payload.get("max_folds"),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class FoldRuleResult:
    fold_id: str
    fold_index: int
    rule_id: str
    rule_name: str
    train_result_id: str | None = None
    test_result_id: str | None = None
    train_selected_count: int = 0
    test_selected_count: int = 0
    train_avg_net_return: float | None = None
    test_avg_net_return: float | None = None
    train_median_net_return: float | None = None
    test_median_net_return: float | None = None
    train_win_rate: float | None = None
    test_win_rate: float | None = None
    train_profit_factor: float | None = None
    test_profit_factor: float | None = None
    train_cumulative_net_return: float | None = None
    test_cumulative_net_return: float | None = None
    train_max_equity_drawdown: float | None = None
    test_max_equity_drawdown: float | None = None
    train_rug_like_drop_rate: float | None = None
    test_rug_like_drop_rate: float | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FoldRuleResult":
        return cls(
            fold_id=payload["fold_id"],
            fold_index=payload["fold_index"],
            rule_id=payload["rule_id"],
            rule_name=payload["rule_name"],
            train_result_id=payload.get("train_result_id"),
            test_result_id=payload.get("test_result_id"),
            train_selected_count=payload.get("train_selected_count", 0),
            test_selected_count=payload.get("test_selected_count", 0),
            train_avg_net_return=payload.get("train_avg_net_return"),
            test_avg_net_return=payload.get("test_avg_net_return"),
            train_median_net_return=payload.get("train_median_net_return"),
            test_median_net_return=payload.get("test_median_net_return"),
            train_win_rate=payload.get("train_win_rate"),
            test_win_rate=payload.get("test_win_rate"),
            train_profit_factor=payload.get("train_profit_factor"),
            test_profit_factor=payload.get("test_profit_factor"),
            train_cumulative_net_return=payload.get("train_cumulative_net_return"),
            test_cumulative_net_return=payload.get("test_cumulative_net_return"),
            train_max_equity_drawdown=payload.get("train_max_equity_drawdown"),
            test_max_equity_drawdown=payload.get("test_max_equity_drawdown"),
            train_rug_like_drop_rate=payload.get("train_rug_like_drop_rate"),
            test_rug_like_drop_rate=payload.get("test_rug_like_drop_rate"),
            warning_flags=list(payload.get("warning_flags", [])),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class RuleWalkForwardSummary:
    rule_id: str
    rule_name: str
    fold_count: int = 0
    valid_test_fold_count: int = 0
    total_test_selected_count: int = 0
    avg_test_selected_count: float | None = None
    avg_test_net_return: float | None = None
    median_test_net_return: float | None = None
    positive_test_fold_count: int = 0
    negative_test_fold_count: int = 0
    positive_test_fold_rate: float | None = None
    avg_test_win_rate: float | None = None
    avg_test_profit_factor: float | None = None
    avg_test_cumulative_net_return: float | None = None
    worst_test_cumulative_net_return: float | None = None
    avg_test_max_drawdown: float | None = None
    avg_test_rug_like_drop_rate: float | None = None
    consistency_score: float | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleWalkForwardSummary":
        return cls(
            rule_id=payload["rule_id"],
            rule_name=payload["rule_name"],
            fold_count=payload.get("fold_count", 0),
            valid_test_fold_count=payload.get("valid_test_fold_count", 0),
            total_test_selected_count=payload.get("total_test_selected_count", 0),
            avg_test_selected_count=payload.get("avg_test_selected_count"),
            avg_test_net_return=payload.get("avg_test_net_return"),
            median_test_net_return=payload.get("median_test_net_return"),
            positive_test_fold_count=payload.get("positive_test_fold_count", 0),
            negative_test_fold_count=payload.get("negative_test_fold_count", 0),
            positive_test_fold_rate=payload.get("positive_test_fold_rate"),
            avg_test_win_rate=payload.get("avg_test_win_rate"),
            avg_test_profit_factor=payload.get("avg_test_profit_factor"),
            avg_test_cumulative_net_return=payload.get("avg_test_cumulative_net_return"),
            worst_test_cumulative_net_return=payload.get("worst_test_cumulative_net_return"),
            avg_test_max_drawdown=payload.get("avg_test_max_drawdown"),
            avg_test_rug_like_drop_rate=payload.get("avg_test_rug_like_drop_rate"),
            consistency_score=payload.get("consistency_score"),
            warning_flags=list(payload.get("warning_flags", [])),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class WalkForwardValidationResult:
    validation_id: str
    created_at: str
    config: WalkForwardConfig
    dataset_path: str
    row_count: int
    filtered_row_count: int
    fold_count: int
    rules_tested: int
    folds: list[WalkForwardFold] = field(default_factory=list)
    fold_rule_results: list[FoldRuleResult] = field(default_factory=list)
    rule_summaries: list[RuleWalkForwardSummary] = field(default_factory=list)
    top_findings: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "created_at": self.created_at,
            "config": self.config.to_dict(),
            "dataset_path": self.dataset_path,
            "row_count": self.row_count,
            "filtered_row_count": self.filtered_row_count,
            "fold_count": self.fold_count,
            "rules_tested": self.rules_tested,
            "folds": [fold.to_dict() for fold in self.folds],
            "fold_rule_results": [result.to_dict() for result in self.fold_rule_results],
            "rule_summaries": [summary.to_dict() for summary in self.rule_summaries],
            "top_findings": list(self.top_findings),
            "warning_flags": list(self.warning_flags),
            "metadata_json": dict(self.metadata_json),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WalkForwardValidationResult":
        return cls(
            validation_id=payload["validation_id"],
            created_at=payload["created_at"],
            config=WalkForwardConfig.from_dict(payload["config"]),
            dataset_path=payload.get("dataset_path", ""),
            row_count=payload.get("row_count", 0),
            filtered_row_count=payload.get("filtered_row_count", 0),
            fold_count=payload.get("fold_count", 0),
            rules_tested=payload.get("rules_tested", 0),
            folds=[WalkForwardFold.from_dict(fold) for fold in payload.get("folds", [])],
            fold_rule_results=[
                FoldRuleResult.from_dict(result)
                for result in payload.get("fold_rule_results", [])
            ],
            rule_summaries=[
                RuleWalkForwardSummary.from_dict(summary)
                for summary in payload.get("rule_summaries", [])
            ],
            top_findings=list(payload.get("top_findings", [])),
            warning_flags=list(payload.get("warning_flags", [])),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


def make_walk_forward_config_id(
    train_window_seconds: int,
    test_window_seconds: int,
    step_seconds: int,
    gap_seconds: int = 0,
) -> str:
    return (
        f"walk_forward_v0__train_{train_window_seconds}"
        f"__test_{test_window_seconds}__step_{step_seconds}__gap_{gap_seconds}"
    )


def make_fold_id(config_id: str, fold_index: int) -> str:
    digest = sha256(f"{config_id}|{fold_index}".encode("utf-8")).hexdigest()[:12]
    return f"wf-fold-{fold_index}-{digest}"


def make_validation_id(config_id: str) -> str:
    digest = sha256(f"{config_id}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()[:16]
    return f"walk-forward-{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
