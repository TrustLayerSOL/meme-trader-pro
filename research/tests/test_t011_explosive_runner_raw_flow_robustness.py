import csv
import json
from pathlib import Path

from research.mtp_research.validation.t011_explosive_runner_raw_flow_robustness import (
    build_t011_raw_flow_robustness_report,
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


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _feature_row(mint: str, ts: int, tier: str, events: int, buys: int, active: int, creator: str) -> dict:
    return {
        "token_mint": mint,
        "launch_id": f"launch-{mint}",
        "creator": creator,
        "launch_ts": ts,
        "trigger_age_seconds": 60,
        "trigger_fdv_proxy": 20_000,
        "peak_fdv_proxy": 100_000 if "100k" in tier or "1m" in tier else 40_000,
        "milestone_tier": tier,
        "event_count_at_20k": events,
        "buy_count_at_20k": buys,
        "sell_count_at_20k": max(0, events - buys),
        "active_wallets_at_20k": active,
        "unique_actors_at_20k": active,
        "crossed_100k_after_20k": tier != "reached_20k_but_never_50k",
        "crossed_500k_after_20k": tier == "reached_1m_plus",
    }


def _snapshot(mint: str, age: int, value: float, events: int, buys: int, active: int, ts: int) -> dict:
    return {
        "token_mint": mint,
        "launch_id": f"launch-{mint}",
        "launch_ts": ts,
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


def test_robustness_report_identifies_stable_low_flow_pattern(tmp_path: Path) -> None:
    rows = []
    snapshots = []
    for idx in range(12):
        winner = idx % 2 == 0
        tier = "reached_1m_plus" if winner else "reached_20k_but_never_50k"
        events = 4 if winner else 16
        buys = 3 if winner else 9
        active = 3 if winner else 6
        mint = f"mint-{idx}"
        ts = 1_700_000_000 + idx * 3600
        rows.append(_feature_row(mint, ts, tier, events, buys, active, creator=f"creator-{idx % 4}"))
        snapshots.extend(
            [
                _snapshot(mint, 30, 15_000, events, buys, active, ts),
                _snapshot(mint, 60, 20_000, events, buys, active, ts),
                _snapshot(mint, 90, 30_000, events, buys, active, ts),
                _snapshot(mint, 120, 100_000 if winner else 40_000, events + 1, buys + 1, active + 1, ts),
            ]
        )
    summary = {
        "final_classification": "descriptive_signal_present",
        "trigger_summary": {"trigger_20k_count": len(rows)},
        "milestone_tier_counts": {"reached_1m_plus": 6, "reached_20k_but_never_50k": 6},
    }
    report = build_t011_raw_flow_robustness_report(
        t011_summary_path=_write_json(tmp_path / "summary.json", summary),
        trigger_20k_rows_path=_write_csv(tmp_path / "rows.csv", rows),
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
    )

    assert report["trigger_20k_count_analyzed"] == 12
    assert report["chronological_robustness"]["halves"]["direction_matches_full_sample"] is True
    assert report["trigger_sensitivity"]["20k"]["direction_matches_full_sample"] is True
    assert report["trigger_sensitivity"]["15k"]["direction_matches_full_sample"] is True
    assert report["outlier_sensitivity"]["exclude_1m_plus"]["direction_matches_full_sample"] is False
    assert report["flow_interpretation"]["refined_pattern"] in {
        "low_total_flow_with_high_fdv_efficiency",
        "low_total_flow_low_churn_thin_squeeze_proxy",
    }
    assert "no_walk_forward_validation" in report["methodology_flags"]


def test_robustness_report_is_data_limited_for_tiny_sample(tmp_path: Path) -> None:
    rows = [_feature_row("mint-a", 1_700_000_000, "reached_20k_but_never_50k", 10, 5, 4, "creator-a")]
    report = build_t011_raw_flow_robustness_report(
        t011_summary_path=_write_json(tmp_path / "summary.json", {"final_classification": "descriptive_signal_present"}),
        trigger_20k_rows_path=_write_csv(tmp_path / "rows.csv", rows),
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", []),
    )

    assert report["robustness_classification"] == "data_limited"
    assert report["chronological_robustness"]["halves"]["available"] is False
