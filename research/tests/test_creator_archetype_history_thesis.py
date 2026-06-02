import json
from pathlib import Path

from research.mtp_research.validation.creator_archetype_history_thesis import (
    build_t003_creator_archetype_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int, creator: str | None) -> dict:
    metadata = {"creator_deployer": creator} if creator else {}
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "mint": mint,
        "launch_ts": launch_ts,
        "block_time": launch_ts,
        "launch_regime": "mon_tue_wed_0600_1200_pt",
        "metadata_json": metadata,
    }


def _snapshot(mint: str, age: int, value: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
    }


def _outcome(mint: str, price: bool = True, liquidity: bool = True) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": price,
        "has_liquidity_proxy_at_120m": liquidity,
        "proxy_threshold_outcomes_usable": True,
    }


def test_creator_history_features_are_prior_only_and_cohorted(tmp_path: Path) -> None:
    candidates = [
        _candidate("mint-a", 1_000, "creator-1"),
        _candidate("mint-b", 2_000, "creator-1"),
        _candidate("mint-c", 3_000, "creator-2"),
    ]
    snapshots = [
        _snapshot("mint-a", 30, 1000),
        _snapshot("mint-a", 7200, 3000),
        _snapshot("mint-b", 30, 1000),
        _snapshot("mint-b", 7200, 1500),
        _snapshot("mint-c", 30, 1000),
        _snapshot("mint-c", 7200, 500),
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", candidates),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a"), _outcome("mint-b"), _outcome("mint-c")]),
    }

    report = build_t003_creator_archetype_report(**paths)
    rows = {row["token_mint"]: row for row in report["launch_rows"]}

    assert rows["mint-a"]["features"]["creator_prior_launch_count"] == 0
    assert rows["mint-a"]["features"]["creator_is_repeat_before_launch"] is False
    assert rows["mint-a"]["creator_cohort"] == "A_0_prior_launches"
    assert rows["mint-b"]["features"]["creator_prior_launch_count"] == 1
    assert rows["mint-b"]["features"]["creator_is_repeat_before_launch"] is True
    assert rows["mint-b"]["creator_cohort"] == "B_1_prior_launch"
    assert rows["mint-b"]["features"]["creator_prior_median_fdv_proxy_runup"] == 2.0
    assert rows["mint-b"]["features"]["time_since_creator_previous_launch"] == 1000
    assert rows["mint-c"]["features"]["creator_prior_launch_count"] == 0
    assert report["creator_counts"]["creator_count"] == 2
    assert report["creator_counts"]["repeat_creator_count"] == 1


def test_feature_and_outcome_coverage_are_reported(tmp_path: Path) -> None:
    paths = {
        "candidates_path": _write_jsonl(
            tmp_path / "launches.jsonl",
            [_candidate("mint-a", 1_000, "creator-1"), _candidate("mint-b", 2_000, None)],
        ),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", [_snapshot("mint-a", 30, 1000)]),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a")]),
    }

    report = build_t003_creator_archetype_report(**paths)

    assert report["field_coverage_audit"]["creator"]["available_rows"] == 1
    assert report["field_coverage_audit"]["creator"]["missing_rows"] == 1
    assert report["field_coverage_audit"]["FDV-proxy runup"]["coverage_pct"] == 50.0
    assert report["outcome_coverage"]["fdv_proxy_runup_available"] == 1
    assert "creator_missing" in report["warning_flags"]


def test_report_is_deterministic_and_classification_is_allowed(tmp_path: Path) -> None:
    candidates = []
    snapshots = []
    outcomes = []
    for index in range(12):
        mint = f"mint-{index}"
        creator = f"creator-{index % 3}"
        candidates.append(_candidate(mint, 1_000 + index, creator))
        snapshots.extend([_snapshot(mint, 30, 1000), _snapshot(mint, 7200, 1000 + (index * 10))])
        outcomes.append(_outcome(mint))
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", candidates),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    }

    first = build_t003_creator_archetype_report(**paths)
    second = build_t003_creator_archetype_report(**paths)

    assert first["feature_reports"] == second["feature_reports"]
    assert first["creator_cohort_report"] == second["creator_cohort_report"]
    assert first["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }
    assert "no_future_leakage" in first["methodology_flags"]
    assert "no_threshold_optimization" in first["methodology_flags"]
