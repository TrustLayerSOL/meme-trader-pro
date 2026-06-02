import json
from pathlib import Path

from research.mtp_research.validation.repeated_buyer_runner_participation_report import (
    build_repeated_buyer_runner_participation_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, launch_ts: int, age: int, value: float, buys: int = 4, active: int = 4) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "creator": f"creator-{mint}",
        "launch_ts": launch_ts,
        "snapshot_ts": launch_ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": 1,
        "active_wallets": active,
        "tx_count": buys + 1,
        "metadata_json": {"event_count": buys + 1},
    }


def _event(mint: str, actor: str, launch_ts: int, age: int) -> dict:
    return {
        "token_mint": mint,
        "actor": actor,
        "block_time": launch_ts + age,
        "side": "accumulate",
        "event_type": "token_accumulation",
        "signature": f"sig-{mint}-{actor}-{age}",
    }


def test_report_builds_leakage_safe_prior_wallet_history(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("old-runner", 1_700_000_000, 60, 20_000),
            _snapshot("old-runner", 1_700_000_000, 120, 600_000),
            _snapshot("new-runner", 1_700_086_400, 60, 20_000),
            _snapshot("new-runner", 1_700_086_400, 120, 1_200_000),
            _snapshot("failure", 1_700_172_800, 60, 20_000),
            _snapshot("failure", 1_700_172_800, 120, 30_000),
        ],
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            _event("old-runner", "wallet-a", 1_700_000_000, 30),
            _event("new-runner", "wallet-a", 1_700_086_400, 30),
            _event("new-runner", "wallet-b", 1_700_086_400, 40),
            _event("failure", "wallet-b", 1_700_172_800, 30),
        ],
    )

    report, paths = build_repeated_buyer_runner_participation_report(
        snapshot_paths=[snapshots],
        event_paths=[events],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "REPEATED_BUYER_STATUS.md",
    )

    by_mint = {row["mint"]: row for row in report["launch_feature_rows"]}
    assert by_mint["old-runner"]["before_20k_count_early_buyers_with_prior_runner"] == 0
    assert by_mint["new-runner"]["before_20k_count_early_buyers_with_prior_500k_runner"] == 1
    assert by_mint["new-runner"]["before_20k_share_early_buyers_with_prior_runner"] == 0.5
    assert by_mint["failure"]["before_20k_count_early_buyers_with_prior_runner"] == 1
    assert paths["summary_json_path"].exists()
    assert paths["tier_comparison_path"].exists()


def test_report_builds_windows_interactions_and_guardrails(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000),
            _snapshot("mint-a", 1_700_000_000, 180, 100_000),
            _snapshot("mint-b", 1_700_086_400, 60, 20_000),
            _snapshot("mint-b", 1_700_086_400, 180, 40_000),
        ],
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            _event("mint-a", "wallet-a", 1_700_000_000, 30),
            _event("mint-a", "wallet-b", 1_700_000_000, 90),
            _event("mint-b", "wallet-a", 1_700_086_400, 30),
        ],
    )

    report, paths = build_repeated_buyer_runner_participation_report(
        snapshot_paths=[snapshots],
        event_paths=[events],
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "REPEATED_BUYER_STATUS.md",
    )

    windows = {row["window_name"] for row in report["early_buyer_window_coverage"]}
    feature_sides = {row["feature_name"]: row["entry_side_classification"] for row in report["entry_side_feature_classification"]}
    forbidden = json.dumps(report).lower()
    assert {"before_20k", "at_20k", "before_50k", "first_60s", "first_120s"} <= windows
    assert report["fdv_efficiency_interaction_summary"]
    assert feature_sides["before_20k_repeated_buyer_quality_proxy"] == "entry_side_available_before_20k"
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_trading_logic" in report["methodology_flags"]
    assert "insider" not in forbidden
    assert "manipulator" not in forbidden
    assert "wash trader" not in forbidden
    assert paths["fdv_efficiency_interaction_path"].exists()


def test_report_is_deterministic(tmp_path: Path) -> None:
    snapshots = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            _snapshot("mint-a", 1_700_000_000, 60, 20_000),
            _snapshot("mint-a", 1_700_000_000, 120, 500_000),
        ],
    )
    events = _write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "wallet-a", 1_700_000_000, 30)])

    first, _ = build_repeated_buyer_runner_participation_report(
        snapshot_paths=[snapshots],
        event_paths=[events],
        output_dir=tmp_path / "reports-a",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_repeated_buyer_runner_participation_report(
        snapshot_paths=[snapshots],
        event_paths=[events],
        output_dir=tmp_path / "reports-b",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["milestone_tier_summary"] == second["milestone_tier_summary"]
    assert first["recommended_next_action"] == second["recommended_next_action"]
