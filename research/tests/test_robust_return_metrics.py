from research.mtp_research.validation.robust_return_metrics import (
    median,
    positive_rate,
    summarize_robust_returns,
    trimmed_mean,
    winsorized_mean,
)


def test_robust_return_metrics_reduce_outlier_influence() -> None:
    values = [-0.1, -0.05, 0.0, 0.05, 10.0]

    assert median(values) == 0.0
    assert positive_rate(values) == 0.4
    assert trimmed_mean(values, trim_pct=0.2) == 0.0
    assert winsorized_mean(values, lower_pct=0.2, upper_pct=0.8) < 3.0

    summary = summarize_robust_returns(values)
    assert summary["mean"] > summary["median"]
    assert summary["trimmed_mean"] == 0.0
