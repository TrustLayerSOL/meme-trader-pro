from __future__ import annotations

from research.mtp_research.validation.t007_protocol_idl_registry import (
    PUMP_FUN_PROGRAM_ID,
    PUMPSWAP_PROGRAM_ID,
    ProtocolIdlRegistry,
    load_protocol_idl_registry,
)


def test_registry_loads_official_pump_and_pumpswap_idls() -> None:
    registry = load_protocol_idl_registry()

    assert isinstance(registry, ProtocolIdlRegistry)
    assert registry.program_id("pump") == PUMP_FUN_PROGRAM_ID
    assert registry.program_id("pump_amm") == PUMPSWAP_PROGRAM_ID
    assert registry.idl_checksum("pump") == "b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49"
    assert registry.idl_checksum("pump_amm") == "cd5c58a5dded23632aedb993b08cc0d2ba91bda2bb084560913464274d3bee50"

    registry.require_instruction("pump", "create_v2")
    registry.require_instruction("pump", "migrate_v2")
    registry.require_instruction("pump_amm", "create_pool")
    registry.require_event("pump_amm", "CreatePoolEvent")
    registry.require_account("pump_amm", "Pool")


def test_registry_builds_anchor_discriminator_maps() -> None:
    registry = load_protocol_idl_registry()

    create_pool = registry.instruction_by_name("pump_amm", "create_pool")
    migrate_v2 = registry.instruction_by_name("pump", "migrate_v2")
    pool_account = registry.account_by_name("pump_amm", "Pool")

    assert registry.classify_instruction("pump_amm", create_pool.discriminator).name == "create_pool"
    assert registry.classify_instruction("pump", migrate_v2.discriminator).name == "migrate_v2"
    assert registry.classify_account("pump_amm", pool_account.discriminator).name == "Pool"
    assert "pool_base_token_account" in create_pool.account_names
    assert "pool_quote_token_account" in migrate_v2.account_names
