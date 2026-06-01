from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.pumpfun_gtfa_census_collection import (
    collect_pumpfun_regime_census_with_gtfa,
    regime_windows,
)
from research.mtp_research.ingestion.pumpfun_creation_census import load_census_rows
from research.mtp_research.ingestion.run_program_signature_probe import PUMP_FUN_PROGRAM_ID


PACIFIC = ZoneInfo("America/Los_Angeles")
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class FakeGtfaAdapter:
    def __init__(self, transactions):
        self.transactions = transactions
        self.calls = []

    def fetch_transactions_for_address_window(self, address, *, start_time, end_time, limit=1000, pagination_token=None):
        self.calls.append(
            {
                "address": address,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "pagination_token": pagination_token,
            }
        )
        return {"transactions": self.transactions, "pagination_token": None}


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


def test_regime_windows_include_requested_weekdays_and_time_blocks() -> None:
    windows = regime_windows(start_date=date(2026, 6, 1), end_date=date(2026, 6, 3))
    labels = [(start.astimezone(PACIFIC).strftime("%A %H:%M"), end.astimezone(PACIFIC).strftime("%H:%M")) for start, end in windows]

    assert labels == [
        ("Monday 06:00", "12:00"),
        ("Monday 17:00", "22:00"),
        ("Tuesday 06:00", "12:00"),
        ("Tuesday 17:00", "22:00"),
        ("Wednesday 06:00", "12:00"),
        ("Wednesday 17:00", "22:00"),
    ]


def test_gtfa_census_collection_writes_verified_create_rows(tmp_path: Path) -> None:
    start = datetime(2026, 6, 1, 6, 0, tzinfo=PACIFIC)
    tx = _create_v2_tx("sig-1", int(start.timestamp()) + 60)
    adapter = FakeGtfaAdapter([tx])
    output_path = tmp_path / "census.jsonl"
    csv_path = tmp_path / "census.csv"

    summary = collect_pumpfun_regime_census_with_gtfa(
        adapter=adapter,
        output_path=output_path,
        csv_output_path=csv_path,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        target_regime_launches=1,
        execute=True,
    )

    rows = load_census_rows(output_path)
    assert summary["accepted_regime_launches"] == 1
    assert summary["transactions_seen"] == 1
    assert len(rows) == 1
    assert rows[0].mint == "mint-sig-1"
    assert rows[0].creator_deployer == "creator-sig-1"
    assert rows[0].source_method == "pumpfun_gtfa_regime_census_collection"


def test_gtfa_census_collection_dry_run_makes_no_network_calls(tmp_path: Path) -> None:
    summary = collect_pumpfun_regime_census_with_gtfa(
        output_path=tmp_path / "census.jsonl",
        csv_output_path=tmp_path / "census.csv",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        target_regime_launches=1500,
        execute=False,
    )

    assert summary["window_count"] == 6
    assert summary["network_calls"] == 0
    assert summary["target_regime_launches"] == 1500
