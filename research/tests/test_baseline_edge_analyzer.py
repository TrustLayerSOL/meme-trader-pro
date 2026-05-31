from research.mtp_research.validation.baseline_edge_analyzer import BaselineEdgeAnalyzer
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(
    row_id: str,
    feature_value: float | None,
    forward_return: float | None,
    *,
    token_mint: str = "mint-1",
    window_name: str = "1m",
    horizon_name: str = "5m",
    label_quality: str = "sparse",
    rug_like_drop: bool | None = False,
    no_future_liquidity: bool = False,
    survived_horizon: bool | None = True,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=100 + int(row_id.split("-")[-1]),
        window_name=window_name,
        window_seconds=60,
        horizon_name=horizon_name,
        horizon_seconds=300,
        age_sec=feature_value,
        event_count=int(feature_value or 0),
        forward_return=forward_return,
        max_runup=0.20 if forward_return is not None else None,
        max_drawdown=-0.10 if forward_return is not None else None,
        future_event_count=2,
        future_quote_volume=5.0,
        rug_like_drop=rug_like_drop,
        no_future_liquidity=no_future_liquidity,
        survived_horizon=survived_horizon,
        label_quality=label_quality,
    )


def test_filters_by_token_window_horizon_quality_and_minimum_label_quality() -> None:
    rows = [
        _row("row-1", 1, 0.1),
        _row("row-2", 2, 0.2, token_mint="mint-2"),
        _row("row-3", 3, 0.3, window_name="5m"),
        _row("row-4", 4, 0.4, horizon_name="15m"),
        _row("row-5", 5, 0.5, label_quality="no_price"),
    ]
    filtered = BaselineEdgeAnalyzer().filter_dataset_rows(
        rows,
        token_mints=["mint-1"],
        window_names=["1m"],
        horizon_names=["5m"],
        min_label_quality="sparse",
    )
    assert [row.row_id for row in filtered] == ["row-1"]


def test_require_forward_return_removes_rows_without_forward_return() -> None:
    rows = [_row("row-1", 1, 0.1), _row("row-2", 2, None)]
    analyzer = BaselineEdgeAnalyzer()
    assert [row.row_id for row in analyzer.filter_dataset_rows(rows)] == ["row-1"]
    assert [row.row_id for row in analyzer.filter_dataset_rows(rows, require_forward_return=False)] == ["row-1", "row-2"]


def test_summarize_outcomes_calculates_core_rates() -> None:
    rows = [
        _row("row-1", 1, 0.1),
        _row("row-2", 2, -0.2, rug_like_drop=True, no_future_liquidity=True, survived_horizon=False),
        _row("row-3", 3, 0.3),
    ]
    summary = BaselineEdgeAnalyzer().summarize_outcomes(rows)
    assert summary.row_count == 3
    assert summary.avg_forward_return == (0.1 - 0.2 + 0.3) / 3
    assert summary.median_forward_return == 0.1
    assert summary.win_rate == 2 / 3
    assert summary.rug_like_drop_rate == 1 / 3
    assert summary.no_future_liquidity_rate == 1 / 3
    assert summary.survived_horizon_rate == 2 / 3


def test_numeric_buckets_are_deterministic_and_exclude_missing_values() -> None:
    rows = [
        _row("row-3", 3, 0.3),
        _row("row-1", 1, 0.1),
        _row("row-2", None, 0.2),
        _row("row-4", 4, 0.4),
    ]
    buckets = BaselineEdgeAnalyzer(bucket_count=3).make_numeric_buckets(rows, "age_sec")
    assert [bucket.bucket_name for bucket, _rows in buckets] == ["q1_low", "q2", "q3_high"]
    assert [[row.row_id for row in bucket_rows] for _bucket, bucket_rows in buckets] == [["row-1"], ["row-3"], ["row-4"]]


def test_low_variance_feature_emits_warning() -> None:
    rows = [_row("row-1", 7, 0.1), _row("row-2", 7, 0.2)]
    report = BaselineEdgeAnalyzer(min_bucket_size=1).analyze_feature(rows, "age_sec")
    assert "low_variance_feature" in report.warning_flags


def test_small_bucket_emits_warning() -> None:
    rows = [_row("row-1", 1, 0.1), _row("row-2", 2, 0.2)]
    report = BaselineEdgeAnalyzer(min_bucket_size=2, bucket_count=2).analyze_feature(rows, "age_sec")
    assert all("small_bucket" in result.warning_flags for result in report.bucket_results)


def test_analyze_feature_creates_best_and_worst_bucket() -> None:
    rows = [_row("row-1", 1, -0.2), _row("row-2", 2, 0.1), _row("row-3", 3, 0.4)]
    report = BaselineEdgeAnalyzer(min_bucket_size=1, bucket_count=3).analyze_feature(rows, "age_sec")
    assert report.best_bucket_name == "q3_high"
    assert report.worst_bucket_name == "q1_low"
    assert report.spread_avg_forward_return == 0.6000000000000001


def test_analyze_creates_report_warning_flags_and_top_findings_without_strategy_language() -> None:
    rows = [_row(f"row-{idx}", idx, idx / 100) for idx in range(1, 9)]
    report = BaselineEdgeAnalyzer(min_bucket_size=1, bucket_count=4).analyze(rows, feature_names=["age_sec"])
    assert report.filtered_row_count == 8
    assert "exploratory_report_not_trading_signal" in report.warning_flags
    assert report.top_findings
    joined = " ".join(report.top_findings).lower()
    assert "requires backtest and walk-forward validation" in joined
    assert "buy" not in joined
    assert "trade" not in joined


def test_future_outcome_fields_are_not_default_features() -> None:
    future_fields = {
        "forward_return",
        "max_runup",
        "max_drawdown",
        "future_event_count",
        "future_quote_volume",
        "future_base_volume",
        "rug_like_drop",
        "survived_horizon",
        "no_future_liquidity",
    }
    assert future_fields.isdisjoint(BaselineEdgeAnalyzer.default_feature_names())
