import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    load_census_rows,
    write_creation_census,
)
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID
from research.mtp_research.validation.parallel_historical_date_acquisition import (
    build_parallel_historical_date_acquisition_plan,
    run_parallel_historical_date_acquisition,
)


PACIFIC = ZoneInfo("America/Los_Angeles")
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class FakeParallelGtfaAdapter:
    def __init__(self, transactions_by_window: dict[tuple[int, int], list[dict]]):
        self.transactions_by_window = transactions_by_window
        self.calls = []

    def fetch_transactions_for_address_window(self, address: str, *, start_time: int, end_time: int, **kwargs) -> dict:
        self.calls.append({"address": address, "start_time": start_time, "end_time": end_time, **kwargs})
        return {
            "transactions": list(self.transactions_by_window.get((start_time, end_time), [])),
            "pagination_token": None,
        }


def _base58_encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    leading_zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeroes + (encoded or "1")


def _create_v2_tx(signature: str, block_time: int) -> dict:
    accounts = [
        f"mint-{signature}",
        "mint-authority",
        f"bonding-{signature}",
        f"assoc-bonding-{signature}",
        "global",
        f"creator-{signature}",
        "system-program",
        "token-program",
        "associated-token-program",
        "metadata-program",
        "metadata-account",
        "rent",
        "event-authority",
        PUMP_FUN_PROGRAM_ID,
        "program-15",
        "program-16",
    ]
    return {
        "slot": 100,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [{"pubkey": f"creator-{signature}", "signer": True}],
                "instructions": [
                    {
                        "programId": PUMP_FUN_PROGRAM_ID,
                        "accounts": accounts,
                        "data": _base58_encode(bytes.fromhex("d6904cec5f8b31b4") + b"payload"),
                    }
                ],
            },
        },
        "meta": {"err": None, "logMessages": ["Program log: Instruction: CreateV2"]},
    }


def _existing_census(path: Path) -> Path:
    existing_time = int(datetime(2026, 5, 25, 7, 0, tzinfo=PACIFIC).timestamp())
    write_creation_census(
        [
            PumpFunCreationCensusRow(
                mint="existing-mint",
                creator_deployer="existing-creator",
                creation_signature="existing-sig",
                slot=1,
                block_time=existing_time,
                parser_confidence="high",
                instruction_type="create_v2",
                source_method="test",
                accepted=True,
                bonding_curve="existing-bonding",
            )
        ],
        path,
    )
    return path


def test_plan_selects_prior_monday_to_wednesday_dates_and_dry_run_makes_no_calls(tmp_path: Path) -> None:
    adapter = FakeParallelGtfaAdapter({})
    census_path = _existing_census(tmp_path / "existing.jsonl")

    result = run_parallel_historical_date_acquisition(
        existing_census_path=census_path,
        output_paths=_paths(tmp_path),
        target_date_count=3,
        max_pages_per_window=2,
        request_ceiling=20,
        execute=False,
        adapter=adapter,
    )

    assert adapter.calls == []
    assert result["execution"]["mode"] == "dry_run"
    assert result["selected_dates"] == ["2026-05-18", "2026-05-19", "2026-05-20"]
    assert result["requests"]["projected_requests"] == 12
    assert result["readiness_classification"] == "parallel_acquisition_ready_for_execute"


def test_hard_stop_blocks_before_network_calls(tmp_path: Path) -> None:
    adapter = FakeParallelGtfaAdapter({})

    result = run_parallel_historical_date_acquisition(
        existing_census_path=_existing_census(tmp_path / "existing.jsonl"),
        output_paths=_paths(tmp_path),
        target_dates=["2026-05-18", "2026-05-19"],
        max_pages_per_window=5,
        request_ceiling=5,
        execute=True,
        adapter=adapter,
    )

    assert adapter.calls == []
    assert result["readiness_classification"] == "parallel_acquisition_blocked"
    assert result["requests"]["request_ceiling_status"] == "above_ceiling"


def test_execute_collects_date_shards_preserves_raw_and_writes_census(tmp_path: Path) -> None:
    morning = datetime(2026, 5, 18, 6, 0, tzinfo=PACIFIC)
    evening = datetime(2026, 5, 18, 17, 0, tzinfo=PACIFIC)
    tx1 = _create_v2_tx("sig-a", int(morning.timestamp()) + 60)
    tx2 = _create_v2_tx("sig-b", int(evening.timestamp()) + 60)
    adapter = FakeParallelGtfaAdapter(
        {
            (int(morning.timestamp()), int(datetime(2026, 5, 18, 12, 0, tzinfo=PACIFIC).timestamp())): [tx1],
            (int(evening.timestamp()), int(datetime(2026, 5, 18, 22, 0, tzinfo=PACIFIC).timestamp())): [tx2],
        }
    )
    paths = _paths(tmp_path)

    result = run_parallel_historical_date_acquisition(
        existing_census_path=_existing_census(tmp_path / "existing.jsonl"),
        output_paths=paths,
        target_dates=["2026-05-18"],
        max_pages_per_window=1,
        request_ceiling=10,
        execute=True,
        adapter=adapter,
        shard_workers=2,
    )

    rows = load_census_rows(paths["census_path"])
    raw_rows = [json.loads(line) for line in paths["raw_dir"].joinpath("date=2026-05-18.jsonl").read_text().splitlines()]
    assert result["execution"]["mode"] == "execute"
    assert result["collection"]["accepted_added"] == 2
    assert result["collection"]["transactions_seen"] == 2
    assert result["requests"]["requests_used"] == 2
    assert {row.mint for row in rows} == {"existing-mint", "mint-sig-a", "mint-sig-b"}
    assert {row["signature"] for row in raw_rows} == {"sig-a", "sig-b"}
    assert result["recommended_next_command"].startswith("./trading_env/bin/python -m research.mtp_research.ingestion.run_pumpfun_lifecycle_collection")


def test_build_plan_reports_existing_dates_and_target_gap(tmp_path: Path) -> None:
    plan = build_parallel_historical_date_acquisition_plan(
        existing_census_path=_existing_census(tmp_path / "existing.jsonl"),
        target_date_count=2,
        max_pages_per_window=3,
        request_ceiling=20,
    )

    assert plan["existing_dates"] == ["2026-05-25"]
    assert plan["selected_dates"] == ["2026-05-18", "2026-05-19"]
    assert plan["target_gap"]["additional_20k_trigger_dates_needed"] == 27
    assert plan["requests"]["projected_requests"] == 12


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "census_path": tmp_path / "parallel_census.jsonl",
        "csv_path": tmp_path / "parallel_census.csv",
        "raw_dir": tmp_path / "raw_creation_shards",
        "checkpoint_path": tmp_path / "checkpoint.json",
        "report_dir": tmp_path / "reports",
    }
