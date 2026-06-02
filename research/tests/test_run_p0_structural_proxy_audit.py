import json
from pathlib import Path

from research.mtp_research.validation.run_p0_structural_proxy_audit import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def test_cli_writes_p0_structural_proxy_audit(tmp_path: Path, monkeypatch, capsys) -> None:
    universe_path = tmp_path / "universe.json"
    universe_path.write_text(
        json.dumps(
            {
                "launch_feature_rows": [
                    {"launch_id": "launch-a", "mint": "mint-a", "milestone_tier": "reached_100k_but_never_200k"}
                ]
            }
        ),
        encoding="utf-8",
    )
    early_path = _write_jsonl(tmp_path / "early.jsonl", [{"current_launch_id": "launch-a", "current_mint": "mint-a", "wallet": "buyer-a", "prior_transaction_count": 1}])
    top_path = _write_jsonl(tmp_path / "top.jsonl", [{"launch_id": "launch-a", "mint": "mint-a", "top_holder_share_proxy": 0.5, "top_10_holder_share_proxy": 0.9, "top_holder_owner": "top-a"}])
    funder_path = _write_jsonl(tmp_path / "funder.jsonl", [{"launch_id": "launch-a", "mint": "mint-a", "creator": "creator-a", "candidate_funder": "funder-a", "candidate_funder_confidence": "high"}])
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_p0_structural_proxy_audit",
            "--universe-path",
            str(universe_path),
            "--early-buyer-path",
            str(early_path),
            "--top-holder-path",
            str(top_path),
            "--creator-funder-path",
            str(funder_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=p0_structural_proxy_audit_v0" in output
    assert "readiness_classification=" in output
    assert "launches_with_any_p0_structural_data=1" in output
    assert (output_dir / "p0_structural_proxy_audit_summary.json").exists()
    assert (output_dir / "p0_structural_proxy_coverage_by_tier.csv").exists()
