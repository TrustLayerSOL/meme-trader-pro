import json
from pathlib import Path

from research.mtp_research.pipeline.run_evidence_audit import main


def test_run_evidence_audit_writes_markdown_and_json(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    Path("data/normalized").mkdir(parents=True)
    Path("data/backtests").mkdir(parents=True)
    Path("data/normalized/candidate_registry.jsonl").write_text(
        json.dumps({"token_mint": "mint-1", "metadata_json": {"is_mock": True}}) + "\n",
        encoding="utf-8",
    )
    Path("data/backtests/backfill_targets_plan.jsonl").write_text(
        json.dumps({"role": "mint", "address": "mint-1", "token_mint": "mint-1"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("sys.argv", ["run_evidence_audit", "--output-dir", str(tmp_path / "reports")])

    assert main() == 0
    output = capsys.readouterr().out
    assert "bottleneck_stage=low_value_backfill_targets" in output
    assert "markdown_path=" in output
    assert "json_path=" in output
    assert (tmp_path / "reports").exists()
    assert list((tmp_path / "reports").glob("evidence_audit_*.md"))
    assert list((tmp_path / "reports").glob("evidence_audit_*.json"))
