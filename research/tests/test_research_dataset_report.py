from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_report import (
    bucket_forward_returns,
    summarize_by_horizon,
    summarize_by_label_quality,
    summarize_by_window,
    summarize_rows,
)


def _row(
    row_id: str,
    forward_return: float | None,
    *,
    token_mint: str = "mint-1",
    window_name: str = "1m",
    horizon_name: str = "1m",
    label_quality: str = "good",
    rug_like_drop: bool = False,
    no_future_liquidity: bool = False,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=100,
        window_name=window_name,
        window_seconds=60,
        horizon_name=horizon_name,
        horizon_seconds=60,
        forward_return=forward_return,
        rug_like_drop=rug_like_drop,
        no_future_liquidity=no_future_liquidity,
        label_quality=label_quality,
    )


def test_empty_rows_are_handled_safely() -> None:
    summary = summarize_rows([])
    assert summary["row_count"] == 0
    assert summary["token_count"] == 0
    assert summary["avg_forward_return"] is None
    assert summary["median_forward_return"] is None


def test_summarize_rows_counts_and_returns() -> None:
    rows = [
        _row("a", 0.2),
        _row("b", -0.1, token_mint="mint-2", horizon_name="5m", label_quality="sparse", rug_like_drop=True),
        _row("c", None, no_future_liquidity=True),
    ]
    summary = summarize_rows(rows)
    assert summary["row_count"] == 3
    assert summary["token_count"] == 2
    assert summary["window_counts"] == {"1m": 3}
    assert summary["horizon_counts"] == {"1m": 2, "5m": 1}
    assert summary["label_quality_counts"] == {"good": 2, "sparse": 1}
    assert summary["rows_with_forward_return"] == 2
    assert summary["avg_forward_return"] == 0.05
    assert summary["median_forward_return"] == 0.05
    assert summary["positive_forward_return_count"] == 1
    assert summary["negative_forward_return_count"] == 1
    assert summary["rug_like_drop_count"] == 1
    assert summary["no_future_liquidity_count"] == 1


def test_bucket_forward_returns() -> None:
    buckets = bucket_forward_returns(
        [
            _row("a", -0.8),
            _row("b", -0.2),
            _row("c", -0.05),
            _row("d", 0.05),
            _row("e", 0.2),
            _row("f", 0.8),
            _row("g", None),
        ]
    )
    assert buckets == {
        "lt_minus_50pct": 1,
        "minus_50_to_minus_10pct": 1,
        "minus_10_to_0pct": 1,
        "zero_to_10pct": 1,
        "ten_to_50pct": 1,
        "gte_50pct": 1,
        "missing": 1,
    }


def test_grouped_summaries() -> None:
    rows = [_row("a", 0.1, window_name="1m"), _row("b", 0.2, window_name="5m", horizon_name="5m")]
    assert set(summarize_by_horizon(rows)) == {"1m", "5m"}
    assert set(summarize_by_window(rows)) == {"1m", "5m"}
    assert summarize_by_label_quality(rows) == {"good": 2}
