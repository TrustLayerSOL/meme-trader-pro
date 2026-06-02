import json
from pathlib import Path

from research.mtp_research.validation.participation_quality_thesis import (
    build_t006_participation_quality_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(
    mint: str,
    age: int,
    *,
    buys: int,
    sells: int,
    events: int,
    active_wallets: int,
    unique_actors: int,
    liquidity_proxy: float,
    value: float,
) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "buy_count": buys,
        "sell_count": sells,
        "tx_count": events,
        "event_count": events,
        "active_wallets": active_wallets,
        "unique_actors": unique_actors,
        "liquidity_proxy": liquidity_proxy,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "price_usd_available": True,
        "metadata_json": {"event_count": events},
    }


def _outcome(mint: str, *, price: bool = True, liquidity: bool = True) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": price,
        "has_liquidity_proxy_at_120m": liquidity,
        "true_market_cap_available": False,
    }


def test_builds_participation_quality_features_and_zero_denominators(tmp_path: Path) -> None:
    snapshots = [
        _snapshot(
            "mint-a",
            30,
            buys=4,
            sells=1,
            events=5,
            active_wallets=5,
            unique_actors=4,
            liquidity_proxy=10,
            value=1000,
        ),
        _snapshot(
            "mint-a",
            180,
            buys=6,
            sells=2,
            events=8,
            active_wallets=4,
            unique_actors=4,
            liquidity_proxy=20,
            value=1300,
        ),
        _snapshot(
            "mint-a",
            300,
            buys=8,
            sells=2,
            events=10,
            active_wallets=5,
            unique_actors=5,
            liquidity_proxy=25,
            value=1250,
        ),
        _snapshot(
            "mint-a",
            600,
            buys=12,
            sells=3,
            events=15,
            active_wallets=5,
            unique_actors=5,
            liquidity_proxy=30,
            value=1400,
        ),
        _snapshot(
            "mint-a",
            1800,
            buys=18,
            sells=6,
            events=24,
            active_wallets=0,
            unique_actors=6,
            liquidity_proxy=40,
            value=1500,
        ),
    ]
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t006_participation_quality_report(**paths)
    features = report["launch_rows"][0]["features"]

    assert features["events_per_active_wallet_30s"] == 1
    assert features["events_per_unique_actor_3m"] == 2
    assert features["buys_per_active_wallet_10m"] == 2.4
    assert features["sells_per_active_wallet_30m"] is None
    assert features["active_wallets_per_event_5m"] == 0.5
    assert features["unique_actors_per_event_30m"] == 0.25
    assert features["active_wallets_per_liquidity_proxy_3m"] == 0.2
    assert features["event_intensity_per_actor_10m"] == 3
    assert report["feature_semantics"]["event_intensity_per_actor"] == (
        "event_count divided by unique_actors; this is an intensity proxy only"
    )


def test_feature_audit_reports_exact_required_field_coverage(tmp_path: Path) -> None:
    paths = {
        "snapshots_path": _write_jsonl(
            tmp_path / "snapshots.jsonl",
            [
                _snapshot(
                    "mint-a",
                    30,
                    buys=1,
                    sells=0,
                    events=1,
                    active_wallets=1,
                    unique_actors=1,
                    liquidity_proxy=2,
                    value=1000,
                ),
                {"token_mint": "mint-b", "launch_id": "launch-mint-b", "launch_age_seconds": 30},
            ],
        ),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a"), _outcome("mint-b", price=False, liquidity=False)]),
    }

    report = build_t006_participation_quality_report(**paths)

    assert report["field_coverage_audit"]["buy_count"]["available_rows"] == 1
    assert report["field_coverage_audit"]["event_count"]["missing_rows"] == 1
    assert report["field_coverage_audit"]["FDV-proxy runup"]["coverage_pct"] == 50.0
    assert report["outcome_coverage"]["price_available_120m"] == 1
    assert "true_market_cap_claims_blocked" in report["warning_flags"]


def test_outputs_are_deterministic_and_methodology_is_guarded(tmp_path: Path) -> None:
    snapshots = []
    outcomes = []
    for index in range(12):
        mint = f"mint-{index}"
        for age, value in [(30, 1000), (60, 1010), (180, 1100), (300, 1120), (600, 1200), (1800, 1300)]:
            snapshots.append(
                _snapshot(
                    mint,
                    age,
                    buys=1 + index + age // 60,
                    sells=index % 4,
                    events=2 + index + age // 60,
                    active_wallets=2 + (index % 5),
                    unique_actors=2 + (index % 4),
                    liquidity_proxy=10 + index,
                    value=value + index,
                )
            )
        outcomes.append(_outcome(mint))
    paths = {
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t006_participation_quality_report(**paths)
    second = build_t006_participation_quality_report(**paths)

    assert first["feature_reports"] == second["feature_reports"]
    assert first["prior_cycle_comparison"]["T005"] == "weak_signal"
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_future_leakage" in first["methodology_flags"]
    assert "no_threshold_optimization" in first["methodology_flags"]
    assert "threshold_tuning_absent" in first["methodology_checks"]
