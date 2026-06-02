import json
from pathlib import Path

from research.mtp_research.validation.historical_date_expansion import (
    build_historical_date_expansion,
    classify_readiness,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, launch_ts: int, age: int, value: float, events: int = 4) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "snapshot_ts": launch_ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": max(1, events - 1),
        "sell_count": 1,
        "active_wallets": 2,
        "unique_actors": 2,
        "tx_count": events,
        "metadata_json": {"event_count": events},
    }


def test_historical_expansion_counts_triggers_by_date(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("a", 1_700_000_000, 30, 15_000),
        _snapshot("a", 1_700_000_000, 60, 20_000),
        _snapshot("a", 1_700_000_000, 120, 100_000),
        _snapshot("b", 1_700_086_400, 60, 10_000),
        _snapshot("b", 1_700_086_400, 120, 30_000),
    ]
    report = build_historical_date_expansion(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        output_root=tmp_path / "out",
        report_dir=tmp_path / "reports",
    )

    assert report["coverage_audit"]["total_launches"] == 2
    assert report["coverage_audit"]["trigger_counts"]["20k"]["total_rows"] == 2
    assert len(report["expanded_trigger_labels"]) == 2
    first = next(row for row in report["expanded_trigger_labels"] if row["mint"] == "a")
    assert first["crossed_100k"] is True
    assert first["event_count_at_20k"] == 4
    assert first["fdv_per_event_at_20k"] == 5000


def test_readiness_requires_preferred_target_and_balance() -> None:
    assert classify_readiness(
        unique_dates=30,
        total_20k_rows=1000,
        median_rows_per_date=10,
        top_date_share=0.35,
        top3_date_share=0.59,
        forward_path_coverage=0.9,
        tiers_available=True,
        trigger_features_available=True,
    ) == "historical_expansion_ready_for_rerun"
    assert classify_readiness(
        unique_dates=3,
        total_20k_rows=422,
        median_rows_per_date=39,
        top_date_share=0.76,
        top3_date_share=1.0,
        forward_path_coverage=1.0,
        tiers_available=True,
        trigger_features_available=True,
    ) == "historical_expansion_requires_external_acquisition"


def test_source_classification_recommends_parallel_external_fetch_when_local_short(tmp_path: Path) -> None:
    report = build_historical_date_expansion(
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", [_snapshot("a", 1_700_000_000, 60, 20_000)]),
        output_root=tmp_path / "out",
        report_dir=tmp_path / "reports",
    )

    sources = report["expansion_paths"]
    assert sources["Helius historical transaction fetch"]["classification"] == "needs_external_fetch"
    assert "parallel_date_sharded_pull" in sources["Helius historical transaction fetch"]["recommended_method"]
    assert report["readiness_classification"] == "historical_expansion_requires_external_acquisition"
