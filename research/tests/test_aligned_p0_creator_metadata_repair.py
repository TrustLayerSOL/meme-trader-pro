import csv
import json
import math
from pathlib import Path

from research.mtp_research.validation.aligned_p0_creator_metadata_repair import (
    build_aligned_p0_creator_metadata_repair,
)


TIERS = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]


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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    structural_rows = [
        {
            "launch_id": "launch-a",
            "mint": "mint-a",
            "creator": "",
            "launch_ts": 1000,
            "launch_date": "2026-01-01",
            "milestone_tier": "reached_20k_but_never_50k",
            "has_early_buyer_wallet_history": True,
            "has_top_holder_replay": True,
            "has_creator_funder_graph": False,
            "has_all_three_p0_layers": False,
        },
        {
            "launch_id": "launch-b",
            "mint": "mint-b",
            "creator": "creator-b",
            "launch_ts": 2000,
            "launch_date": "2026-01-02",
            "milestone_tier": "reached_50k_but_never_100k",
            "has_early_buyer_wallet_history": False,
            "has_top_holder_replay": True,
            "has_creator_funder_graph": True,
            "has_all_three_p0_layers": False,
        },
        {
            "launch_id": "launch-c",
            "mint": "mint-c",
            "creator": "",
            "launch_ts": 3000,
            "launch_date": "2026-01-03",
            "milestone_tier": "reached_100k_but_never_200k",
            "has_early_buyer_wallet_history": True,
            "has_top_holder_replay": True,
            "has_creator_funder_graph": True,
            "has_all_three_p0_layers": True,
        },
    ]
    target_rows = [
        {**row, "reason_selected": "fixture"} for row in structural_rows
    ]
    summary = {
        "target_cohort": {"launches_selected": 3},
        "overlap_audit": {"launches_with_all_three_p0_layers": 1},
        "input_paths": {"event_paths": []},
    }
    universe_rows = []
    event_rows = []
    for tier_idx, tier in enumerate(TIERS):
        for i in range(2):
            mint = f"candidate-{tier_idx}-{i}"
            launch_ts = 10_000 + tier_idx * 1000 + i * 100
            universe_rows.append(
                {
                    "launch_id": f"candidate-launch-{tier_idx}-{i}",
                    "mint": mint,
                    "creator": "" if i == 0 else f"existing-creator-{tier_idx}",
                    "launch_ts": launch_ts,
                    "launch_date": f"2026-02-{tier_idx + 1:02d}",
                    "milestone_tier": tier,
                    "crossing_20k_age": 30,
                    "crossing_50k_age": 60,
                    "crossing_100k_age": 90,
                    "crossing_200k_age": 120,
                    "crossing_500k_age": 150,
                    "crossing_1m_age": 180,
                }
            )
            event_rows.append({"token_mint": mint, "actor": f"buyer-{tier_idx}-{i}", "block_time": launch_ts + 10, "side": "accumulate", "venue": "pumpfun_buy"})
    creator_rows = [
        {"mint": "mint-a", "creator_deployer": "creator-a", "accepted": True},
        {"mint": "mint-c", "creator_deployer": "creator-c-1", "accepted": True},
        {"mint": "mint-c", "creator_deployer": "creator-c-2", "accepted": True},
    ]
    for tier_idx in range(len(TIERS)):
        creator_rows.append({"mint": f"candidate-{tier_idx}-0", "creator_deployer": f"recovered-creator-{tier_idx}", "accepted": True})
    cleanup_file = tmp_path / "repo" / "data" / "backtests" / "diagnostics" / "research_dataset_price_quality_gated.jsonl"
    cleanup_file.parent.mkdir(parents=True, exist_ok=True)
    cleanup_file.write_text('{"generated": true}\n', encoding="utf-8")
    return {
        "summary_path": _write_json(tmp_path / "summary.json", summary),
        "structural_path": _write_jsonl(tmp_path / "structural.jsonl", structural_rows),
        "target_path": _write_csv(tmp_path / "targets.csv", target_rows),
        "universe_path": _write_json(tmp_path / "universe.json", {"launch_feature_rows": universe_rows, "dataset": {"event_paths": []}}),
        "creator_path": _write_jsonl(tmp_path / "creators.jsonl", creator_rows),
        "events_path": _write_jsonl(tmp_path / "events.jsonl", event_rows),
        "repo_root": tmp_path / "repo",
        "cleanup_file": cleanup_file,
        "output_root": tmp_path / "lake",
        "status_path": tmp_path / "STATUS.md",
    }


def test_creator_recovery_and_ambiguous_rows_fail_closed(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=paths["summary_path"],
        structural_features_path=paths["structural_path"],
        aligned_target_path=paths["target_path"],
        universe_path=paths["universe_path"],
        creator_lookup_paths=[paths["creator_path"]],
        event_paths=[paths["events_path"]],
        repo_root=paths["repo_root"],
        repo_local_artifacts=[paths["cleanup_file"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
    )

    assert report["creator_audit"]["unknown_creator_count_before"] == 2
    assert report["creator_recovery"]["recovered_count"] == 1
    assert report["creator_recovery"]["unknown_count_after"] == 1
    assert report["creator_recovery"]["classification_counts"]["ambiguous_multiple_creators"] == 1
    assert outputs["repaired_jsonl_path"].exists()
    repaired_rows = [json.loads(line) for line in outputs["repaired_jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_mint = {row["mint"]: row for row in repaired_rows}
    assert by_mint["mint-a"]["repaired_creator"] == "creator-a"
    assert by_mint["mint-c"]["repaired_creator"] is None


def test_overlap_failure_classification_and_second_plan_bias(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=paths["summary_path"],
        structural_features_path=paths["structural_path"],
        aligned_target_path=paths["target_path"],
        universe_path=paths["universe_path"],
        creator_lookup_paths=[paths["creator_path"]],
        event_paths=[paths["events_path"]],
        repo_root=paths["repo_root"],
        repo_local_artifacts=[paths["cleanup_file"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
        second_run_per_tier=1,
    )

    assert report["overlap_failure_audit"]["cause_counts"]["unknown_creator"] == 1
    assert report["overlap_failure_audit"]["cause_counts"]["no_early_buyers_before_trigger"] == 1
    assert report["second_run_plan"]["target_count"] == 6
    assert report["second_run_plan"]["known_creator_share_pct"] == 100.0
    assert report["second_run_plan"]["projected_all_three_layer_eligibility"] == 6
    assert outputs["second_run_targets_path"].exists()
    rows = list(csv.DictReader(outputs["second_run_targets_path"].open(encoding="utf-8")))
    assert len(rows) == 6
    assert all(row["creator"] for row in rows)


def test_repo_local_generated_artifact_cleanup_is_verified(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=paths["summary_path"],
        structural_features_path=paths["structural_path"],
        aligned_target_path=paths["target_path"],
        universe_path=paths["universe_path"],
        creator_lookup_paths=[paths["creator_path"]],
        event_paths=[paths["events_path"]],
        repo_root=paths["repo_root"],
        repo_local_artifacts=[paths["cleanup_file"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
    )

    artifact = report["repo_local_artifact_cleanup"]["artifacts"][0]
    assert artifact["classification"] == "generated_repo_local_artifact"
    assert artifact["action_taken"] == "moved_to_orico_and_removed_repo_duplicate"
    assert artifact["checksum_verified"] is True
    assert not paths["cleanup_file"].exists()
    assert Path(artifact["orico_path"]).exists()
    assert outputs["cleanup_report_json_path"].exists()


def test_guardrails_no_network_or_trading_labels(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, _outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=paths["summary_path"],
        structural_features_path=paths["structural_path"],
        aligned_target_path=paths["target_path"],
        universe_path=paths["universe_path"],
        creator_lookup_paths=[paths["creator_path"]],
        event_paths=[paths["events_path"]],
        repo_root=paths["repo_root"],
        repo_local_artifacts=[paths["cleanup_file"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
    )

    text = json.dumps(report).lower()
    assert report["network_calls_made"] == 0
    assert "no_trading_logic" in report["methodology_flags"]
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text


def test_nan_creator_values_are_treated_as_unknown(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    structural = _write_jsonl(
        tmp_path / "nan_structural.jsonl",
        [
            {
                "launch_id": "launch-nan",
                "mint": "mint-a",
                "creator": math.nan,
                "launch_ts": 1000,
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_20k_but_never_50k",
                "has_early_buyer_wallet_history": True,
                "has_top_holder_replay": True,
                "has_creator_funder_graph": False,
                "has_all_three_p0_layers": False,
            }
        ],
    )

    report, _outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=paths["summary_path"],
        structural_features_path=structural,
        aligned_target_path=paths["target_path"],
        universe_path=paths["universe_path"],
        creator_lookup_paths=[paths["creator_path"]],
        event_paths=[paths["events_path"]],
        repo_root=paths["repo_root"],
        repo_local_artifacts=[paths["cleanup_file"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
    )

    assert report["creator_audit"]["unknown_creator_count_before"] == 1
    assert report["creator_recovery"]["recovered_count"] == 1
