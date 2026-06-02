import json
from pathlib import Path

from research.mtp_research.validation.entity_coordination_proxy_thesis import (
    build_t007_entity_coordination_report,
    write_t007_report_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int = 1000) -> dict:
    return {"launch_id": f"launch-{mint}", "token_mint": mint, "launch_ts": launch_ts}


def _snapshot(mint: str, age: int, value: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_age_seconds": age,
        "launch_ts": 1000,
        "snapshot_ts": 1000 + age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "liquidity_proxy": 1.0,
    }


def _outcome(mint: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
        "true_market_cap_available": False,
    }


def _entity_proxy(mint: str, value: float | None, confidence: str = "medium") -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "creator": f"creator-{mint}",
        "creator_linked_share_proxy": value,
        "repeated_actor_overlap_proxy": value if value is not None else 0,
        "repeated_buyer_overlap_proxy": value if value is not None else 0,
        "synchronized_participation_proxy": value,
        "circularity_proxy": value if value is not None else 0,
        "churn_proxy": value,
        "proxy_confidence": confidence,
        "proxy_missing_reason": None if value is not None else "creator_linked_share_proxy_unavailable",
    }


def test_t007_builds_proxy_reports_and_does_not_use_blocked_labels(tmp_path: Path) -> None:
    candidates = [_candidate("mint-a"), _candidate("mint-b"), _candidate("mint-c")]
    snapshots = [
        _snapshot("mint-a", 30, 1000),
        _snapshot("mint-a", 7200, 1200),
        _snapshot("mint-b", 30, 1000),
        _snapshot("mint-b", 7200, 900),
        _snapshot("mint-c", 30, 1000),
        _snapshot("mint-c", 7200, 1300),
    ]
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "candidates.jsonl", candidates),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(tmp_path / "outcomes.jsonl", [_outcome("mint-a"), _outcome("mint-b"), _outcome("mint-c")]),
        "entity_proxy_path": _write_jsonl(
            tmp_path / "entity_proxy.jsonl",
            [_entity_proxy("mint-a", 1.0), _entity_proxy("mint-b", 2.0), _entity_proxy("mint-c", None, confidence="low")],
        ),
    }

    report = build_t007_entity_coordination_report(**paths, bucket_count=2)

    assert report["thesis_id"] == "T007"
    assert report["sample_counts"]["launch_count"] == 3
    assert report["proxy_coverage"]["creator_linked_share_proxy"]["available_count"] == 2
    assert report["proxy_coverage"]["repeated_actor_overlap_proxy"]["available_count"] == 3
    assert report["feature_reports"]["repeated_actor_overlap_proxy"]["bucket_count"] == 2
    assert report["prior_cycle_comparison"]["T005"] == "weak_signal_baseline_control"
    assert report["final_classification"] in {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}
    serialized = json.dumps(report).lower()
    assert "insider" not in serialized
    assert "wash trading" not in serialized
    assert "no_future_leakage" in report["methodology_flags"]
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_t007_reports_robustness_views_and_writes_outputs(tmp_path: Path) -> None:
    candidates = []
    snapshots = []
    outcomes = []
    proxies = []
    for index in range(12):
        mint = f"mint-{index}"
        candidates.append(_candidate(mint, launch_ts=1000 + index))
        snapshots.extend([_snapshot(mint, 30, 1000), _snapshot(mint, 7200, 1000 + index * 10)])
        outcomes.append(_outcome(mint))
        proxies.append(_entity_proxy(mint, float(index), confidence="medium"))
    report = build_t007_entity_coordination_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        snapshots_path=_write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        outcomes_path=_write_jsonl(tmp_path / "outcomes.jsonl", outcomes),
        entity_proxy_path=_write_jsonl(tmp_path / "entity_proxy.jsonl", proxies),
        bucket_count=5,
    )
    paths = write_t007_report_outputs(report, output_dir=tmp_path / "reports", status_path=tmp_path / "T007_STATUS.md")

    assert report["sensitivity_checks"]["chronological_halves"]["first_half"]["launch_count"] == 6
    assert report["sensitivity_checks"]["chronological_halves"]["second_half"]["launch_count"] == 6
    assert "exclude_top_1pct_fdv_proxy_runups" in report["sensitivity_checks"]
    assert paths["json_summary_path"].exists()
    assert paths["markdown_summary_path"].exists()
    status_text = paths["status_path"].read_text(encoding="utf-8")
    assert "No thesis promotion was performed." in status_text
    assert "True market-cap claims remain blocked" in status_text
