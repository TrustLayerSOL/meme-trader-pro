import json
from pathlib import Path

from research.mtp_research.validation.t011_expanded_rerun import (
    audit_expanded_snapshots,
    build_t011_expanded_rerun_report,
    write_combined_expanded_snapshots,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, launch_ts: int, age: int, value: float, events: int, buys: int, active: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "snapshot_ts": launch_ts + age,
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


def _cohort_rows(count: int = 12) -> list[dict]:
    rows = []
    for idx in range(count):
        mint = f"mint-{idx}"
        ts = 1_700_000_000 + idx * 86_400
        winner = idx % 2 == 0
        events = 4 if winner else 18
        buys = 3 if winner else 10
        active = 3 if winner else 8
        peak = 1_000_000 if winner else 40_000
        rows.extend(
            [
                _snapshot(mint, ts, 30, 15_000, events, buys, active),
                _snapshot(mint, ts, 60, 20_000, events, buys, active),
                _snapshot(mint, ts, 120, peak, events + 1, buys + 1, active + 1),
            ]
        )
    return rows


def test_combined_expanded_snapshots_dedupes_snapshot_keys(tmp_path: Path) -> None:
    first = _write_jsonl(tmp_path / "first.jsonl", [_snapshot("mint-a", 1_700_000_000, 60, 20_000, 4, 3, 3)])
    second = _write_jsonl(
        tmp_path / "second.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000, 4, 3, 3),
            _snapshot("mint-b", 1_700_086_400, 60, 20_000, 5, 4, 4),
        ],
    )

    summary = write_combined_expanded_snapshots([first, second], tmp_path / "combined.jsonl")

    assert summary["snapshot_rows_written"] == 2
    assert summary["unique_mints"] == 2


def test_expanded_snapshot_audit_reports_trigger_coverage(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "snapshots.jsonl", _cohort_rows(4))

    audit = audit_expanded_snapshots(path)

    assert audit["total_launches"] == 4
    assert audit["trigger_counts"]["15k"] == 4
    assert audit["trigger_counts"]["20k"] == 4
    assert audit["trigger_counts"]["30k"] == 4
    assert audit["milestone_counts"]["1m"] == 2
    assert audit["forward_path_coverage"]["20k"] == 1.0


def test_expanded_rerun_writes_reports_and_keeps_guardrails(tmp_path: Path) -> None:
    snapshots = _write_jsonl(tmp_path / "snapshots.jsonl", _cohort_rows(12))

    report, paths = build_t011_expanded_rerun_report(
        snapshot_paths=[snapshots],
        output_dir=tmp_path / "reports",
    )

    assert report["review_type"] == "descriptive_rerun_stability_only"
    assert "no_validation_run" in report["methodology_flags"]
    assert "no_live_trading" in report["methodology_flags"]
    assert report["expanded_dataset_audit"]["trigger_counts"]["20k"] == 12
    assert report["old_vs_expanded_comparison"]["old_sample"]["unique_trigger_dates"] == 3
    assert paths["json_summary_path"].exists()
    assert paths["markdown_summary_path"].exists()
    assert paths["expanded_trigger_20k_feature_rows_path"].exists()
