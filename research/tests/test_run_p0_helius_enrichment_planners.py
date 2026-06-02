import json
from pathlib import Path

import pytest

from research.mtp_research.validation.run_p0_helius_enrichment_planners import main


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_dry_run_writes_outputs_and_rejects_execute(tmp_path: Path, monkeypatch, capsys) -> None:
    master = _write_json(
        tmp_path / "master.json",
        {
            "helius_budget_plan": [
                {"plan_id": "top_holder_milestone_snapshot_pilot", "estimated_credits": 20_000, "priority": "P0"}
            ],
            "priority_rank": [{"priority": "P0", "data_family": "top_holder_structure"}],
        },
    )
    repeated = _write_json(
        tmp_path / "repeated.json",
        {
            "launch_feature_rows": [
                {
                    "launch_id": "launch-a",
                    "mint": "mint-a",
                    "creator": "creator-a",
                    "launch_ts": 1_700_000_000,
                    "launch_date": "2023-11-14",
                    "milestone_tier": "reached_1m_plus",
                    "crossing_20k_age": 60,
                    "crossing_50k_age": 90,
                    "crossing_100k_age": 120,
                    "crossing_500k_age": 180,
                    "crossing_1m_age": 240,
                },
                {
                    "launch_id": "launch-b",
                    "mint": "mint-b",
                    "creator": "creator-b",
                    "launch_ts": 1_700_086_400,
                    "launch_date": "2023-11-15",
                    "milestone_tier": "reached_20k_but_never_50k",
                    "crossing_20k_age": 70,
                },
            ],
            "dataset": {"event_paths": []},
        },
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [{"token_mint": "mint-a", "actor": "wallet-a", "block_time": 1_700_000_030, "side": "accumulate"}],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_p0_helius_enrichment_planners",
            "--master-plan-path",
            str(master),
            "--repeated-buyer-report-path",
            str(repeated),
            "--event-path",
            str(events),
            "--funding-link-path",
            "",
            "--pilot",
            "top-holder",
            "--output-dir",
            str(tmp_path / "reports"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
            "--dry-run",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "overall_classification=" in output
    assert "network_calls_made=0" in output
    assert (tmp_path / "reports" / "p0_helius_planner_summary.json").exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_p0_helius_enrichment_planners",
            "--master-plan-path",
            str(master),
            "--repeated-buyer-report-path",
            str(repeated),
            "--pilot",
            "top-holder",
            "--output-dir",
            str(tmp_path / "reports"),
            "--execute",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
