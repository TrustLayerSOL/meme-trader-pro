import json
from pathlib import Path

from research.mtp_research.validation.run_holder_growth_tempo_thesis import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def test_cli_writes_t002_reports_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "launches.jsonl",
        [{"launch_id": "launch-a", "token_mint": "mint-a", "launch_ts": 1000, "launch_regime": "strict"}],
    )
    snapshots_path = _write_jsonl(
        tmp_path / "snapshots.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 30,
                "active_wallets": 1,
                "unique_actors": 1,
                "buy_count": 1,
                "sell_count": 0,
                "tx_count": 1,
                "liquidity_proxy": 1,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1000,
                "metadata_json": {"event_count": 1},
            },
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "launch_age_seconds": 1800,
                "active_wallets": 3,
                "unique_actors": 3,
                "buy_count": 4,
                "sell_count": 1,
                "tx_count": 5,
                "liquidity_proxy": 2,
                "valuation_proxy_available": True,
                "valuation_proxy_usd": 1100,
                "metadata_json": {"event_count": 5},
            },
        ],
    )
    outcomes_path = _write_jsonl(
        tmp_path / "outcomes.jsonl",
        [
            {
                "launch_id": "launch-a",
                "token_mint": "mint-a",
                "price_available_120m": True,
                "has_liquidity_proxy_at_120m": True,
                "proxy_threshold_outcomes_usable": True,
            }
        ],
    )
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "T002_STATUS.md"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_holder_growth_tempo_thesis",
            "--candidates-path",
            str(candidates_path),
            "--snapshots-path",
            str(snapshots_path),
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
    assert (output_dir / "T002_holder_growth_tempo_summary.json").exists()
    assert (output_dir / "T002_holder_growth_tempo_summary.md").exists()
    status_text = status_path.read_text(encoding="utf-8")
    assert "No trading rules were generated." in status_text
    assert "Holder Growth Tempo" in status_text
