import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_forward_birth_to_trigger_followup_audit import main


def test_cli_writes_birth_to_trigger_followup_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    out = tmp_path / "reports"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 1,
            }
        ],
    )
    _write_jsonl(obs / "candidate_paths.jsonl", [{"observation_id": "birth-a", "mint": "mint-a", "event_type": "pumpfun_create", "timestamp": 1}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_birth_to_trigger_followup_audit",
            "--data-root",
            str(root),
            "--output-dir",
            str(out),
        ],
    )

    exit_code = main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "report_id=forward_birth_to_trigger_followup_audit_v0" in captured
    assert "total_birth_watch_candidates=1" in captured
    assert "network_calls_made=0" in captured
    assert (out / "birth_to_trigger_followup_audit.json").exists()
    assert (out / "birth_to_trigger_followup_audit.md").exists()
    assert (out / "birth_to_trigger_followup_audit.csv").exists()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
