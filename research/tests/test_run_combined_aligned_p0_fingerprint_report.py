import json
from pathlib import Path

from research.mtp_research.validation.run_combined_aligned_p0_fingerprint_report import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def test_cli_writes_combined_fingerprint_report(tmp_path: Path, capsys) -> None:
    base = {
        "launch_id": "launch-a",
        "mint": "mint-a",
        "creator": "creator-a",
        "launch_ts": 1_700_000_000,
        "launch_date": "2023-11-14",
        "milestone_tier": "reached_1m_plus",
        "early_buyer_wallet_count": 3,
        "early_buyer_with_prior_history_count": 2,
        "top_holder_share_proxy": 0.4,
        "top_10_holder_share_proxy": 0.8,
        "top_holder_replay_confidence": "medium",
        "is_confirmed_full_chain_snapshot": False,
        "candidate_funder": "funder-a",
        "candidate_funder_confidence": "medium",
        "shared_funding_proxy": True,
        "time_linked_funding_proxy": True,
        "has_early_buyer_wallet_history": True,
        "has_top_holder_replay": True,
        "has_creator_funder_graph": True,
        "has_all_three_p0_layers": True,
    }
    original = _write_jsonl(tmp_path / "original.jsonl", [base])
    balanced = _write_jsonl(tmp_path / "balanced.jsonl", [{**base, "launch_id": "launch-b", "mint": "mint-b"}])
    leftover = _write_jsonl(tmp_path / "leftover.jsonl", [{**base, "launch_id": "launch-c", "mint": "mint-c"}])

    rc = main(
        [
            "--original-structural-path",
            str(original),
            "--balanced-structural-path",
            str(balanced),
            "--remaining-structural-path",
            str(leftover),
            "--output-dir",
            str(tmp_path / "reports"),
            "--dataset-parquet-path",
            str(tmp_path / "combined.parquet"),
            "--dataset-jsonl-path",
            str(tmp_path / "combined.jsonl"),
            "--status-path",
            str(tmp_path / "STATUS.md"),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "report_id=combined_aligned_p0_fingerprint_report_v0" in out
    assert "combined_unique_rows=3" in out
    assert "all_three_p0_rows=3" in out
