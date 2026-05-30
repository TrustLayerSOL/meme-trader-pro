from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)
from research.mtp_research.ingestion.run_normalize_trade_events import main
from research.mtp_research.ingestion.trade_normalization_models import WSOL_MINT


BASE_MINT = "BaseMint111111111111111111111111111111111111"


def _raw_json() -> dict:
    return {
        "slot": 42,
        "blockTime": 1_700_000_000,
        "transaction": {
            "signatures": ["sig-1"],
            "message": {
                "accountKeys": [
                    {"pubkey": "owner-1", "signer": True, "writable": True},
                    {"pubkey": "base-account", "signer": False, "writable": True},
                    {"pubkey": "quote-account", "signer": False, "writable": True},
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
                    "mint": BASE_MINT,
                    "owner": "owner-1",
                    "uiTokenAmount": {"uiAmountString": "1", "decimals": 6},
                },
                {
                    "accountIndex": 2,
                    "mint": WSOL_MINT,
                    "owner": "owner-1",
                    "uiTokenAmount": {"uiAmountString": "5", "decimals": 9},
                },
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": BASE_MINT,
                    "owner": "owner-1",
                    "uiTokenAmount": {"uiAmountString": "3", "decimals": 6},
                },
                {
                    "accountIndex": 2,
                    "mint": WSOL_MINT,
                    "owner": "owner-1",
                    "uiTokenAmount": {"uiAmountString": "4", "decimals": 9},
                },
            ],
        },
    }


def test_run_normalize_trade_events_cli_writes_trade_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    raw_path = tmp_path / "raw.jsonl"
    events_path = tmp_path / "events.jsonl"
    RawTransactionStore(path=raw_path).upsert(
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
            "run_normalize_trade_events",
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
    assert "trade_events_inserted=1" in output
    assert "possible_buy" in output

    events = NormalizedEventStore(path=events_path).load_all()
    assert len(events) == 1
    assert events[0].event_type == "possible_buy"
    assert events[0].token_mint == BASE_MINT
    assert events[0].metadata_json["quote_mint"] == WSOL_MINT
    assert events[0].metadata_json["parser_version"] == "trade_event_normalizer_v0"
