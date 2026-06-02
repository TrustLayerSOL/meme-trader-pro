import json
from pathlib import Path

from research.mtp_research.validation.run_t002_holder_growth_chronological_robustness import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t002_chronological_robustness_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates = []
    snapshots = []
    holder_state = []
    outcomes = []
    for index in range(8):
        mint = f"mint-{index}"
        candidates.append(
            {
                "launch_id": f"launch-{mint}",
                "token_mint": mint,
                "launch_ts": 1_700_000_000 + index * 60,
                "launch_regime": "strict",
            }
        )
        for age, holder_count, value in [
            (30, 1, 1000),
            (180, 2 + index, 1010 + index),
            (600, 3 + index, 1020 + index),
            (1800, 4 + index, 1030 + index),
            (7200, 4 + index, 1040 + index),
        ]:
            snapshots.append(
                {
                    "launch_id": f"launch-{mint}",
                    "token_mint": mint,
                    "launch_age_seconds": age,
                    "active_wallets": holder_count,
                    "unique_actors": holder_count,
                    "buy_count": holder_count,
                    "sell_count": 0,
                    "tx_count": holder_count,
                    "liquidity_proxy": 1,
                    "valuation_proxy_available": True,
                    "valuation_proxy_usd": value,
                    "metadata_json": {"event_count": holder_count},
                }
            )
            if age in {30, 180, 600, 1800}:
                holder_state.append(
                    {
                        "launch_id": f"launch-{mint}",
                        "mint": mint,
                        "snapshot_age_seconds": age,
                        "holder_count": holder_count,
                        "top_holder_share": 0.25,
                        "top_10_holder_share": 0.75,
                        "creator_holder_share": 0.0,
                        "holder_snapshot_confidence": "medium",
                        "is_observed_delta_replay": True,
                        "is_confirmed_full_chain_snapshot": False,
                    }
                )
        outcomes.append(
            {
                "launch_id": f"launch-{mint}",
                "token_mint": mint,
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
                "proxy_threshold_outcomes_usable": True,
            }
        )
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", candidates)
    snapshots_path = _write_jsonl(tmp_path / "snapshots.jsonl", snapshots)
    holder_state_path = _write_jsonl(tmp_path / "holder_state.jsonl", holder_state)
    outcomes_path = _write_jsonl(tmp_path / "outcomes.jsonl", outcomes)
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T002_ROBUSTNESS_STATUS.md"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_t002_holder_growth_chronological_robustness",
            "--candidates-path",
            str(candidates_path),
            "--snapshots-path",
            str(snapshots_path),
            "--holder-state-snapshots-path",
            str(holder_state_path),
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
    assert "thesis_id=T002" in output
    assert "robustness_classification=" in output
    assert (output_dir / "T002_holder_growth_chronological_robustness_summary.json").exists()
    assert (output_dir / "T002_holder_growth_chronological_robustness_summary.md").exists()
    assert status_path.exists()
