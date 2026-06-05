import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_cross_sample_pattern_synthesis import main


def test_cross_sample_pattern_synthesis_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    live = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    live.mkdir(parents=True)
    _write_jsonl(live / "births.jsonl", [{"mint": "mint-a", "fdv_path_before_20k": True, "official_accepted_birth": True}])
    _write_jsonl(
        live / "followup_paths.jsonl",
        [{"mint": "mint-a", "timestamp": 1.0, "fdv_proxy": 25_000, "crossed_20k": True}],
    )
    (live / "lifecycle_state.json").write_text('{"mints":{"mint-a":{"state":"trigger_qualified_active_watch"}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_cross_sample_pattern_synthesis",
            "--data-root",
            str(tmp_path),
            "--timestamp",
            "20260605T000000Z",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "Cross-Sample Pattern Synthesis" in output
    assert "collector_left_running=" in output
    assert "no_live_trading=True" in output
    assert (
        tmp_path
        / "data/backtests/diagnostics/reports/forward_observation/cross_sample_pattern_synthesis/cross_sample_pattern_synthesis_summary.json"
    ).exists()
    assert (tmp_path / "theses" / "CROSS_SAMPLE_PATTERN_SYNTHESIS_STATUS.md").exists()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
