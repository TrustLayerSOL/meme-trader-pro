import json
import math
from pathlib import Path

from research.mtp_research.validation.funding_lineage_thesis import build_t010_funding_lineage_report


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _funding_row(index: int, funder: str | None, sharing: int, age: int | None, confidence: float = 0.85) -> dict:
    mint = f"mint-{index}"
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "creator": f"creator-{index % 3}",
        "launch_ts": 1000 + index * 100,
        "launch_time": "1970-01-01T00:00:00+00:00",
        "candidate_funding_wallet": funder,
        "candidate_funding_signature": f"sig-{index}" if funder else None,
        "candidate_funding_time": "1970-01-01T00:00:00+00:00" if funder else None,
        "funding_age_seconds": age,
        "funding_amount_sol": float(index) if funder else None,
        "funding_amount_token": None,
        "funding_source_confidence": confidence if funder else 0.0,
        "funding_source_reason": "parsed_sol_transfer_to_creator" if funder else None,
        "funding_source_missing_reason": None if funder else "no_prior_funding_trace_found",
        "launches_sharing_funder": sharing,
        "creator_funder_reuse_count": max(0, sharing - 1),
        "common_funder_candidate_id": funder if sharing > 1 else None,
        "creator_has_prior_funding_trace": bool(funder),
    }


def _outcome(index: int, runup: float) -> dict:
    mint = f"mint-{index}"
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1000 + index * 100,
        "runups": {"max_runup_120m": runup},
        "drawdowns": {"max_drawdown_120m": -0.1},
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "true_market_cap_available": False,
    }


def test_builds_fixed_funding_buckets_and_feature_audit(tmp_path: Path) -> None:
    funding = [
        _funding_row(0, "funder-a", 1, 500),
        _funding_row(1, "funder-a", 2, 7200),
        _funding_row(2, "funder-b", 5, 25000),
        _funding_row(3, None, 0, None),
    ]
    outcomes = [_outcome(i, runup=float(i)) for i in range(4)]

    report = build_t010_funding_lineage_report(
        funding_link_path=_write_jsonl(tmp_path / "funding.jsonl", funding),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    )

    assert report["thesis_id"] == "T010"
    assert report["dataset"]["launch_count"] == 4
    assert report["feature_coverage_audit"]["candidate_funding_wallet"]["available_rows"] == 3
    assert report["bucket_counts"]["funding_source_available"] == {"available": 3, "unavailable": 1}
    assert report["bucket_counts"]["repeated_funder_flag"] == {"no_repeated_funder": 2, "repeated_funder": 2}
    assert report["bucket_counts"]["launches_sharing_funder_bucket"]["0_or_1"] == 2
    assert report["bucket_counts"]["launches_sharing_funder_bucket"]["2_to_4"] == 1
    assert report["bucket_counts"]["launches_sharing_funder_bucket"]["5_plus"] == 1
    assert "no_future_leakage" in report["methodology_flags"]
    assert report["final_classification"] in {
        "descriptive_signal_present",
        "weak_signal",
        "no_signal",
        "data_limited",
    }


def test_filters_future_funding_rows_and_preserves_warning(tmp_path: Path) -> None:
    bad = _funding_row(0, "future-funder", 2, -50)
    good = _funding_row(1, "past-funder", 2, 3600)
    report = build_t010_funding_lineage_report(
        funding_link_path=_write_jsonl(tmp_path / "funding.jsonl", [bad, good]),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(0, 10.0), _outcome(1, 1.0)]),
    )

    assert report["dataset"]["launch_count"] == 1
    assert "future_funding_rows_excluded" in report["warning_flags"]
    assert report["launch_rows"][0]["token_mint"] == "mint-1"


def test_treats_parquet_nan_funder_as_missing(tmp_path: Path) -> None:
    row = _funding_row(0, "funder-a", 1, 500)
    row["candidate_funding_wallet"] = math.nan
    row["funding_amount_sol"] = math.nan
    row["common_funder_candidate_id"] = math.nan
    report = build_t010_funding_lineage_report(
        funding_link_path=_write_jsonl(tmp_path / "funding.jsonl", [row]),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", [_outcome(0, 1.0)]),
    )

    assert report["funding_link_coverage"]["funding_source_available_count"] == 0
    assert report["bucket_counts"]["funding_source_available"] == {"unavailable": 1}


def test_reports_repeated_funder_and_prior_comparisons(tmp_path: Path) -> None:
    funding = []
    outcomes = []
    for index in range(12):
        repeated = index >= 6
        funding.append(_funding_row(index, "shared" if repeated else None, 6 if repeated else 0, 3600 if repeated else None))
        outcomes.append(_outcome(index, runup=10.0 if repeated else 1.0))

    report = build_t010_funding_lineage_report(
        funding_link_path=_write_jsonl(tmp_path / "funding.jsonl", funding),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
    )

    comparison = report["main_comparisons"]["repeated_funder_vs_no_repeated_funder"]
    assert comparison["left_group"] == "repeated_funder"
    assert comparison["left"]["sample_count"] == 6
    assert comparison["right"]["sample_count"] == 6
    assert comparison["median_runup_delta"] > 0
    assert report["prior_result_comparison"]["T009"] == "no_signal"
