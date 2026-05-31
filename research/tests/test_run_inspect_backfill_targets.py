import json
from pathlib import Path

from research.mtp_research.pipeline.run_inspect_backfill_targets import main


def test_inspect_backfill_targets_prints_counts_and_warnings(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "candidate_registry.jsonl"
    target_path = tmp_path / "targets.jsonl"
    registry_path.write_text(
        json.dumps({"token_mint": "mint-1", "metadata_json": {"example_only": True}}) + "\n",
        encoding="utf-8",
    )
    target_path.write_text(
        json.dumps(
            {
                "target_id": "mint-1-target",
                "role": "mint",
                "address": "mint-1",
                "token_mint": "mint-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_inspect_backfill_targets",
            "--candidate-registry-path",
            str(registry_path),
            "--target-plan-path",
            str(target_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "candidate_count=1" in output
    assert "target_count=1" in output
    assert "role_counts={'mint': 1}" in output
    assert "warning=mint_only_targets" in output
    assert "warning=mock_candidates_present" in output
    assert "target target_id=mint-1-target role=mint address=mint-1 token_mint=mint-1" in output
