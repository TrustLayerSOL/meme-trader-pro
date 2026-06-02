import json
from pathlib import Path

from research.mtp_research.validation.run_creator_migration_reputation_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_runs_with_explicit_paths_and_writes_outputs(tmp_path: Path, capsys) -> None:
    candidates = [
        {
            "launch_id": "launch-1",
            "token_mint": "mint-1",
            "launch_ts": 60,
            "metadata_json": {"creator_deployer": "creator-a"},
        },
        {
            "launch_id": "launch-2",
            "token_mint": "mint-2",
            "launch_ts": 120,
            "metadata_json": {"creator_deployer": "creator-a"},
        },
    ]
    outcomes = [
        {
            "launch_id": "launch-1",
            "token_mint": "mint-1",
            "runups": {"max_runup_120m": 1.0},
            "drawdowns": {"max_drawdown_120m": -0.1},
            "price_available_120m": True,
            "has_liquidity_proxy_at_120m": True,
        },
        {
            "launch_id": "launch-2",
            "token_mint": "mint-2",
            "runups": {"max_runup_120m": 2.0},
            "drawdowns": {"max_drawdown_120m": -0.2},
            "price_available_120m": True,
            "has_liquidity_proxy_at_120m": True,
        },
    ]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-a",
            "migration_time": "1970-01-01T00:01:10+00:00",
            "migration_signature": "migration-1",
            "pumpfun_migrate_event_observed": True,
            "migration_source": "helius_json_rpc_pumpfun_migrate_log",
        }
    ]

    result = main(
        [
            "--candidates-path",
            str(_write_jsonl(tmp_path / "candidates.jsonl", candidates)),
            "--outcomes-path",
            str(_write_jsonl(tmp_path / "outcomes.jsonl", outcomes)),
            "--migration-labels-path",
            str(_write_jsonl(tmp_path / "labels.jsonl", labels)),
            "--output-dir",
            str(tmp_path / "reports"),
            "--status-path",
            str(tmp_path / "T008_STATUS.md"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "thesis_id=T008" in output
    assert "dataset_scope=all_collected" in output
    assert "launch_count=2" in output
    assert (tmp_path / "reports" / "T008_creator_migration_reputation_summary.json").exists()
    assert (tmp_path / "T008_STATUS.md").exists()
