import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.historical_rule_discovery import (
    build_broad_buy_side_pattern_search,
    build_broad_exit_side_pattern_search,
    build_candidate_frameworks,
    build_chronological_split,
    build_historical_rule_discovery,
    build_historical_rule_discovery_dataset,
    build_historical_source_inventory,
)


def test_historical_rule_discovery_inventory_dataset_safety_and_outputs(tmp_path: Path) -> None:
    data_root = _write_historical_lake(tmp_path)

    result = build_historical_rule_discovery(data_root=data_root, execute=True)

    report_root = Path(result["report_root"])
    inventory = pd.read_csv(report_root / "historical_source_inventory.csv")
    dataset = _read_jsonl(report_root / "historical_rule_discovery_dataset.jsonl")
    comparison = pd.read_csv(report_root / "historical_candidate_rule_comparison.csv")
    config = json.loads(
        (
            data_root
            / "data"
            / "forward_observation"
            / "official_lifecycle_watch_v2"
            / "historical_rule_paper_shadow_config.json"
        ).read_text(encoding="utf-8")
    )

    assert not inventory.empty
    assert {"path", "row_count", "mint_count", "feature_families_available", "usable_for_buy_side_discovery"}.issubset(
        inventory.columns
    )
    by_mint = {row["mint"]: row for row in dataset}
    assert by_mint["runner"]["confirmed_crossed_20k"] is True
    assert by_mint["spike"]["single_row_spike_flag"] is True
    assert by_mint["spike"]["clean_path_flag"] is False
    assert by_mint["jump"]["same_timestamp_major_jump_flag"] is True
    assert by_mint["jump"]["clean_path_flag"] is False
    assert any(row["rule_id"] == "BROAD_10K_WATCH_20K_BUY" for row in _read_csv_dicts(report_root / "candidate_buy_sell_frameworks.csv"))
    assert not comparison.empty
    assert config["use_confirmed_milestones_only"] is True
    assert config["raw_milestones_allowed"] is False
    assert config["single_row_spikes_allowed"] is False
    assert config["same_timestamp_major_jump_allowed_for_entry"] is False
    assert config["live_trading_enabled"] is False
    assert config["private_keys_allowed"] is False
    assert config["paper_trading_allowed"] is True
    assert "no_live_trading" in result["guardrails"]
    assert (report_root / "historical_rule_discovery_summary.md").exists()
    assert Path(result["status_file"]).exists()


def test_historical_rule_discovery_components_are_deterministic(tmp_path: Path) -> None:
    data_root = _write_historical_lake(tmp_path)
    source_paths = [
        data_root
        / "data"
        / "backtests"
        / "structural_enrichment"
        / "full_campaign"
        / "master_enriched_runner_fingerprint.parquet",
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "efficient_mover_drawdown_recovery"
        / "drawdown_events.csv",
    ]

    inventory = build_historical_source_inventory(data_root, source_paths=source_paths)
    dataset = build_historical_rule_discovery_dataset(data_root, source_paths=source_paths)
    split = build_chronological_split(dataset)
    buy_rows = build_broad_buy_side_pattern_search(dataset, split)
    exit_rows = build_broad_exit_side_pattern_search(dataset, split)
    framework_rows = build_candidate_frameworks()

    assert len(inventory) == 2
    assert len(dataset) == 4
    assert {row["split"] for row in dataset} <= {"discovery_train", "design_test", "holdout"}
    assert split["split_method"] in {"60_20_20_chronological", "70_30_chronological"}
    assert any(row["feature"] == "fdv_per_buy_at_20k" for row in buy_rows)
    assert any(row["feature"] == "no_reclaim_after_5m" for row in exit_rows)
    assert {"rule_id", "exit_rule_id"}.intersection(framework_rows[0].keys())


def test_historical_rule_discovery_contains_no_execution_logic() -> None:
    text = Path("research/mtp_research/validation/historical_rule_discovery.py").read_text(encoding="utf-8").lower()
    forbidden = ["sendtransaction", "signtransaction", "secretkey", "buildswaptransaction"]
    assert not any(term in text for term in forbidden)


def _write_historical_lake(root: Path) -> Path:
    full = root / "data" / "backtests" / "structural_enrichment" / "full_campaign"
    full.mkdir(parents=True)
    rows = [
        _row("runner", "2026-01-01", "reached_500k_but_never_1m", 500_000, 8_000, 12_000, 4, 0.2),
        _row("stall", "2026-01-02", "reached_20k_but_never_50k", 35_000, 2_000, 3_000, 20, 0.9),
        _row("spike", "2026-01-03", "reached_20k_but_never_50k", 36_000, 30_000, 36_000, 1, 0.5),
        _row("jump", "2026-01-04", "reached_1m_plus", 1_100_000, 25_000, 30_000, 2, 0.4),
    ]
    pd.DataFrame(rows).to_parquet(full / "master_enriched_runner_fingerprint.parquet", index=False)

    snapshot_root = root / "data" / "backtests" / "diagnostics" / "reports" / "T011_expanded_rerun"
    snapshot_root.mkdir(parents=True)
    snapshots = [
        _path("runner", 100, 9_000),
        _path("runner", 110, 22_000),
        _path("runner", 130, 24_000),
        _path("runner", 180, 520_000),
        _path("stall", 200, 12_000),
        _path("stall", 230, 22_000),
        _path("stall", 260, 24_000),
        _path("spike", 300, 2_400),
        _path("spike", 310, 36_000),
        _path("spike", 320, 2_300),
        _path("jump", 400, 1_100_000),
        _path("jump", 400, 1_120_000),
    ]
    _write_jsonl(snapshot_root / "combined_expanded_lifecycle_snapshots.jsonl", snapshots)

    drawdown = root / "data" / "backtests" / "diagnostics" / "reports" / "efficient_mover_drawdown_recovery"
    drawdown.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "token_mint": "runner",
                "drawdown_level": "30pct",
                "drawdown_pct": 30.0,
                "reclaimed_prior_high_within_5m": True,
                "failed_to_reclaim_within_5m": False,
                "failed_to_reclaim_within_10m": False,
                "reached_higher_milestone_after_drawdown": True,
                "drawdown_classification": "recoverable_dip_proxy",
            },
            {
                "token_mint": "stall",
                "drawdown_level": "30pct",
                "drawdown_pct": 70.0,
                "reclaimed_prior_high_within_5m": False,
                "failed_to_reclaim_within_5m": True,
                "failed_to_reclaim_within_10m": True,
                "reached_higher_milestone_after_drawdown": False,
                "drawdown_classification": "terminal_drawdown_proxy",
            },
        ]
    ).to_csv(drawdown / "drawdown_events.csv", index=False)
    return root


def _row(mint: str, date: str, tier: str, peak: float, fdv_event: float, fdv_buy: float, events: int, top_holder: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "creator": f"creator-{mint}",
        "launch_date": date,
        "launch_ts": pd.Timestamp(date, tz="UTC").timestamp(),
        "milestone_tier": tier,
        "peak_fdv_proxy": peak,
        "fdv_per_event_at_20k": fdv_event,
        "fdv_per_buy_at_20k": fdv_buy,
        "fdv_per_active_wallet_at_20k": fdv_buy,
        "event_count_at_20k": events,
        "buy_count_at_20k": max(1, events - 1),
        "sell_count_at_20k": 1,
        "active_wallets_at_20k": max(1, events - 2),
        "buy_sell_ratio_at_20k": max(1, events - 1),
        "top_holder_share_proxy": top_holder,
        "creator_net_flow_sol_before_20k": -0.1,
        "synthetic_activity_proxy": 0.1,
        "metadata_completeness_score": 0.5,
    }


def _path(mint: str, ts: float, fdv: float) -> dict:
    return {
        "token_mint": mint,
        "snapshot_ts": ts,
        "valuation_proxy_usd": fdv,
        "tx_count": 4,
        "buy_count": 3,
        "sell_count": 1,
        "active_wallets": 3,
        "launch_ts": 0,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_csv_dicts(path: Path) -> list[dict]:
    return pd.read_csv(path).to_dict(orient="records")
