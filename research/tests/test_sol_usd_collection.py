import json
import subprocess
from pathlib import Path

from research.mtp_research.launch_regime.sol_usd_collection import (
    collect_sol_usd_prices,
    timestamp_span,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def test_timestamp_span_reads_snapshots_and_outcomes(tmp_path: Path) -> None:
    snapshots = _write_jsonl(tmp_path / "snapshots.jsonl", [{"snapshot_ts": 100}, {"snapshot_ts": 200}])
    outcomes = _write_jsonl(tmp_path / "outcomes.jsonl", [{"metadata_json": {"price_event_block_time_120m": 300}}])

    assert timestamp_span([snapshots, outcomes]) == (100, 300)


def test_collect_sol_usd_prices_writes_rows_from_mocked_client(tmp_path: Path) -> None:
    snapshots = _write_jsonl(tmp_path / "snapshots.jsonl", [{"snapshot_ts": 100}])
    outcomes = _write_jsonl(tmp_path / "outcomes.jsonl", [{"metadata_json": {"price_event_block_time_120m": 200}}])

    def fake_get(url: str) -> dict:
        assert "from=100" in url
        assert "to=200" in url
        return {"prices": [[100_000, 80.0], [200_000, 81.0]]}

    report = collect_sol_usd_prices(
        input_paths=[snapshots, outcomes],
        output_path=tmp_path / "sol_usd.jsonl",
        http_get=fake_get,
        execute=True,
    )

    assert report["execute"] is True
    assert report["price_rows_written"] == 2
    assert report["network_calls"] == 1
    rows = [json.loads(line) for line in (tmp_path / "sol_usd.jsonl").read_text().splitlines()]
    assert rows[0]["ts"] == 100
    assert rows[0]["sol_usd"] == 80.0
    assert rows[0]["source"] == "coingecko_solana_market_chart_range"


def test_sol_usd_collection_cli_dry_run(tmp_path: Path) -> None:
    snapshots = _write_jsonl(tmp_path / "snapshots.jsonl", [{"snapshot_ts": 100}])

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_sol_usd_collection",
            "--input-path",
            str(snapshots),
            "--output-path",
            str(tmp_path / "sol_usd.jsonl"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "execute=False" in result.stdout
    assert "network_calls=0" in result.stdout
