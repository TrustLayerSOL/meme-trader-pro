from pathlib import Path

import pandas as pd

from research.mtp_research.validation.efficient_mover_drawdown_recovery_report import (
    REPORT_ID,
    build_efficient_mover_drawdown_recovery_report,
    classify_drawdown_event,
    detect_drawdown_events,
    normalize_path_snapshots,
    trailing_stop_30pct_diagnostic,
)


def _master(path: Path) -> Path:
    rows = []
    for idx, (launch_id, tier) in enumerate(
        [
            ("recover", "reached_1m_plus"),
            ("terminal", "reached_500k_but_never_1m"),
            ("limited", "reached_500k_but_never_1m"),
        ]
    ):
        rows.append(
            {
                "launch_id": launch_id,
                "token_mint": f"mint-{launch_id}",
                "creator": f"creator-{idx}",
                "launch_date": f"2026-01-0{idx + 1}",
                "milestone_tier": tier,
                "fdv_per_event_at_20k": 7000,
                "fdv_per_buy_at_20k": 9000,
                "fdv_per_active_wallet_at_20k": 4500,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 2,
                "active_wallets_at_20k": 2,
                "creator_net_flow_sol_before_20k": 0.1,
                "synthetic_activity_proxy": 0.1 * idx,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _snapshots(path: Path) -> Path:
    rows = []

    def add(launch_id: str, values: list[tuple[int, float, int, int, int, int]]) -> None:
        for ts, fdv, events, buys, sells, wallets in values:
            rows.append(
                {
                    "launch_id": launch_id,
                    "token_mint": f"mint-{launch_id}",
                    "snapshot_ts": ts,
                    "launch_age_seconds": ts - 1000,
                    "valuation_proxy_usd": fdv,
                    "tx_count": events,
                    "buy_count": buys,
                    "sell_count": sells,
                    "active_wallets": wallets,
                    "liquidity_proxy": 1.0,
                }
            )

    add("recover", [(1000, 20_000, 2, 2, 0, 2), (1030, 100_000, 4, 4, 0, 3), (1060, 65_000, 6, 4, 2, 3), (1090, 105_000, 8, 6, 2, 4)])
    add("terminal", [(1000, 20_000, 2, 2, 0, 2), (1030, 100_000, 4, 4, 0, 3), (1060, 65_000, 6, 4, 2, 3), (1360, 50_000, 8, 4, 4, 2)])
    add("limited", [(1000, 20_000, 2, 2, 0, 2), (1030, 100_000, 4, 4, 0, 3), (1060, 65_000, 6, 4, 2, 3)])
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_json(path, orient="records", lines=True)
    return path


def test_detect_drawdown_events_tracks_local_highs_and_fixed_levels(tmp_path: Path) -> None:
    snapshots = normalize_path_snapshots(pd.read_json(_snapshots(tmp_path / "snapshots.jsonl"), lines=True))
    recover_path = snapshots[snapshots["launch_id"] == "recover"]
    events = detect_drawdown_events(recover_path)

    event_30 = next(event for event in events if event["drawdown_level"] == "30pct")

    assert event_30["local_high_fdv"] == 100_000
    assert event_30["drawdown_fdv"] == 65_000
    assert round(event_30["drawdown_pct"], 2) == 35.0
    assert event_30["time_from_local_high_to_drawdown"] == 30


def test_recovery_terminal_and_data_limited_classifications(tmp_path: Path) -> None:
    snapshots = normalize_path_snapshots(pd.read_json(_snapshots(tmp_path / "snapshots.jsonl"), lines=True))
    recover_event = next(event for event in detect_drawdown_events(snapshots[snapshots["launch_id"] == "recover"]) if event["drawdown_level"] == "30pct")
    terminal_event = next(event for event in detect_drawdown_events(snapshots[snapshots["launch_id"] == "terminal"]) if event["drawdown_level"] == "30pct")
    limited_event = next(event for event in detect_drawdown_events(snapshots[snapshots["launch_id"] == "limited"]) if event["drawdown_level"] == "30pct")

    assert classify_drawdown_event(recover_event, snapshots[snapshots["launch_id"] == "recover"])["drawdown_classification"] == "recoverable_drawdown_proxy"
    assert classify_drawdown_event(terminal_event, snapshots[snapshots["launch_id"] == "terminal"])["drawdown_classification"] == "terminal_drawdown_proxy"
    assert classify_drawdown_event(limited_event, snapshots[snapshots["launch_id"] == "limited"])["drawdown_classification"] == "data_limited_drawdown"


def test_trailing_stop_30pct_diagnostic_counts_recoverable_and_terminal() -> None:
    rows = [
        {"drawdown_level": "30pct", "drawdown_classification": "recoverable_drawdown_proxy", "reached_higher_milestone_after_drawdown": True},
        {"drawdown_level": "30pct", "drawdown_classification": "terminal_drawdown_proxy", "reached_higher_milestone_after_drawdown": False},
        {"drawdown_level": "30pct", "drawdown_classification": "data_limited_drawdown", "reached_higher_milestone_after_drawdown": False},
    ]

    report = trailing_stop_30pct_diagnostic(rows)

    assert report["drawdown_30pct_events"] == 3
    assert report["recoverable_count"] == 1
    assert report["terminal_count"] == 1
    assert report["data_limited_count"] == 1
    assert report["would_have_exited_too_early_count"] == 1


def test_build_report_outputs_tables_and_guardrails(tmp_path: Path) -> None:
    report, paths = build_efficient_mover_drawdown_recovery_report(
        master_path=_master(tmp_path / "master.parquet"),
        snapshots_path=_snapshots(tmp_path / "snapshots.jsonl"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["efficient_mover_universe"]["rows"] == 3
    assert report["drawdown_event_counts_by_level"]["30pct"] >= 3
    assert report["trailing_stop_30pct_diagnostic"]["drawdown_30pct_events"] >= 3
    assert paths["summary_json_path"].exists()
    assert paths["drawdown_events_path"].exists()
    assert paths["recoverable_vs_terminal_features_path"].exists()
    assert paths["trailing_stop_30pct_diagnostic_path"].exists()
    assert paths["exit_side_candidate_features_path"].exists()
    assert paths["status_path"].exists()
    text = str(report).lower() + paths["status_path"].read_text(encoding="utf-8").lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        assert blocked not in text
    assert "no_threshold_optimization" in report["methodology_flags"]
