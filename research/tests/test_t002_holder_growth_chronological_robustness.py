import json
from pathlib import Path

from research.mtp_research.validation.t002_holder_growth_chronological_robustness import (
    build_t002_chronological_robustness_report,
    write_t002_chronological_robustness_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "block_time": launch_ts,
        "launch_regime": "strict",
    }


def _snapshot(mint: str, age: int, holder_count: int, value: float, confidence: str = "medium") -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "active_wallets": holder_count,
        "unique_actors": holder_count,
        "buy_count": holder_count,
        "sell_count": 0,
        "tx_count": holder_count,
        "liquidity_proxy": 1.0,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "metadata_json": {"event_count": holder_count},
    }


def _holder_state(mint: str, age: int, holder_count: int, confidence: str = "medium") -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "snapshot_age_seconds": age,
        "holder_count": holder_count,
        "top_holder_share": 0.2,
        "top_10_holder_share": 0.6,
        "creator_holder_share": 0.0,
        "holder_snapshot_confidence": confidence,
        "holder_snapshot_state": "observed_holder_values",
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
    }


def _outcome(mint: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "proxy_threshold_outcomes_usable": True,
    }


def _paths(tmp_path: Path, launch_count: int = 12) -> dict:
    candidates = []
    snapshots = []
    holder_state = []
    outcomes = []
    for index in range(launch_count):
        mint = f"mint-{index:02d}"
        launch_ts = 1_700_000_000 + index * 3600
        candidates.append(_candidate(mint, launch_ts))
        growth = index % 6
        values = {
            30: 1000,
            180: 1000 + growth * 20,
            600: 1000 + growth * 30,
            1800: 1000 + growth * 50,
            7200: 1000 + growth * 80,
        }
        for age, value in values.items():
            snapshots.append(_snapshot(mint, age, holder_count=1 + growth, value=value))
        for age, holder_count in [(30, 1), (180, 1 + growth), (600, 2 + growth), (1800, 3 + growth)]:
            confidence = "insufficient_prior_state" if index == 0 and age == 180 else "medium"
            holder_state.append(_holder_state(mint, age, holder_count, confidence=confidence))
        outcomes.append(_outcome(mint))
    return {
        "candidates_path": _write_jsonl(tmp_path / "candidates.jsonl", candidates),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "holder_state_snapshots_path": _write_jsonl(tmp_path / "holder_state.jsonl", holder_state),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }


def test_chronological_robustness_builds_splits_and_allowed_classification(tmp_path: Path) -> None:
    report = build_t002_chronological_robustness_report(**_paths(tmp_path), bucket_count=5)

    assert report["thesis_id"] == "T002"
    assert report["original_t002_v2_classification"] in {"weak_signal", "no_signal", "data_limited", "descriptive_signal_present"}
    assert report["robustness_classification"] in {
        "stable_weak_signal",
        "unstable_weak_signal",
        "no_robust_signal",
        "data_limited",
    }
    assert report["sample_counts"]["launch_count"] == 12
    assert report["chronological_splits"]["halves"]["first_half"]["launch_count"] == 6
    assert report["chronological_splits"]["halves"]["second_half"]["launch_count"] == 6
    assert [bucket["launch_count"] for bucket in report["chronological_splits"]["thirds"].values()] == [4, 4, 4]
    assert "no_future_leakage" in report["methodology_flags"]
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert "no_walk_forward_validation" in report["methodology_flags"]


def test_outlier_and_holder_confidence_sensitivity_are_reported(tmp_path: Path) -> None:
    report = build_t002_chronological_robustness_report(**_paths(tmp_path, launch_count=20), bucket_count=5)

    assert set(report["outlier_sensitivity"]) == {
        "exclude_top_1pct_fdv_proxy_runups",
        "exclude_top_5pct_fdv_proxy_runups",
        "exclude_extreme_drawdowns",
    }
    assert report["outlier_sensitivity"]["exclude_top_1pct_fdv_proxy_runups"]["launch_count"] < 20
    assert report["concentration_sensitivity"]["insufficient_prior_state_launches"]["launch_count"] == 1
    assert report["concentration_sensitivity"]["holder_state_confidence_counts"]["medium"] > 0


def test_outputs_are_deterministic_and_status_is_written(tmp_path: Path) -> None:
    paths = _paths(tmp_path, launch_count=15)
    first = build_t002_chronological_robustness_report(**paths, bucket_count=5)
    second = build_t002_chronological_robustness_report(**paths, bucket_count=5)
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T002_ROBUSTNESS.md"

    written = write_t002_chronological_robustness_outputs(first, output_dir=output_dir, status_path=status_path)

    assert first == second
    assert written["json_summary_path"].exists()
    assert written["markdown_summary_path"].exists()
    status_text = status_path.read_text(encoding="utf-8")
    assert "No thesis promotion was performed." in status_text
    assert "Robustness Classification" in status_text
