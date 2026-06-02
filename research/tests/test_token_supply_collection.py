import json
import subprocess
from pathlib import Path

from research.mtp_research.launch_regime.token_supply_collection import (
    collect_token_supply,
    load_unique_mints,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def fetch_token_supply(self, mint: str) -> dict:
        self.calls.append(mint)
        return {
            "mint": mint,
            "slot": 123,
            "amount": "1000000000000000",
            "decimals": 6,
            "ui_amount": 1000000000,
            "ui_amount_string": "1000000000",
            "source": "helius_getTokenSupply",
        }


def test_load_unique_mints_dedupes_and_sorts(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "launches.jsonl",
        [{"token_mint": "mint-b"}, {"token_mint": "mint-a"}, {"token_mint": "mint-b"}],
    )

    assert load_unique_mints(path) == ["mint-a", "mint-b"]


def test_collect_token_supply_writes_supply_rows(tmp_path: Path) -> None:
    launches = _write_jsonl(tmp_path / "launches.jsonl", [{"token_mint": "mint-a"}, {"token_mint": "mint-b"}])
    adapter = FakeAdapter()

    report = collect_token_supply(
        launches_path=launches,
        output_path=tmp_path / "token_supply.jsonl",
        adapter=adapter,
        execute=True,
    )

    assert report["execute"] is True
    assert report["mints_planned"] == 2
    assert report["supply_rows_written"] == 2
    assert report["network_calls"] == 2
    assert adapter.calls == ["mint-a", "mint-b"]
    rows = [json.loads(line) for line in (tmp_path / "token_supply.jsonl").read_text().splitlines()]
    assert rows[0]["total_supply"] == 1000000000
    assert rows[0]["supply_source"] == "helius_getTokenSupply"
    assert rows[0]["supply_provenance"] == "current_spl_mint_supply"


def test_collect_token_supply_dry_run_does_not_call_adapter(tmp_path: Path) -> None:
    launches = _write_jsonl(tmp_path / "launches.jsonl", [{"token_mint": "mint-a"}])
    adapter = FakeAdapter()

    report = collect_token_supply(
        launches_path=launches,
        output_path=tmp_path / "token_supply.jsonl",
        adapter=adapter,
        execute=False,
    )

    assert report["execute"] is False
    assert report["mints_planned"] == 1
    assert report["supply_rows_written"] == 0
    assert report["network_calls"] == 0
    assert adapter.calls == []


def test_token_supply_collection_cli_dry_run(tmp_path: Path) -> None:
    launches = _write_jsonl(tmp_path / "launches.jsonl", [{"token_mint": "mint-a"}])

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_token_supply_collection",
            "--launches-path",
            str(launches),
            "--output-path",
            str(tmp_path / "token_supply.jsonl"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "execute=False" in result.stdout
    assert "network_calls=0" in result.stdout
