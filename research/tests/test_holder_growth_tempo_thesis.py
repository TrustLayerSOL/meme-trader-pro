import json
from pathlib import Path

import pytest

from research.mtp_research.validation.holder_growth_tempo_thesis import (
    build_t002_holder_growth_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1000,
        "launch_regime": "mon_tue_wed_0600_1200_pt",
    }


def _snapshot(mint: str, age: int, active_wallets: int, buy_count: int, value: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "active_wallets": active_wallets,
        "unique_actors": active_wallets,
        "buy_count": buy_count,
        "sell_count": 1,
        "tx_count": buy_count + 1,
        "liquidity_proxy": 2.0,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "metadata_json": {"event_count": buy_count + 1},
    }


def _outcome(mint: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "proxy_threshold_outcomes_usable": True,
    }


def _holder_state(mint: str, age: int, holder_count: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "snapshot_age_seconds": age,
        "holder_count": holder_count,
        "top_holder_share": 0.5,
        "top_10_holder_share": 1.0,
        "creator_holder_share": 0.0,
        "holder_snapshot_confidence": "medium",
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
    }


def test_feature_audit_reports_available_and_missing_fields(tmp_path: Path) -> None:
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")]),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", [_snapshot("mint-a", 30, 2, 3, 1000)]),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t002_holder_growth_report(**paths)

    assert report["field_coverage_audit"]["holder_count"]["available_rows"] == 0
    assert report["field_coverage_audit"]["buy_count"]["available_rows"] == 1
    assert report["field_coverage_audit"]["unique_wallet_count"]["coverage_pct"] == 0
    assert "holder_count_unavailable" in report["warning_flags"]


def test_builds_growth_features_without_using_post_30m_snapshots(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 2, 3, 1000),
        _snapshot("mint-a", 180, 5, 7, 1100),
        _snapshot("mint-a", 600, 8, 11, 1200),
        _snapshot("mint-a", 1800, 10, 13, 1300),
        _snapshot("mint-a", 7200, 1000, 5000, 5000),
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")]),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t002_holder_growth_report(**paths)
    row = report["launch_rows"][0]

    assert row["features"]["active_wallet_growth_30s_to_3m"] == 3
    assert row["features"]["buyer_growth_3m_to_10m"] == 4
    assert row["features"]["active_wallet_growth_velocity"] == 8 / 1770
    assert row["metadata_json"]["max_feature_snapshot_age_seconds"] == 1800
    assert row["outcomes"]["fdv_proxy_runup_120m"] == 4.0


def test_missing_holder_features_are_not_fabricated(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 2, 3, 1000),
        _snapshot("mint-a", 1800, 10, 13, 1300),
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")]),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t002_holder_growth_report(**paths)
    row = report["launch_rows"][0]

    assert row["features"]["holder_growth_30s_to_3m"] is None
    assert row["feature_missing_reasons"]["holder_growth_30s_to_3m"] == "holder_count_unavailable"
    assert report["missing_value_audit"]["holder_growth_30s_to_3m"]["missing_count"] == 1


def test_holder_state_v2_merges_holder_counts_without_replacing_fdv_snapshots(tmp_path: Path) -> None:
    snapshots = [
        _snapshot("mint-a", 30, 2, 3, 1000),
        _snapshot("mint-a", 180, 5, 7, 1100),
        _snapshot("mint-a", 600, 8, 11, 1200),
        _snapshot("mint-a", 1800, 10, 13, 1300),
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", [_candidate("mint-a")]),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "holder_state_snapshots_path": _write_jsonl(
            tmp_path / "holder_state.jsonl",
            [
                _holder_state("mint-a", 30, 1),
                _holder_state("mint-a", 180, 3),
                _holder_state("mint-a", 600, 4),
                _holder_state("mint-a", 1800, 6),
            ],
        ),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t002_holder_growth_report(**paths)
    row = report["launch_rows"][0]

    assert report["field_coverage_audit"]["holder_count"]["available_rows"] == 4
    assert "holder_count_unavailable" not in report["warning_flags"]
    assert row["features"]["holder_growth_30s_to_3m"] == 2
    assert row["features"]["holder_growth_30s_to_30m"] == 5
    assert row["outcomes"]["fdv_proxy_runup_120m"] == pytest.approx(0.3)
    assert "holder_state_observed_delta_replay_not_full_chain_state" in report["methodology_flags"]


def test_outputs_are_deterministic_and_classification_is_allowed(tmp_path: Path) -> None:
    launches = []
    snapshots = []
    outcomes = []
    for i in range(10):
        mint = f"mint-{i}"
        launches.append(_candidate(mint))
        snapshots.extend(
            [
                _snapshot(mint, 30, 1 + i, 2 + i, 1000),
                _snapshot(mint, 180, 2 + i, 3 + i, 1000 + i),
                _snapshot(mint, 600, 3 + i, 4 + i, 1000 + i),
                _snapshot(mint, 1800, 4 + i, 5 + i, 1000 + i),
            ]
        )
        outcomes.append(_outcome(mint))
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", launches),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t002_holder_growth_report(**paths, bucket_count=5)
    second = build_t002_holder_growth_report(**paths, bucket_count=5)

    assert first["feature_reports"] == second["feature_reports"]
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_future_leakage" in first["methodology_flags"]
    assert "no_threshold_optimization" in first["methodology_flags"]
