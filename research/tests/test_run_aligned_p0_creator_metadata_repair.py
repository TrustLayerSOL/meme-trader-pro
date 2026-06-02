import json
from pathlib import Path

from research.mtp_research.validation.run_aligned_p0_creator_metadata_repair import main


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


def test_cli_runs_metadata_repair_dry_sprint(tmp_path: Path, capsys) -> None:
    summary = _write_json(tmp_path / "summary.json", {"target_cohort": {"launches_selected": 1}, "overlap_audit": {"launches_with_all_three_p0_layers": 0}})
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [
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
            }
        ],
    )
    targets = tmp_path / "targets.csv"
    targets.write_text(
        "creator,launch_id,launch_ts,milestone_tier,mint,crossing_20k_age\n,launch-a,1000,reached_20k_but_never_50k,mint-a,30\n",
        encoding="utf-8",
    )
    universe = _write_json(tmp_path / "universe.json", {"launch_feature_rows": []})
    creators = _write_jsonl(tmp_path / "creators.jsonl", [{"mint": "mint-a", "creator_deployer": "creator-a"}])

    rc = main(
        [
            "--summary-path",
            str(summary),
            "--structural-features-path",
            str(structural),
            "--aligned-target-path",
            str(targets),
            "--universe-path",
            str(universe),
            "--creator-lookup-path",
            str(creators),
            "--output-root",
            str(tmp_path / "lake"),
            "--repo-root",
            str(tmp_path / "repo"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=aligned_p0_creator_metadata_repair_v0" in out
    assert "unknown_creator_count_before=1" in out
    assert "creator_recovered_count=1" in out
    assert "network_calls_made=0" in out
