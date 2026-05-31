from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.fold_sufficiency_analyzer import (
    FoldSufficiencyAnalyzer,
    _total_valid_rule_folds,
)
from research.mtp_research.validation.fold_sufficiency_models import FoldConfigCandidate
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, snapshot_ts: int, selectable: bool = True) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        end_price=1.1,
        forward_return=0.1,
        possible_buy_count=1 if selectable else 0,
        possible_sell_count=0,
        confidence_weighted_net_flow=1.0 if selectable else -1.0,
        buy_sell_imbalance=0.75 if selectable else 0.0,
        unique_actor_count=3 if selectable else 0,
        quote_volume=1.0 if selectable else 0.0,
        label_quality="sparse",
    )


def test_default_configs_exist() -> None:
    configs = FoldSufficiencyAnalyzer().default_config_candidates()

    assert [config.name for config in configs] == [
        "ultra_short_15m_train_5m_test",
        "short_30m_train_10m_test",
        "one_hour_train_15m_test",
        "six_hour_train_one_hour_test",
        "one_day_train_six_hour_test",
    ]


def test_summarize_dataset_time_works() -> None:
    rows = [_row("row-1", 100), _row("row-2", 3700)]
    summary = FoldSufficiencyAnalyzer().summarize_dataset_time(rows)

    assert summary["row_count"] == 2
    assert summary["token_count"] == 1
    assert summary["time_min"] == 100
    assert summary["time_max"] == 3700
    assert summary["time_span_seconds"] == 3600
    assert summary["rows_by_hour"] == {0: 1, 1: 1}


def test_evaluate_config_detects_no_valid_folds() -> None:
    rows = [_row(f"row-{idx}", idx * 60) for idx in range(4)]
    config = FoldConfigCandidate("tiny", 900, 300, 300, min_train_rows=5, min_test_rows=3)

    result = FoldSufficiencyAnalyzer().evaluate_config(rows, default_rule_library(), config)

    assert result.fold_count == 0
    assert "no_folds_generated" in result.warning_flags
    assert "no_valid_test_folds" in result.warning_flags


def test_evaluate_config_counts_selected_rows_and_valid_folds() -> None:
    rows = [_row(f"row-{idx}", idx * 60) for idx in range(31)]
    config = FoldConfigCandidate("tiny", 900, 300, 300, min_train_rows=5, min_test_rows=3)

    result = FoldSufficiencyAnalyzer().evaluate_config(rows, default_rule_library(), config)

    positive_flow = next(rule for rule in result.rule_sufficiency if rule.rule_id == "positive_flow_basic")
    assert result.fold_count > 0
    assert positive_flow.rows_selected_total == 31
    assert positive_flow.valid_test_fold_count > 0
    assert positive_flow.total_test_selected_count > 0


def test_analyze_picks_best_config_by_sufficiency_not_returns() -> None:
    rows = [_row(f"row-{idx}", idx * 60) for idx in range(31)]
    analyzer = FoldSufficiencyAnalyzer()
    report = analyzer.analyze(rows, default_rule_library(), dataset_path="dataset.jsonl")
    best = next(result for result in report.config_results if result.config_name == report.best_config_name)

    assert _total_valid_rule_folds(best) == max(
        _total_valid_rule_folds(result) for result in report.config_results
    )
    assert report.recommended_next_action == "scale_bounded_backfill"


def test_recommended_next_action_uses_shorter_diagnostic_folds_when_short_works() -> None:
    rows = [_row(f"row-{idx}", idx * 60) for idx in range(220)]
    report = FoldSufficiencyAnalyzer().analyze(rows, default_rule_library(), dataset_path="dataset.jsonl")

    assert report.best_config_name != "one_day_train_six_hour_test"
    assert report.recommended_next_action == "use_shorter_diagnostic_folds_until_dataset_scales"
