from __future__ import annotations

import base64
import struct

from research.mtp_research.validation.t007_protocol_idl_registry import (
    PUMP_FUN_PROGRAM_ID,
    PUMPSWAP_PROGRAM_ID,
    load_protocol_idl_registry,
)
from research.mtp_research.validation.t007_pump_pumpswap_decoders import (
    b58encode_pubkey,
    decode_pool_account_snapshot,
    decode_protocol_instruction_event,
)


def _instruction(program: str, name: str, accounts_by_name: dict[str, str]) -> dict:
    registry = load_protocol_idl_registry()
    meta = registry.instruction_by_name(program, name)
    accounts = [accounts_by_name.get(account_name, f"acct-{account_name}") for account_name in meta.account_names]
    return {
        "programId": registry.program_id(program),
        "accounts": accounts,
        "data": base64.b64encode(meta.discriminator + b"payload").decode("ascii"),
    }


def test_pumpswap_create_pool_instruction_decodes_as_level_a_migration() -> None:
    row = decode_protocol_instruction_event(
        program_id=PUMPSWAP_PROGRAM_ID,
        instruction=_instruction(
            "pump_amm",
            "create_pool",
            {
                "pool": "pool111111111111111111111111111111111111111",
                "base_mint": "mint111111111111111111111111111111111111111",
                "quote_mint": "So11111111111111111111111111111111111111112",
                "pool_base_token_account": "baseVault111111111111111111111111111111111",
                "pool_quote_token_account": "quoteVault1111111111111111111111111111111",
                "creator": "creator11111111111111111111111111111111111",
            },
        ),
        signature="sig-create-pool",
        slot=55,
        instruction_index=3,
        observed_at=1000.5,
    )

    assert row is not None
    assert row["event_family"] == "migration"
    assert row["migration_evidence_level"] == "LEVEL_A"
    assert row["detection_method"] == "pumpswap_create_pool_instruction"
    assert row["source_lane"] == "pumpswap_create_pool_lane"
    assert row["lifecycle_state"] == "MIGRATION_CONFIRMED_LEVEL_A"
    assert row["mint"] == "mint111111111111111111111111111111111111111"
    assert row["pool_or_pair_address"] == "pool111111111111111111111111111111111111111"
    assert row["quote_asset"] == "SOL"
    assert row["trade_data_eligible"] is False


def test_pump_migrate_v2_instruction_decodes_as_level_a_migration() -> None:
    row = decode_protocol_instruction_event(
        program_id=PUMP_FUN_PROGRAM_ID,
        instruction=_instruction(
            "pump",
            "migrate_v2",
            {
                "pool": "pool222222222222222222222222222222222222222",
                "base_mint": "mint222222222222222222222222222222222222222",
                "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "pool_base_token_account": "baseVault222222222222222222222222222222222",
                "pool_quote_token_account": "quoteVault2222222222222222222222222222222",
            },
        ),
        signature="sig-migrate-v2",
        slot=56,
        instruction_index=1,
        observed_at=1001.5,
    )

    assert row is not None
    assert row["migration_evidence_level"] == "LEVEL_A"
    assert row["detection_method"] == "pumpfun_migrate_v2_instruction"
    assert row["source_lane"] == "pumpfun_migration_lane"
    assert row["mint"] == "mint222222222222222222222222222222222222222"
    assert row["quote_asset"] == "USDC"


def test_pumpswap_swap_instruction_is_context_not_migration_proof() -> None:
    row = decode_protocol_instruction_event(
        program_id=PUMPSWAP_PROGRAM_ID,
        instruction=_instruction("pump_amm", "buy", {"pool": "pool333", "base_mint": "mint333"}),
        signature="sig-buy",
        slot=57,
        instruction_index=0,
        observed_at=1002.5,
    )

    assert row is not None
    assert row["event_family"] == "post_migration_swap_context"
    assert row["migration_evidence_level"] == "NONE"
    assert row["migration_confirmed"] is False
    assert row["trade_data_eligible"] is False


def test_pool_account_snapshot_decodes_pool_metadata() -> None:
    registry = load_protocol_idl_registry()
    disc = registry.account_by_name("pump_amm", "Pool").discriminator
    pubkeys = [bytes([value]) * 32 for value in range(1, 7)]
    coin_creator = bytes([7]) * 32
    data = b"".join(
        [
            disc,
            struct.pack("<B", 9),
            struct.pack("<H", 0),
            *pubkeys,
            struct.pack("<Q", 123456),
            coin_creator,
            b"\x00",
            b"\x01",
        ]
    )

    row = decode_pool_account_snapshot("pool-pubkey", data, slot=99, observed_at=1003.5)

    assert row["pool_or_pair_address"] == "pool-pubkey"
    assert row["pool_account_decode_status"] == "decoded"
    assert row["pool_index"] == 0
    assert row["creator"] == b58encode_pubkey(pubkeys[0])
    assert row["base_mint"] == b58encode_pubkey(pubkeys[1])
    assert row["quote_mint"] == b58encode_pubkey(pubkeys[2])
    assert row["pool_base_token_account"] == b58encode_pubkey(pubkeys[4])
    assert row["pool_quote_token_account"] == b58encode_pubkey(pubkeys[5])
    assert row["is_cashback_coin"] is True
