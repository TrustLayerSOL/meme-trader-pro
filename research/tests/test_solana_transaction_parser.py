from datetime import datetime, timezone

from research.mtp_research.ingestion.basic_transaction_normalizer import (
    transaction_summary_to_observed_event,
)
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.ingestion.solana_transaction_parser import (
    extract_account_summaries,
    extract_program_invocations,
    extract_token_balance_deltas,
    summarize_raw_transaction,
)
from research.mtp_research.ingestion.transaction_parser_models import VenueClassification


def _mock_raw_json() -> dict:
    return {
        "slot": 42,
        "blockTime": 1_700_000_000,
        "transaction": {
            "signatures": ["sig-1"],
            "message": {
                "accountKeys": [
                    {"pubkey": "wallet-1", "signer": True, "writable": True, "source": "transaction"},
                    {"pubkey": "token-account-1", "signer": False, "writable": True},
                    {"pubkey": "program-1", "signer": False, "writable": False},
                ],
                "instructions": [
                    {
                        "programId": "program-1",
                        "program": "spl-token",
                        "parsed": {"type": "transferChecked"},
                    }
                ],
            },
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "innerInstructions": [
                {
                    "index": 0,
                    "instructions": [
                        {
                            "programId": "inner-program-1",
                            "program": "system",
                            "parsed": {"type": "transfer"},
                        }
                    ],
                }
            ],
            "preTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": "mint-1",
                    "owner": "wallet-1",
                    "uiTokenAmount": {
                        "uiAmount": 1.0,
                        "uiAmountString": "1",
                        "decimals": 6,
                    },
                }
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": "mint-1",
                    "owner": "wallet-1",
                    "uiTokenAmount": {
                        "uiAmount": 3.5,
                        "uiAmountString": "3.5",
                        "decimals": 6,
                    },
                }
            ],
        },
    }


def _raw_record(raw_json: dict | None = None) -> RawTransactionRecord:
    return RawTransactionRecord(
        signature="sig-1",
        slot=42,
        block_time=1_700_000_000,
        success=True,
        fetched_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
        raw_json=raw_json or _mock_raw_json(),
    )


def test_account_summaries_parse_from_json_parsed_transaction() -> None:
    accounts = extract_account_summaries(_mock_raw_json())

    assert accounts[0].pubkey == "wallet-1"
    assert accounts[0].signer is True
    assert accounts[0].writable is True
    assert accounts[0].source == "transaction"


def test_top_level_and_inner_program_invocations_parse() -> None:
    programs = extract_program_invocations(_mock_raw_json())

    assert programs[0].program_id == "program-1"
    assert programs[0].instruction_type == "transferChecked"
    assert programs[0].index == 0
    assert programs[0].inner_index is None
    assert programs[1].program_id == "inner-program-1"
    assert programs[1].instruction_type == "transfer"
    assert programs[1].index == 0
    assert programs[1].inner_index == 0


def test_token_balance_deltas_calculate_correctly() -> None:
    deltas = extract_token_balance_deltas(_mock_raw_json())

    assert len(deltas) == 1
    assert deltas[0].owner == "wallet-1"
    assert deltas[0].account == "token-account-1"
    assert deltas[0].mint == "mint-1"
    assert deltas[0].pre_amount == 1.0
    assert deltas[0].post_amount == 3.5
    assert deltas[0].delta == 2.5
    assert deltas[0].decimals == 6


def test_missing_meta_or_transaction_fields_do_not_crash() -> None:
    raw_json = {"slot": 1}

    assert extract_account_summaries(raw_json) == []
    assert extract_program_invocations(raw_json) == []
    assert extract_token_balance_deltas(raw_json) == []

    summary = summarize_raw_transaction(_raw_record(raw_json))
    assert summary.signature == "sig-1"
    assert summary.accounts == []
    assert summary.programs == []
    assert summary.token_balance_deltas == []


def test_transaction_summary_to_observed_event_includes_parser_metadata() -> None:
    summary = summarize_raw_transaction(_raw_record())
    summary.venue_classification = VenueClassification(
        venue="unknown_token_swap_candidate",
        confidence=0.3,
        reasons=["token_balance_deltas_present_without_known_venue"],
    )

    event = transaction_summary_to_observed_event(summary)

    assert event.event_type == "transaction_observed"
    assert event.venue == "unknown_token_swap_candidate"
    assert event.metadata_json["fee_lamports"] == 5000
    assert event.metadata_json["program_ids"] == ["program-1", "inner-program-1"]
    assert event.metadata_json["token_balance_delta_count"] == 1
    assert event.metadata_json["venue_confidence"] == 0.3
    assert event.metadata_json["venue_reasons"] == [
        "token_balance_deltas_present_without_known_venue"
    ]
