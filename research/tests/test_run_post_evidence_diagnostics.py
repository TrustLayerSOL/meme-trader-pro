import json
from pathlib import Path

from research.mtp_research.pipeline.run_post_evidence_diagnostics import main


def test_run_post_evidence_diagnostics_prints_low_value_guidance(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
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
    monkeypatch.setattr("sys.argv", ["run_post_evidence_diagnostics"])

    assert main() == 0
    output = capsys.readouterr().out
    assert "bottleneck_stage=low_value_backfill_targets" in output
    assert "inspect data/backtests/backfill_targets_plan.jsonl" in output
    assert "do not scale Helius backfills yet" in output
    assert "network_calls=0" in output
