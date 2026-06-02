import csv
import json
from pathlib import Path

from research.mtp_research.validation.t011_explosive_runner_validation import (
    build_t011_validation_report,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(index: int, *, event_count: int, fdv_per_event: float, winner: bool, creator: str = "creator") -> dict:
    creator_value = creator if creator == "dominant" else f"{creator}-{index % 6}"
    return {
        "token_mint": f"mint-{index}",
        "launch_id": f"launch-{index}",
        "creator": creator_value,
        "launch_ts": 1_700_000_000 + index,
        "trigger_age_seconds": 60,
        "trigger_fdv_proxy": event_count * fdv_per_event,
        "peak_fdv_proxy": 120_000 if winner else 40_000,
        "milestone_tier": "reached_1m_plus" if winner else "reached_20k_but_never_50k",
        "event_count_at_20k": event_count,
        "buy_count_at_20k": max(1, event_count - 1),
        "sell_count_at_20k": 1,
        "active_wallets_at_20k": max(1, event_count // 2),
        "crossed_50k_after_20k": winner,
        "crossed_100k_after_20k": winner,
        "crossed_200k_after_20k": winner,
        "crossed_500k_after_20k": winner,
        "crossed_1m_after_20k": winner,
    }


def _design(path: Path) -> Path:
    return _write_json(
        path,
        {
            "report_id": "t011_validation_design_v0",
            "validation_design": {
                "primary_split": {"type": "chronological", "train_pct": 60, "holdout_pct": 40},
                "primary_trigger": 20000,
                "secondary_triggers": [15000, 30000],
                "primary_outcome": "crossed_100k_after_20k",
                "bucket_method": "train_partition_quintiles_only",
                "primary_contrast": "highest_fdv_per_event_quintile_and_lowest_event_count_quintile_vs_all_other_holdout_launches",
            },
        },
    )


def test_validation_uses_train_only_cutoffs_and_holdout_eval(tmp_path: Path) -> None:
    rows = []
    for idx in range(10):
        rows.append(_row(idx, event_count=10 + idx, fdv_per_event=100 + idx, winner=False))
    for idx in range(10, 14):
        rows.append(_row(idx, event_count=1, fdv_per_event=30_000, winner=True))
    for idx in range(14, 20):
        rows.append(_row(idx, event_count=20, fdv_per_event=1_000, winner=False))
    report = build_t011_validation_report(
        design_path=_design(tmp_path / "design.json"),
        trigger_20k_rows_path=_write_csv(tmp_path / "rows.csv", rows),
        t011_summary_path=_write_json(tmp_path / "summary.json", {"final_classification": "descriptive_signal_present"}),
        robustness_summary_path=_write_json(tmp_path / "robust.json", {"robustness_classification": "robust_descriptive_signal"}),
    )

    assert report["primary_split"]["train_rows"] == 12
    assert report["primary_split"]["holdout_rows"] == 8
    assert report["training_cutoffs"]["event_count_lowest_quintile_max"] == 1
    assert report["training_cutoffs"]["fdv_per_event_highest_quintile_min"] == 30000
    assert report["primary_validation"]["primary_group_count"] == 2
    assert report["primary_validation"]["primary_group_hit_rate"] == 1.0
    assert report["leakage_checks"]["all_checks_passed"] is True
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_validation_classifies_data_limited_when_support_is_tiny(tmp_path: Path) -> None:
    rows = [_row(idx, event_count=10 + idx, fdv_per_event=100, winner=False) for idx in range(6)]
    report = build_t011_validation_report(
        design_path=_design(tmp_path / "design.json"),
        trigger_20k_rows_path=_write_csv(tmp_path / "rows.csv", rows),
    )

    assert report["validation_classification"] == "validation_data_limited"
    assert report["failure_conditions"]["bucket_support_too_small"] is True


def test_validation_reports_creator_date_dominance(tmp_path: Path) -> None:
    rows = []
    for idx in range(10):
        rows.append(_row(idx, event_count=10 + idx, fdv_per_event=100 + idx, winner=False))
    for idx in range(10, 20):
        rows.append(_row(idx, event_count=1, fdv_per_event=30_000, winner=True, creator="dominant"))
    report = build_t011_validation_report(
        design_path=_design(tmp_path / "design.json"),
        trigger_20k_rows_path=_write_csv(tmp_path / "rows.csv", rows),
    )

    dominance = report["dominance_checks"]
    assert dominance["dominant_creator_share_primary_group"] >= 0.5
    assert "creator_or_date_dominance" in report["warning_flags"]
