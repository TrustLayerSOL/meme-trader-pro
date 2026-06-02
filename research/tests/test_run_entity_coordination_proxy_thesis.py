import json
from pathlib import Path

from research.mtp_research.validation.run_entity_coordination_proxy_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t007_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [{"launch_id": "launch-a", "token_mint": "mint-a", "launch_ts": 1000}],
    )
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 30,
                "launch_ts": 1000,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1000,
            },
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 7200,
                "launch_ts": 1000,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1100,
            },
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [{"launch_id": "launch-a", "token_mint": "mint-a", "price_available_120m": True, "has_liquidity_proxy_at_120m": True}],
    )
    entity_proxy_path = _write_jsonl(
        tmp_path / "entity_proxy.jsonl",
        [
            {
                "launch_id": "launch-a",
                "mint": "mint-a",
                "creator_linked_share_proxy": 0.1,
                "repeated_actor_overlap_proxy": 1,
                "repeated_buyer_overlap_proxy": 1,
                "synchronized_participation_proxy": 0.5,
                "circularity_proxy": 0,
                "churn_proxy": 0.0,
                "proxy_confidence": "medium",
                "proxy_missing_reason": None,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T007_STATUS.md"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_entity_coordination_proxy_thesis",
            "--candidates-path",
            str(candidates_path),
            "--snapshots-path",
            str(snapshots_path),
            "--outcomes-path",
            str(outcomes_path),
            "--entity-proxy-path",
            str(entity_proxy_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "thesis_id=T007" in output
    assert "final_classification=" in output
    assert (output_dir / "T007_entity_coordination_proxy_summary.json").exists()
    assert (output_dir / "T007_entity_coordination_proxy_summary.md").exists()
    assert status_path.exists()
