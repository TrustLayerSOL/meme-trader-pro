import json
from pathlib import Path

from research.mtp_research.validation.run_t011_expanded_rerun import main


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _snapshot(mint: str, ts: int, age: int, value: float, events: int, buys: int, active: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": ts,
        "snapshot_ts": ts + age,
        "launch_age_seconds": age,
        "valuation_proxy_available": True,
        "valuation_proxy_usd": value,
        "buy_count": buys,
        "sell_count": max(0, events - buys),
        "active_wallets": active,
        "unique_actors": active,
        "tx_count": events,
        "metadata_json": {"event_count": events},
    }


def test_cli_runs_expanded_rerun_without_sidecars(tmp_path: Path, monkeypatch, capsys) -> None:
    rows = []
    for idx in range(6):
        mint = f"mint-{idx}"
        ts = 1_700_000_000 + idx * 86_400
        rows.extend(
            [
                _snapshot(mint, ts, 30, 15_000, 4, 3, 3),
                _snapshot(mint, ts, 60, 20_000, 4, 3, 3),
                _snapshot(mint, ts, 120, 100_000 if idx % 2 == 0 else 40_000, 5, 4, 4),
            ]
        )
    snapshots = _write_jsonl(tmp_path / "snapshots.jsonl", rows)
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_t011_expanded_rerun",
            "--snapshot-path",
            str(snapshots),
            "--holder-state-snapshots-path",
            "",
            "--entity-proxy-path",
            "",
            "--migration-labels-path",
            "",
            "--funding-link-path",
            "",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=t011_expanded_rerun_v0" in output
    assert "expanded_20k_trigger_count=6" in output
    assert (output_dir / "T011_expanded_rerun_summary.json").exists()
    assert (output_dir / "T011_expanded_rerun_summary.md").exists()
