import csv
import json
from pathlib import Path

from research.mtp_research.validation.run_combined_p0_fingerprint_selection_design import main


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_cli_writes_selection_design_report(tmp_path: Path, capsys) -> None:
    summary = _write_json(
        tmp_path / "summary.json",
        {
            "coverage_audit": {
                "total_unique_launches": 2,
                "all_three_p0_launches": 2,
                "balanced_sample_rows": 1,
                "leftover_sample_rows": 1,
            },
            "milestone_tier_counts": {"reached_20k_but_never_50k": 1, "reached_1m_plus": 1},
        },
    )
    tier = _write_csv(
        tmp_path / "tier.csv",
        [
            {
                "evidence_subset": "combined_sample",
                "feature": "fdv_per_event_at_20k",
                "milestone_tier": "reached_1m_plus",
                "median": 10,
                "sample_count": 1,
                "coverage_pct": 100,
            },
            {
                "evidence_subset": "combined_sample",
                "feature": "fdv_per_event_at_20k",
                "milestone_tier": "reached_20k_but_never_50k",
                "median": 1,
                "sample_count": 1,
                "coverage_pct": 100,
            },
        ],
    )
    entry_exit = _write_csv(
        tmp_path / "entry_exit.csv",
        [{"feature_name": "fdv_per_event_at_20k", "feature_side": "entry_side", "available_now": True}],
    )
    candidate = _write_csv(tmp_path / "candidate.csv", [{"name": "concept", "sample_support": 0}])
    dataset = _write_jsonl(
        tmp_path / "combined.jsonl",
        [
            {
                "launch_id": "a",
                "milestone_tier": "reached_1m_plus",
                "is_balanced_sample": True,
                "is_leftover_sample": False,
                "fdv_per_event_at_20k": 10,
                "repeated_buyer_quality_proxy": 0.9,
                "launches_sharing_funder": 0,
                "shared_funding_proxy": False,
                "time_linked_funding_proxy": False,
                "top_holder_share_proxy": 0.95,
            },
            {
                "launch_id": "b",
                "milestone_tier": "reached_20k_but_never_50k",
                "is_balanced_sample": False,
                "is_leftover_sample": True,
                "fdv_per_event_at_20k": 1,
                "repeated_buyer_quality_proxy": 0.2,
                "launches_sharing_funder": 2,
                "shared_funding_proxy": True,
                "time_linked_funding_proxy": True,
                "top_holder_share_proxy": 0.6,
            },
        ],
    )

    rc = main(
        [
            "--summary-path",
            str(summary),
            "--tier-feature-comparison-path",
            str(tier),
            "--entry-vs-exit-features-path",
            str(entry_exit),
            "--candidate-fingerprints-path",
            str(candidate),
            "--combined-dataset-path",
            str(dataset),
            "--output-dir",
            str(tmp_path / "reports"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=combined_p0_fingerprint_selection_design_v0" in out
    assert "readiness_classification=" in out
    assert "selected_fingerprints=" in out
    assert "immediate_next_action=" in out
