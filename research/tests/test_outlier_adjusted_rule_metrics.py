import json
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import RuleCondition, RuleDefinition
from research.mtp_research.validation.outlier_adjusted_rule_metrics import (
    build_outlier_adjusted_report,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, forward_return: float) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="15m",
        horizon_seconds=900,
        possible_buy_count=2,
        buy_sell_imbalance=0.8,
        forward_return=forward_return,
        label_quality="sparse",
    )


def _rule() -> RuleDefinition:
    return RuleDefinition(
        rule_id="buy_imbalance_basic",
        name="Buy Imbalance Basic",
        conditions=[RuleCondition("buy_sell_imbalance", "gte", 0.5)],
    )


def test_outlier_adjusted_report_separates_excluded_classifications(tmp_path: Path) -> None:
    outlier_report_path = tmp_path / "outliers.json"
    outlier_report_path.write_text(
        json.dumps(
            {
                "reviews": [
                    {"row_id": "outlier", "outlier_classification": "suspicious_price_jump"},
                    {"row_id": "good", "outlier_classification": "plausible_price_path"},
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_outlier_adjusted_report(
        [_row("loss", -0.1), _row("good", 0.2), _row("outlier", 10.0)],
        [_rule()],
        ["buy_imbalance_basic"],
        outlier_report_path=outlier_report_path,
        return_cap=1.0,
        dataset_path="dataset.jsonl",
    )

    summary = report["rule_summaries"][0]
    assert summary["selected_count"] == 3
    assert summary["excluded_outlier_count"] == 1
    assert summary["excluded_classification_counts"] == {"suspicious_price_jump": 1}
    assert summary["raw_metrics"]["mean"] > summary["capped_metrics"]["mean"]
    assert summary["included_metrics"]["mean"] == 0.05
    assert report["recommended_next_action"] == "separate_outlier_metrics_before_scaling"
