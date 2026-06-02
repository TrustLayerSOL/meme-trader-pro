import json
from pathlib import Path

from research.mtp_research.validation.short_window_expansion_discovery import (
    build_short_window_expansion_discovery_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, value: float, active: int = 2, buys: int = 2) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "active_wallets": active,
        "unique_actors": active,
        "buy_count": buys,
        "sell_count": 1,
        "tx_count": buys + 1,
        "metadata_json": {"event_count": buys + 1},
    }


def test_detects_trigger_and_short_window_labels(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 30, 10_000),
        _snapshot("a", 60, 20_000),
        _snapshot("a", 120, 55_000),
        _snapshot("a", 300, 105_000),
        _snapshot("a", 600, 80_000),
    ]
    report = build_short_window_expansion_discovery_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    labels = [row for row in report["label_rows"] if row["token_mint"] == "a" and row["trigger_name"] == "trigger_20k"]

    assert len(labels) == 1
    row = labels[0]
    assert row["trigger_age_seconds"] == 60
    assert row["hit_50k_within_2m"] is True
    assert row["hit_100k_within_5m"] is True
    assert row["hit_2x_before_down_30pct"] is True
    assert row["time_to_2x_seconds"] == 60
    assert report["trigger_feasibility"]["trigger_20k"]["launches_with_trigger"] == 1
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_target_before_stop_fails_when_drawdown_happens_first(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 60, 20_000),
        _snapshot("a", 120, 13_000),
        _snapshot("a", 180, 50_000),
    ]
    report = build_short_window_expansion_discovery_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    row = next(row for row in report["label_rows"] if row["trigger_name"] == "trigger_20k")

    assert row["failed_down_30pct_before_2x"] is True
    assert row["hit_2x_before_down_30pct"] is False
    assert row["time_to_failure_seconds"] == 60


def test_feature_snapshot_uses_only_data_at_or_before_trigger(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 30, 10_000, active=1, buys=1),
        _snapshot("a", 60, 20_000, active=2, buys=2),
        _snapshot("a", 120, 100_000, active=50, buys=50),
    ]
    report = build_short_window_expansion_discovery_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    row = next(row for row in report["label_rows"] if row["trigger_name"] == "trigger_20k")

    assert row["features_at_trigger"]["active_wallets_60s"] == 2
    assert row["features_at_trigger"]["buy_count_60s"] == 2
    assert row["features_at_trigger"]["future_snapshot_used"] is False


def test_ready_classification_requires_nontrivial_trigger_sample(tmp_path: Path) -> None:
    snapshots = []
    for index in range(40):
        snapshots.extend(
            [
                _snapshot(f"mint-{index}", 60, 20_000 + index),
                _snapshot(f"mint-{index}", 120, 45_000 + index),
            ]
        )
    report = build_short_window_expansion_discovery_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )

    assert report["readiness_classification"] in {
        "short_window_expansion_ready_for_formal_thesis",
        "short_window_expansion_partial_needs_more_forward_path",
        "short_window_expansion_blocked",
    }
    assert report["readiness_classification"] != "short_window_expansion_ready_for_formal_thesis"
