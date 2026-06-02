import json
from pathlib import Path

from research.mtp_research.validation.combined_aligned_p0_fingerprint_report import (
    build_combined_aligned_p0_fingerprint_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _row(launch_id: str, tier: str, run: str, all_three: bool = True, creator: str = "creator-a") -> dict:
    return {
        "launch_id": launch_id,
        "mint": f"mint-{launch_id}",
        "creator": creator,
        "launch_ts": 1_700_000_000,
        "launch_time_utc": "2023-11-14T22:13:20+00:00",
        "launch_date": "2023-11-14",
        "milestone_tier": tier,
        "early_buyer_wallet_count": 4,
        "early_buyer_with_prior_history_count": 3,
        "top_holder_share_proxy": 0.4 if run != "original" else 0.9,
        "top_10_holder_share_proxy": 0.8,
        "top_holder_replay_confidence": "medium",
        "is_confirmed_full_chain_snapshot": False,
        "candidate_funder": "funder-a",
        "candidate_funder_confidence": "medium",
        "shared_funding_proxy": run != "original",
        "time_linked_funding_proxy": run != "original",
        "has_early_buyer_wallet_history": True,
        "has_top_holder_replay": True,
        "has_creator_funder_graph": all_three,
        "has_all_three_p0_layers": all_three,
    }


def test_combined_report_resolves_duplicates_and_tags_samples(tmp_path: Path) -> None:
    original = _write_jsonl(
        tmp_path / "original.jsonl",
        [
            _row("a", "reached_20k_but_never_50k", "original", all_three=False, creator=""),
            _row("b", "reached_1m_plus", "original"),
        ],
    )
    balanced = _write_jsonl(
        tmp_path / "balanced.jsonl",
        [
            _row("a", "reached_20k_but_never_50k", "balanced"),
            _row("c", "reached_500k_but_never_1m", "balanced"),
        ],
    )
    leftover = _write_jsonl(tmp_path / "leftover.jsonl", [_row("d", "reached_50k_but_never_100k", "leftover")])

    report, paths = build_combined_aligned_p0_fingerprint_report(
        original_structural_path=original,
        balanced_structural_path=balanced,
        remaining_structural_path=leftover,
        output_dir=tmp_path / "reports",
        dataset_parquet_path=tmp_path / "combined.parquet",
        dataset_jsonl_path=tmp_path / "combined.jsonl",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["coverage_audit"]["total_unique_launches"] == 4
    assert report["coverage_audit"]["duplicate_rows_resolved"] == 1
    assert report["coverage_audit"]["balanced_sample_rows"] == 3
    assert report["coverage_audit"]["leftover_sample_rows"] == 1
    assert report["coverage_audit"]["all_three_p0_launches"] == 4
    rows = [json.loads(line) for line in paths["dataset_jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_id = {row["launch_id"]: row for row in rows}
    assert by_id["a"]["source_run"] == "duplicate_resolved"
    assert by_id["a"]["is_balanced_sample"] is True
    assert by_id["d"]["is_leftover_sample"] is True
    assert by_id["d"]["is_date_concentrated_sample"] is True
    assert paths["coverage_audit_path"].exists()


def test_combined_report_outputs_fingerprints_and_guardrails(tmp_path: Path) -> None:
    original = _write_jsonl(tmp_path / "original.jsonl", [_row("a", "reached_20k_but_never_50k", "original")])
    balanced = _write_jsonl(tmp_path / "balanced.jsonl", [_row("b", "reached_1m_plus", "balanced")])
    leftover = _write_jsonl(tmp_path / "leftover.jsonl", [_row("c", "reached_50k_but_never_100k", "leftover")])

    report, paths = build_combined_aligned_p0_fingerprint_report(
        original_structural_path=original,
        balanced_structural_path=balanced,
        remaining_structural_path=leftover,
        output_dir=tmp_path / "reports",
        dataset_parquet_path=tmp_path / "combined.parquet",
        dataset_jsonl_path=tmp_path / "combined.jsonl",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["readiness_classification"] in {
        "combined_p0_fingerprint_ready_for_formal_thesis_selection",
        "combined_p0_fingerprint_needs_more_balanced_scale",
        "combined_p0_fingerprint_inconclusive",
    }
    assert report["candidate_fingerprints"]
    assert all("sample_support" in row for row in report["candidate_fingerprints"])
    assert paths["tier_feature_comparison_path"].exists()
    assert paths["candidate_fingerprints_path"].exists()
    assert paths["entry_vs_exit_features_path"].exists()
    forbidden = json.dumps(report).lower()
    assert "insider" not in forbidden
    assert "scammer" not in forbidden
    assert "wash trader" not in forbidden
    assert "manipulator" not in forbidden
    assert "no_trading_logic" in report["methodology_flags"]
    assert "no_validation_run" in report["methodology_flags"]


def test_combined_report_is_deterministic(tmp_path: Path) -> None:
    original = _write_jsonl(tmp_path / "original.jsonl", [_row("a", "reached_20k_but_never_50k", "original")])
    balanced = _write_jsonl(tmp_path / "balanced.jsonl", [_row("b", "reached_1m_plus", "balanced")])
    leftover = _write_jsonl(tmp_path / "leftover.jsonl", [_row("c", "reached_50k_but_never_100k", "leftover")])

    first, _ = build_combined_aligned_p0_fingerprint_report(
        original_structural_path=original,
        balanced_structural_path=balanced,
        remaining_structural_path=leftover,
        output_dir=tmp_path / "reports-a",
        dataset_parquet_path=tmp_path / "combined-a.parquet",
        dataset_jsonl_path=tmp_path / "combined-a.jsonl",
        status_path=tmp_path / "STATUS_A.md",
    )
    second, _ = build_combined_aligned_p0_fingerprint_report(
        original_structural_path=original,
        balanced_structural_path=balanced,
        remaining_structural_path=leftover,
        output_dir=tmp_path / "reports-b",
        dataset_parquet_path=tmp_path / "combined-b.parquet",
        dataset_jsonl_path=tmp_path / "combined-b.jsonl",
        status_path=tmp_path / "STATUS_B.md",
    )

    assert first["coverage_audit"] == second["coverage_audit"]
    assert first["candidate_fingerprints"] == second["candidate_fingerprints"]
