import json
from pathlib import Path

from research.mtp_research.validation.run_funding_lineage_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t010_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    funding_path = _write_jsonl(
        tmp_path / "funding.jsonl",
        [
            {
                "launch_id": "launch-a",
                "mint": "mint-a",
                "creator": "creator-a",
                "launch_ts": 1000,
                "candidate_funding_wallet": "funder-a",
                "funding_age_seconds": 3600,
                "funding_amount_sol": 1.0,
                "funding_source_confidence": 0.85,
                "creator_has_prior_funding_trace": True,
                "launches_sharing_funder": 2,
                "creator_funder_reuse_count": 1,
                "common_funder_candidate_id": "funder-a",
            }
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "runups": {"max_runup_120m": 0.2},
                "drawdowns": {"max_drawdown_120m": -0.1},
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T010_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_funding_lineage_thesis",
            "--funding-link-path",
            str(funding_path),
            "--outcomes-path",
            str(outcomes_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "thesis_id=T010" in output
    assert "launch_count=1" in output
    assert (output_dir / "T010_funding_lineage_summary.json").exists()
    assert (output_dir / "T010_funding_lineage_summary.md").exists()
    status_text = status_path.read_text(encoding="utf-8")
    assert "T010 FUNDING LINEAGE" in status_text
    assert "No thesis promotion was made." in status_text
    assert "No trading rules were generated." in status_text
