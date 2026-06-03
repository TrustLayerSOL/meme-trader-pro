import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_forward_50_freshness_quality_audit import main


def test_cli_writes_forward_50_audit_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    raw = root / "data" / "raw" / "forward_observation" / "efficient_movers"
    out = tmp_path / "reports"
    obs.mkdir(parents=True)
    raw.mkdir(parents=True)
    _write_jsonl(obs / "candidates.jsonl", [{"observation_id": "o1", "mint": "mint-a", "source": "source-a", "observed_at": 1}])
    _write_jsonl(obs / "candidate_paths.jsonl", [{"observation_id": "o1", "mint": "mint-a", "timestamp": 1, "fdv_proxy": 25_000}])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_forward_50_freshness_quality_audit",
            "--data-root",
            str(root),
            "--max-candidates",
            "1",
            "--output-dir",
            str(out),
        ],
    )

    exit_code = main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "report_id=forward_50_freshness_quality_audit_v0" in captured
    assert "candidates_audited=1" in captured
    assert "network_calls_made=0" in captured
    assert (out / "forward_50_freshness_quality_summary.json").exists()
    assert (out / "forward_50_freshness_audit.csv").exists()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
