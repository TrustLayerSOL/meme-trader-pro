import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_forward_birth_watch_followup_collector import main


def test_cli_runs_birth_watch_followup_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(obs / "candidates.jsonl", [{"observation_id": "birth-a", "mint": "mint-a", "freshness_lane": "birth_watch"}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_birth_watch_followup_collector",
            "--data-root",
            str(root),
            "--max-mints",
            "1",
            "--signatures-per-mint",
            "4",
            "--transactions-per-mint",
            "2",
            "--request-ceiling",
            "10",
        ],
    )

    exit_code = main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "report_id=forward_birth_watch_followup_collector_v0" in captured
    assert "execute=False" in captured
    assert "selected_mint_count=1" in captured
    assert "network_calls_made=0" in captured


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
