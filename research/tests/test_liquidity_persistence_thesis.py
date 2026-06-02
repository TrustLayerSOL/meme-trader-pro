import json
from pathlib import Path

import pytest

from research.mtp_research.validation.liquidity_persistence_thesis import (
    build_t004_liquidity_persistence_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, liquidity: float, value: float, active: int = 2) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "liquidity_proxy": liquidity,
        "bonding_curve_liquidity_proxy_sol": liquidity,
        "metadata_json": {"liquidity_proxy_source": "bonding_curve_post_balance", "event_count": active + 1},
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "active_wallets": active,
        "unique_actors": active,
        "tx_count": active + 1,
        "buy_count": active,
        "sell_count": 1,
    }


def _outcome(mint: str, liquidity: bool = True, price: bool = True) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": price,
        "has_liquidity_proxy_at_120m": liquidity,
        "proxy_threshold_outcomes_usable": True,
        "true_market_cap_available": False,
    }


def test_builds_liquidity_features_and_documents_proxy_semantics(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 10, 1000, active=5),
        _snapshot("mint-a", 60, 12, 1100, active=5),
        _snapshot("mint-a", 180, 20, 1400, active=10),
        _snapshot("mint-a", 600, 15, 1200, active=10),
        _snapshot("mint-a", 1800, 5, 900, active=10),
        _snapshot("mint-a", 7200, 2, 800, active=10),
    ]
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t004_liquidity_persistence_report(**paths)
    row = report["launch_rows"][0]

    assert row["features"]["liquidity_proxy_30s"] == 10
    assert row["features"]["liquidity_proxy_retention_30s_to_30m"] == 0.5
    assert row["features"]["liquidity_proxy_drop_30s_to_30m"] == 0.5
    assert row["features"]["liquidity_proxy_growth_30s_to_3m"] == 10
    assert row["features"]["liquidity_proxy_slope_30s_to_30m"] == pytest.approx(-5 / 1770)
    assert row["features"]["liquidity_per_active_wallet_30m"] == 0.5
    assert report["liquidity_proxy_semantics"]["classification"] == "proxy"
    assert "not_confirmed_dex_depth" in report["warning_flags"]


def test_feature_audit_reports_available_and_missing_fields(tmp_path: Path) -> None:
    paths = {
        "snapshots_path": _write_jsonl(
            tmp_path / "snapshots.jsonl",
            [
                _snapshot("mint-a", 30, 10, 1000),
                {"token_mint": "mint-b", "launch_id": "launch-mint-b", "launch_age_seconds": 30},
            ],
        ),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a"), _outcome("mint-b", False)]),
    }

    report = build_t004_liquidity_persistence_report(**paths)

    assert report["field_coverage_audit"]["liquidity_proxy"]["available_rows"] == 1
    assert report["field_coverage_audit"]["liquidity_proxy"]["missing_rows"] == 1
    assert report["field_coverage_audit"]["FDV-proxy runup"]["coverage_pct"] == 50.0
    assert report["outcome_coverage"]["liquidity_proxy_available_120m"] == 1


def test_outputs_are_deterministic_and_classification_is_allowed(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    for index in range(10):
        mint = f"mint-{index}"
        snapshots.extend(
            [
                _snapshot(mint, 30, 1 + index, 1000),
                _snapshot(mint, 600, 2 + index, 1000 + index),
                _snapshot(mint, 1800, 3 + index, 1000 + index),
                _snapshot(mint, 7200, 4 + index, 1000 + index),
            ]
        )
        outcomes.append(_outcome(mint))
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t004_liquidity_persistence_report(**paths)
    second = build_t004_liquidity_persistence_report(**paths)

    assert first["feature_reports"] == second["feature_reports"]
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_future_leakage" in first["methodology_flags"]
    assert "no_threshold_optimization" in first["methodology_flags"]
