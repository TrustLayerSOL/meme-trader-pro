import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.cross_sample_pattern_synthesis import (
    run_cross_sample_pattern_synthesis,
    snapshot_live_v2_data,
)


def test_snapshot_live_v2_data_copies_without_mutating_live_files(tmp_path: Path) -> None:
    live = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    live.mkdir(parents=True)
    births = live / "births.jsonl"
    births.write_text('{"mint":"mint-a","sample_label":"official_lifecycle_watch_v2"}\n', encoding="utf-8")

    manifest = snapshot_live_v2_data(tmp_path, timestamp="20260605T000000Z", collector_left_running=True)

    snapshot_root = Path(manifest["snapshot_root"])
    assert manifest["collector_left_running"] is True
    assert manifest["row_counts"]["births.jsonl"] == 1
    assert (snapshot_root / "births.jsonl").read_text(encoding="utf-8") == births.read_text(encoding="utf-8")
    assert births.read_text(encoding="utf-8") == '{"mint":"mint-a","sample_label":"official_lifecycle_watch_v2"}\n'
    assert (snapshot_root / "snapshot_manifest.json").exists()
    assert (snapshot_root / "snapshot_manifest.md").exists()


def test_cross_sample_synthesis_writes_inventory_dataset_and_reports(tmp_path: Path) -> None:
    _write_live_v2_sample(tmp_path)
    _write_historical_sample(tmp_path)
    _write_quarantined_sample(tmp_path)

    report = run_cross_sample_pattern_synthesis(tmp_path, timestamp="20260605T000000Z", collector_left_running=True)

    report_root = Path(report["report_root"])
    snapshot_root = Path(report["snapshot"]["snapshot_root"])
    assert snapshot_root.exists()
    assert report["guardrails"]["collector_left_running"] is True
    assert report["guardrails"]["no_live_trading"] is True
    assert report["guardrails"]["no_enabled_paper_trading"] is True
    assert report["guardrails"]["no_validation"] is True
    assert report["summary"]["mints_analyzed"] >= 4
    assert report["summary"]["datasets_combined"] >= 3
    assert report["recommendation"]["recommendation_id"] in {"A", "C", "D", "E"}

    inventory = pd.read_csv(report_root / "source_inventory.csv")
    assert {"source_dataset", "source_class", "rows", "mints", "allowed_use"}.issubset(inventory.columns)
    assert set(inventory["source_class"]) >= {"official_lifecycle_v2_snapshot", "historical_enriched", "quarantined_forward"}

    rows = _read_jsonl(report_root / "cross_sample_synthesis_dataset.jsonl")
    assert (report_root / "cross_sample_synthesis_dataset.parquet").exists()
    assert rows
    assert {
        "mint",
        "source_dataset",
        "data_quality_tier",
        "actionability_tier",
        "quarantine_flag",
        "crossed_20k",
        "crossed_1m",
        "same_timestamp_20k_to_1m_jump",
        "clean_milestone_sequence",
    }.issubset(rows[0])
    assert any(row["actionability_tier"] == "actionable_crossed_20k" for row in rows)
    assert any(row["quarantine_flag"] is True for row in rows)

    for filename in [
        "metadata_social_pattern_audit.csv",
        "high_runner_pattern_comparison.csv",
        "fall_bounce_vs_die_analysis.csv",
        "candidate_buy_sell_framework.csv",
        "cross_sample_pattern_synthesis_summary.json",
        "cross_sample_pattern_synthesis_summary.md",
    ]:
        assert (report_root / filename).exists()

    status = tmp_path / "theses" / "CROSS_SAMPLE_PATTERN_SYNTHESIS_STATUS.md"
    assert status.exists()
    assert "No live trading" in status.read_text(encoding="utf-8")


def _write_live_v2_sample(root: Path) -> None:
    live = root / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    live.mkdir(parents=True)
    _write_jsonl(
        live / "births.jsonl",
        [
            {
                "mint": "mint-runner",
                "sample_label": "official_lifecycle_watch_v2",
                "creator": "creator-a",
                "create_time": 100.0,
                "first_followup_attempt_time": 101.0,
                "first_fdv_path_time": 102.0,
                "fdv_path_before_10k": True,
                "fdv_path_before_15k": True,
                "fdv_path_before_20k": True,
                "official_accepted_birth": True,
            },
            {
                "mint": "mint-stall",
                "sample_label": "official_lifecycle_watch_v2",
                "creator": "creator-b",
                "create_time": 100.0,
                "first_followup_attempt_time": 101.0,
                "first_fdv_path_time": 110.0,
                "fdv_path_before_10k": False,
                "fdv_path_before_20k": False,
                "official_accepted_birth": True,
            },
        ],
    )
    _write_jsonl(
        live / "followup_paths.jsonl",
        [
            {
                "mint": "mint-runner",
                "sample_label": "official_lifecycle_watch_v2",
                "timestamp": 102.0,
                "fdv_proxy": 9_000,
                "crossed_10k": False,
                "crossed_20k": False,
                "event_count": 2,
                "buy_count": 2,
                "sell_count": 0,
                "active_wallet_count": 2,
                "fdv_per_event": 4_500,
                "fdv_per_buy": 4_500,
                "fdv_per_active_wallet": 4_500,
            },
            {
                "mint": "mint-runner",
                "sample_label": "official_lifecycle_watch_v2",
                "timestamp": 104.0,
                "fdv_proxy": 22_000,
                "crossed_10k": True,
                "crossed_15k": True,
                "crossed_20k": True,
                "event_count": 4,
                "buy_count": 4,
                "sell_count": 0,
                "active_wallet_count": 4,
                "fdv_per_event": 5_500,
                "fdv_per_buy": 5_500,
                "fdv_per_active_wallet": 5_500,
            },
            {
                "mint": "mint-runner",
                "sample_label": "official_lifecycle_watch_v2",
                "timestamp": 120.0,
                "fdv_proxy": 1_200_000,
                "crossed_10k": True,
                "crossed_20k": True,
                "crossed_50k": True,
                "crossed_100k": True,
                "crossed_500k": True,
                "crossed_1m": True,
            },
            {
                "mint": "mint-stall",
                "sample_label": "official_lifecycle_watch_v2",
                "timestamp": 110.0,
                "fdv_proxy": 35_000,
                "crossed_10k": True,
                "crossed_20k": True,
            },
        ],
    )
    _write_jsonl(
        live / "metadata.jsonl",
        [
            {
                "mint": "mint-runner",
                "token_name": "Runner",
                "token_symbol": "RUN",
                "website_url": "https://example.com",
                "twitter_x_url": "https://x.com/example",
                "metadata_observed_at": 103.0,
            },
            {"mint": "mint-stall", "token_name": "Stall", "token_symbol": "STL"},
        ],
    )
    _write_jsonl(live / "drawdowns.jsonl", [{"mint": "mint-stall", "timestamp": 112.0, "drawdown_pct": 75.0}])
    (live / "lifecycle_state.json").write_text(
        json.dumps(
            {
                "mints": {
                    "mint-runner": {"state": "matured_reached_1m", "crossed_levels": ["10k", "20k", "1m"]},
                    "mint-stall": {"state": "matured_terminal_collapse", "crossed_levels": ["10k", "20k"]},
                }
            }
        ),
        encoding="utf-8",
    )
    for name in [
        "provisional_births.jsonl",
        "stale_births.jsonl",
        "hydration_results.jsonl",
        "events.jsonl",
        "lifecycle_transitions.jsonl",
        "paper_shadow_labels.jsonl",
        "paper_shadow_exit_labels.jsonl",
    ]:
        (live / name).write_text("", encoding="utf-8")


def _write_historical_sample(root: Path) -> None:
    hist = root / "data" / "backtests" / "structural_enrichment" / "full_campaign"
    hist.mkdir(parents=True)
    _write_jsonl(
        hist / "master_enriched_runner_fingerprint.jsonl",
        [
            {
                "mint": "hist-runner",
                "crossed_20k": True,
                "crossed_100k": True,
                "crossed_500k": True,
                "crossed_1m": False,
                "fdv_per_event_at_20k": 7_000,
                "social_link_count": 2,
            }
        ],
    )


def _write_quarantined_sample(root: Path) -> None:
    q = root / "data" / "forward_observation" / "quarantined" / "old_forward"
    q.mkdir(parents=True)
    _write_jsonl(q / "births.jsonl", [{"mint": "q-mint", "fdv_path_before_20k": True}])
    _write_jsonl(q / "followup_paths.jsonl", [{"mint": "q-mint", "fdv_proxy": 55_000, "crossed_20k": True, "crossed_50k": True}])


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
