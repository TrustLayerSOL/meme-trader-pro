import json
from pathlib import Path

from research.mtp_research.validation.winner_anatomy_explosive_runner_discovery import (
    build_winner_anatomy_explosive_runner_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, value: float, holders: int | None = None, active: int = 3) -> dict:
    row = {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "active_wallets": active,
        "unique_actors": active,
        "buy_count": active,
        "sell_count": 1,
        "tx_count": active + 1,
        "metadata_json": {"event_count": active + 1},
    }
    if holders is not None:
        row["holder_count"] = holders
    return row


def test_detects_first_milestone_crossings_and_tier(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 30, 10_000),
        _snapshot("a", 60, 20_000),
        _snapshot("a", 120, 100_000),
        _snapshot("a", 300, 250_000),
    ]
    report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    row = report["launch_rows"][0]

    assert row["crossings"]["first_crossed_20k"]["age_seconds"] == 60
    assert row["crossed_100k_fdv_proxy"] is True
    assert row["crossed_200k_fdv_proxy"] is True
    assert row["milestone_tier"] == "reached_200k_but_never_500k"
    assert report["milestone_counts"]["crossed_100k_fdv_proxy"] == 1
    tier_features = report["milestone_tier_anatomy"]["reached_200k_but_never_500k"]["feature_medians"]
    assert tier_features["fdv_per_event"] == 5_000
    assert tier_features["fdv_per_buy"] == 20_000 / 3
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_selects_pre_crossing_and_non_winner_snapshots(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("winner", 60, 20_000, holders=100),
        _snapshot("winner", 240, 80_000, holders=200),
        _snapshot("winner", 300, 100_000, holders=250),
        _snapshot("non", 60, 20_000, holders=80),
        _snapshot("non", 180, 40_000, holders=90),
    ]
    report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )
    pre = [
        row for row in report["pre_milestone_snapshots"]
        if row["token_mint"] == "winner" and row["milestone"] == "100k" and row["snapshot_context"] == "60s_before"
    ]
    matched = [
        row for row in report["pre_milestone_snapshots"]
        if row["token_mint"] == "non" and row["milestone"] == "non_winner"
    ]

    assert pre
    assert pre[0]["snapshot_age_seconds"] == 240
    assert matched
    assert matched[0]["snapshot_context"] in {"first_20k", "peak_never_100k"}


def test_builds_holder_fdv_relationship_buckets(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 60, 8_000, holders=40),
        _snapshot("b", 60, 60_000, holders=250),
        _snapshot("c", 60, 600_000, holders=600),
    ]
    report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )

    holder_table = report["holder_fdv_relationship"]["median_fdv_by_holder_bucket"]
    fdv_table = report["holder_fdv_relationship"]["median_holder_count_by_fdv_bucket"]
    assert holder_table["0_to_49"]["sample_count"] == 1
    assert holder_table["500_to_999"]["median_fdv_proxy"] == 600_000
    assert fdv_table["50k_to_100k"]["median_holder_count"] == 250


def test_ready_classification_requires_higher_tier_examples(tmp_path: Path) -> None:
    snapshots = []
    for index in range(30):
        snapshots.extend([_snapshot(f"mint-{index}", 60, 20_000), _snapshot(f"mint-{index}", 120, 100_000)])
    report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )

    assert report["readiness_classification"] != "winner_anatomy_ready_for_formal_explosive_thesis"
    assert "no_trading_rules" in report["methodology_flags"]
