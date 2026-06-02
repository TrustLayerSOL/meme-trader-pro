import json
from pathlib import Path

from research.mtp_research.validation.explosive_runner_winner_anatomy_report import (
    build_explosive_runner_winner_anatomy_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, ts: int, age: int, value: float, events: int, buys: int, active: int, holders: int | None = None) -> dict:
    row = {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": ts,
        "snapshot_ts": ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": max(0, events - buys),
        "active_wallets": active,
        "unique_actors": active,
        "tx_count": events,
        "metadata_json": {"event_count": events},
    }
    if holders is not None:
        row["holder_count"] = holders
    return row


def _sample_rows() -> list[dict]:
    rows = []
    tiers = [
        ("never", 12_000),
        ("t20", 30_000),
        ("t50", 80_000),
        ("t100", 150_000),
        ("t200", 300_000),
        ("t500", 700_000),
        ("t1m", 1_200_000),
    ]
    for idx, (mint, peak) in enumerate(tiers):
        ts = 1_700_000_000 + idx * 86_400
        rows.extend(
            [
                _snapshot(mint, ts, 30, min(15_000, peak), 4, 3, 3, holders=2 + idx),
                _snapshot(mint, ts, 60, min(20_000, peak), 5, 4, 4, holders=3 + idx),
                _snapshot(mint, ts, 120, peak, 8, 5, 5, holders=4 + idx),
            ]
        )
    return rows


def test_report_assigns_exactly_one_highest_milestone_tier(tmp_path: Path) -> None:
    report, _paths = build_explosive_runner_winner_anatomy_report(
        snapshot_paths=[_write_jsonl(tmp_path / "snapshots.jsonl", _sample_rows())],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "WINNER_STATUS.md",
    )
    counts = {tier: values["launch_count"] for tier, values in report["milestone_tier_summary"].items()}

    assert counts["never_reached_20k"] == 1
    assert counts["reached_20k_but_never_50k"] == 1
    assert counts["reached_50k_but_never_100k"] == 1
    assert counts["reached_100k_but_never_200k"] == 1
    assert counts["reached_200k_but_never_500k"] == 1
    assert counts["reached_500k_but_never_1m"] == 1
    assert counts["reached_1m_plus"] == 1
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_trading_rules" in report["methodology_flags"]


def test_report_builds_feature_coverage_and_holder_fdv_tables(tmp_path: Path) -> None:
    report, paths = build_explosive_runner_winner_anatomy_report(
        snapshot_paths=[_write_jsonl(tmp_path / "snapshots.jsonl", _sample_rows())],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "WINNER_STATUS.md",
    )

    assert report["coverage_report"]["trigger_counts"]["20k"] == 6
    assert report["holder_fdv_relationship_conclusion"]["paired_rows"] > 0
    assert paths["milestone_tier_feature_comparison_path"].exists()
    assert paths["holder_fdv_relationship_deep_dive_path"].exists()


def test_report_generates_archetypes_and_recommendation_schema(tmp_path: Path) -> None:
    rows = []
    for idx in range(40):
        mint = f"mint-{idx}"
        ts = 1_700_000_000 + idx * 86_400
        high = idx % 2 == 0
        peak = 1_200_000 if high else 40_000
        events = 4 if high else 18
        rows.extend(
            [
                _snapshot(mint, ts, 30, 15_000, events, 3, 3, holders=idx + 2),
                _snapshot(mint, ts, 60, 20_000, events, 3, 3, holders=idx + 3),
                _snapshot(mint, ts, 120, peak, events + 1, 4, 4, holders=idx + 4),
            ]
        )
    report, paths = build_explosive_runner_winner_anatomy_report(
        snapshot_paths=[_write_jsonl(tmp_path / "snapshots.jsonl", rows)],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "WINNER_STATUS.md",
    )

    assert report["runner_archetypes"]
    assert all("archetype" in row and "example_count" in row for row in report["runner_archetypes"])
    assert report["recommended_next_theses"]
    assert all("thesis_name" in row and "recommended_type" in row for row in report["recommended_next_theses"])
    assert paths["runner_archetype_summary_path"].exists()
    assert paths["recommended_next_theses_path"].exists()
