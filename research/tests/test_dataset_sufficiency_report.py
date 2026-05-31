from research.mtp_research.validation.dataset_sufficiency_report import (
    summarize_dataset_sufficiency,
    summarize_rule_selectability,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, **kwargs):
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": "token-a",
        "snapshot_ts": 100,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "5m",
        "horizon_seconds": 300,
        "label_quality": "good",
        "entry_price": 1.0,
        "forward_return": 0.1,
        "entry_price_source": "last_before_snapshot",
    }
    payload.update(kwargs)
    return ResearchDatasetRow(**payload)


def test_dataset_sufficiency_counts_entry_price_and_forward_return() -> None:
    summary = summarize_dataset_sufficiency(
        [
            _row("1"),
            _row("2", entry_price=None, forward_return=None, label_quality="no_price"),
            _row("3", token_mint="token-b", entry_price_source="nearest_research_fallback"),
        ],
        token_mints={"token-a"},
    )

    assert summary["total_rows"] == 3
    assert summary["rows_with_entry_price"] == 2
    assert summary["rows_with_forward_return"] == 2
    assert summary["real_only_rows"] == 2
    assert summary["rows_by_label_quality"]["good"] == 2
    assert summary["rows_by_entry_price_source"]["nearest_research_fallback"] == 1


def test_rule_selectability_counts_sparse_and_good_rows() -> None:
    summary = summarize_rule_selectability(
        [_row("1", label_quality="good"), _row("2", label_quality="sparse"), _row("3", label_quality="no_price")]
    )

    assert summary["rows_min_label_quality_sparse"] == 2
    assert summary["rows_min_label_quality_good"] == 1
    assert summary["rows_with_entry_and_forward_return"] == 3
