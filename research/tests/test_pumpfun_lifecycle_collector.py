from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillRequest,
    HeliusBackfillResult,
    HeliusTransactionRecord,
)
from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    write_creation_census,
)
from research.mtp_research.ingestion.pumpfun_lifecycle_collector import (
    collect_pumpfun_lifecycle,
    select_lifecycle_rows,
)
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore


PACIFIC = ZoneInfo("America/Los_Angeles")


class FakeAdapter:
    def __init__(self, signature_pages: dict[str, list[list[HeliusTransactionRecord]]], transactions: dict[str, dict]):
        self.signature_pages = signature_pages
        self.transactions = transactions
        self.requests: list[HeliusBackfillRequest] = []
        self.hydrated: list[list[str]] = []
        self.window_calls = []

    def fetch_signatures_for_address(self, request: HeliusBackfillRequest) -> HeliusBackfillResult:
        self.requests.append(request)
        pages = self.signature_pages.get(request.address, [])
        page_index = max(0, sum(1 for prior in self.requests if prior.address == request.address) - 1)
        records = pages[page_index] if page_index < len(pages) else []
        return HeliusBackfillResult(
            request=request,
            records=records,
            next_before=records[-1].signature if records else None,
        )

    def fetch_transactions(self, signatures: list[str]) -> list[dict]:
        self.hydrated.append(list(signatures))
        return [self.transactions.get(signature, {}) for signature in signatures]

    def fetch_transactions_for_address_window(self, address, *, start_time, end_time, limit=1000, pagination_token=None):
        self.window_calls.append(
            {
                "address": address,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "pagination_token": pagination_token,
            }
        )
        txs = [
            body for body in self.transactions.values()
            if start_time <= body.get("blockTime", 0) <= end_time
        ]
        return {"transactions": txs[:limit], "pagination_token": None}


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=PACIFIC).timestamp())


def _row(mint: str, block_time: int, bonding_curve: str = "curve") -> PumpFunCreationCensusRow:
    return PumpFunCreationCensusRow(
        mint=mint,
        creator_deployer=f"creator-{mint}",
        creation_signature=f"create-{mint}",
        slot=1,
        block_time=block_time,
        parser_confidence="high",
        instruction_type="create_v2",
        source_method="test",
        accepted=True,
        bonding_curve=bonding_curve,
    )


def _record(signature: str, block_time: int) -> HeliusTransactionRecord:
    return HeliusTransactionRecord(
        signature=signature,
        slot=1,
        block_time=block_time,
        success=True,
        raw_json={"signature": signature, "blockTime": block_time},
    )


def test_select_lifecycle_rows_supports_existing_and_regime_lanes(tmp_path: Path) -> None:
    rows = [
        _row("existing", _ts(2026, 5, 31, 22)),
        _row("regime", _ts(2026, 6, 1, 6)),
    ]

    assert [row.mint for row in select_lifecycle_rows(rows, lane="existing", limit=2)] == ["existing", "regime"]
    assert [row.mint for row in select_lifecycle_rows(rows, lane="regime", limit=2)] == ["regime"]


def test_lifecycle_collector_hydrates_only_first_two_hour_signatures(tmp_path: Path) -> None:
    launch_ts = _ts(2026, 6, 1, 6)
    census_path = tmp_path / "census.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    write_creation_census([_row("mint", launch_ts, bonding_curve="curve-1")], census_path)
    adapter = FakeAdapter(
        signature_pages={
            "curve-1": [
                [
                    _record("too-new", launch_ts + 8000),
                    _record("inside-2", launch_ts + 120),
                    _record("inside-1", launch_ts + 30),
                    _record("too-old", launch_ts - 1),
                ]
            ]
        },
        transactions={
            "inside-1": {"slot": 1, "blockTime": launch_ts + 30, "meta": {"err": None}},
            "inside-2": {"slot": 2, "blockTime": launch_ts + 120, "meta": {"err": None}},
        },
    )

    summary = collect_pumpfun_lifecycle(
        census_path=census_path,
        raw_path=raw_path,
        lane="existing",
        target_launches=1,
        adapter=adapter,
        execute=True,
        signatures_per_page=10,
        max_signature_pages_per_launch=1,
        max_transactions_per_launch=10,
    )

    assert summary["launches_processed"] == 1
    assert summary["signatures_in_window"] == 2
    assert summary["transactions_fetched"] == 2
    assert summary["raw_inserted"] == 2
    assert adapter.hydrated == [["inside-2", "inside-1"]]
    assert {record.signature for record in RawTransactionStore(raw_path).load_all()} == {"inside-1", "inside-2"}


def test_lifecycle_collector_dry_run_makes_no_network_calls(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    write_creation_census([_row("mint", _ts(2026, 6, 1, 6), bonding_curve="curve-1")], census_path)

    summary = collect_pumpfun_lifecycle(
        census_path=census_path,
        raw_path=tmp_path / "raw.jsonl",
        lane="regime",
        target_launches=1,
        execute=False,
    )

    assert summary["selected_launches"] == 1
    assert summary["estimated_signature_requests"] == 1
    assert summary["estimated_transaction_requests_up_to"] == 100
    assert summary["network_calls"] == 0


def test_lifecycle_collector_can_use_address_window_method_to_avoid_per_signature_hydration(tmp_path: Path) -> None:
    launch_ts = _ts(2026, 6, 1, 6)
    census_path = tmp_path / "census.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    write_creation_census([_row("mint", launch_ts, bonding_curve="curve-1")], census_path)
    adapter = FakeAdapter(
        signature_pages={},
        transactions={
            "inside-1": {"slot": 1, "blockTime": launch_ts + 30, "meta": {"err": None}, "transaction": {"signatures": ["inside-1"]}},
            "inside-2": {"slot": 2, "blockTime": launch_ts + 120, "meta": {"err": None}, "transaction": {"signatures": ["inside-2"]}},
        },
    )

    summary = collect_pumpfun_lifecycle(
        census_path=census_path,
        raw_path=raw_path,
        lane="existing",
        target_launches=1,
        adapter=adapter,
        execute=True,
        collection_method="address_window",
        max_transactions_per_launch=10,
    )

    assert summary["network_calls"] == 1
    assert summary["transactions_fetched"] == 2
    assert summary["raw_inserted"] == 2
    assert adapter.requests == []
    assert adapter.hydrated == []
    assert adapter.window_calls[0]["address"] == "curve-1"
