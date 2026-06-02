import json
from pathlib import Path

from research.mtp_research.validation.buy_sell_flow_baseline_thesis import (
    build_t005_buy_sell_flow_baseline_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, age: int, buys: int, sells: int, value: float, active: int = 2) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "buy_count": buys,
        "sell_count": sells,
        "tx_count": buys + sells,
        "active_wallets": active,
        "unique_actors": active,
        "liquidity_proxy": 2.0,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "price_usd_available": True,
        "bonding_curve_liquidity_proxy_available": True,
        "metadata_json": {"event_count": buys + sells},
    }


def _outcome(mint: str, price: bool = True, liquidity: bool = True) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": price,
        "has_liquidity_proxy_at_120m": liquidity,
        "true_market_cap_available": False,
    }


def test_builds_flow_features_and_handles_zero_denominators(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 4, 0, 1000, active=2),
        _snapshot("mint-a", 180, 8, 2, 1300, active=4),
        _snapshot("mint-a", 600, 10, 5, 1200, active=5),
        _snapshot("mint-a", 1800, 15, 5, 1500, active=5),
    ]
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t005_buy_sell_flow_baseline_report(**paths)
    row = report["launch_rows"][0]

    assert row["features"]["buy_count_30s"] == 4
    assert row["features"]["sell_count_30s"] == 0
    assert row["features"]["buy_sell_count_ratio_30s"] is None
    assert row["features"]["net_buy_count_3m"] == 6
    assert row["features"]["buy_count_growth_30s_to_3m"] == 4
    assert row["features"]["sell_count_growth_3m_to_10m"] == 3
    assert row["features"]["buys_per_active_wallet_30m"] == 3
    assert row["features"]["events_per_unique_actor_30m"] == 4
    assert row["features"]["confidence_weighted_flow_30m"] == 10
    assert report["feature_semantics"]["buy_count"] == "cumulative observed buy count at launch-relative snapshot age"


def test_feature_audit_reports_available_and_missing_fields(tmp_path: Path) -> None:
    paths = {
        "snapshots_path": _write_jsonl(
            tmp_path / "snapshots.jsonl",
            [
                _snapshot("mint-a", 30, 1, 0, 1000),
                {"token_mint": "mint-b", "launch_id": "launch-mint-b", "launch_age_seconds": 30},
            ],
        ),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a"), _outcome("mint-b", False, False)]),
    }

    report = build_t005_buy_sell_flow_baseline_report(**paths)

    assert report["field_coverage_audit"]["buy_count"]["available_rows"] == 1
    assert report["field_coverage_audit"]["sell_count"]["missing_rows"] == 1
    assert report["field_coverage_audit"]["FDV-proxy runup"]["coverage_pct"] == 50.0
    assert report["outcome_coverage"]["price_available_120m"] == 1
    assert "true_market_cap_claims_blocked" in report["warning_flags"]


def test_outputs_are_deterministic_and_classification_is_allowed(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    for index in range(10):
        mint = f"mint-{index}"
        snapshots.extend(
            [
                _snapshot(mint, 30, 1 + index, index % 3, 1000),
                _snapshot(mint, 180, 2 + index, index % 3, 1000 + index),
                _snapshot(mint, 600, 3 + index, index % 3, 1000 + index),
                _snapshot(mint, 1800, 4 + index, index % 3, 1000 + index),
            ]
        )
        outcomes.append(_outcome(mint))
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t005_buy_sell_flow_baseline_report(**paths)
    second = build_t005_buy_sell_flow_baseline_report(**paths)

    assert first["feature_reports"] == second["feature_reports"]
    assert first["prior_cycle_comparison"]["T002"] == "weak_signal"
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_future_leakage" in first["methodology_flags"]
    assert "no_threshold_optimization" in first["methodology_flags"]
