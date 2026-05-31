from research.mtp_research.validation.price_outlier_auditor import (
    find_extreme_return_rows,
    find_extreme_runup_rows,
    group_outliers_by_entry_source,
    group_outliers_by_token,
    summarize_price_outliers,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(
    row_id: str,
    token_mint: str,
    forward_return: float | None,
    max_runup: float | None,
    source: str = "exact_snapshot",
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="15m",
        horizon_seconds=900,
        entry_price_source=source,
        forward_return=forward_return,
        max_runup=max_runup,
        label_quality="sparse",
    )


def test_price_outlier_auditor_finds_extreme_rows_and_groups_them() -> None:
    rows = [
        _row("a", "mint-a", 1.5, 0.2, "nearest_research_fallback"),
        _row("b", "mint-b", 0.1, 2.0),
        _row("c", "mint-a", -0.1, 0.1),
    ]

    assert [row.row_id for row in find_extreme_return_rows(rows)] == ["a"]
    assert [row.row_id for row in find_extreme_runup_rows(rows)] == ["b"]
    assert group_outliers_by_token(rows) == {"mint-a": 2, "mint-b": 1}
    assert group_outliers_by_entry_source(rows) == {
        "exact_snapshot": 2,
        "nearest_research_fallback": 1,
    }

    summary = summarize_price_outliers(rows)
    assert summary["extreme_forward_return_count"] == 1
    assert summary["extreme_runup_count"] == 1
