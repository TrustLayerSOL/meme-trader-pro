from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)
from research.mtp_research.ingestion.run_parse_raw_transactions import main


def _raw_json() -> dict:
    return {
        "slot": 42,
        "blockTime": 1_700_000_000,
        "transaction": {
            "signatures": ["sig-1"],
            "message": {
                "accountKeys": [
                    {"pubkey": "wallet-1", "signer": True, "writable": True},
                    {"pubkey": "token-account-1", "signer": False, "writable": True},
                ],
                "instructions": [],
            },
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "preTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": "mint-1",
                    "owner": "wallet-1",
                    "uiTokenAmount": {"uiAmountString": "1", "decimals": 6},
                }
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": "mint-1",
                    "owner": "wallet-1",
                    "uiTokenAmount": {"uiAmountString": "2", "decimals": 6},
                }
            ],
        },
    }


def test_parse_raw_transactions_cli_writes_normalized_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    raw_path = tmp_path / "raw.jsonl"
    events_path = tmp_path / "events.jsonl"
    raw_store = RawTransactionStore(path=raw_path)
    raw_store.upsert(
        RawTransactionRecord(
            signature="sig-1",
            slot=42,
            block_time=1_700_000_000,
            success=True,
            fetched_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
            raw_json=_raw_json(),
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_parse_raw_transactions",
            "--raw-path",
            str(raw_path),
            "--events-path",
            str(events_path),
            "--limit",
            "100",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "raw_records_processed=1" in output
    assert "events_inserted=1" in output
    assert "unknown_token_swap_candidate" in output

    events = NormalizedEventStore(path=events_path).load_all()
    assert len(events) == 1
    assert events[0].signature == "sig-1"
    assert events[0].venue == "unknown_token_swap_candidate"
