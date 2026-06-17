from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from research.mtp_research.validation.t007_protocol_idl_registry import PUMPSWAP_PROGRAM_ID, load_protocol_idl_registry
from research.mtp_research.validation.t007_pumpswap_gap_backfill import (
    PumpSwapGapBackfillClient,
    run_pumpswap_gap_backfill,
)


class FakeClient(PumpSwapGapBackfillClient):
    def __init__(self, tx_by_sig: dict[str, dict]) -> None:
        self.tx_by_sig = tx_by_sig
        self.calls: list[dict] = []

    def fetch_signatures_for_address(self, address: str, *, limit: int, before: str | None = None, until: str | None = None) -> list[dict]:
        assert address == PUMPSWAP_PROGRAM_ID
        self.calls.append({"address": address, "limit": limit, "before": before, "until": until})
        return [{"signature": sig, "slot": idx + 1} for idx, sig in enumerate(self.tx_by_sig)][:limit]

    def fetch_transaction(self, signature: str) -> dict:
        return self.tx_by_sig.get(signature, {})


def _create_pool_tx(signature: str, mint: str, pool: str) -> dict:
    registry = load_protocol_idl_registry()
    meta = registry.instruction_by_name("pump_amm", "create_pool")
    accounts_by_name = {
        "pool": pool,
        "base_mint": mint,
        "quote_mint": "So11111111111111111111111111111111111111112",
        "pool_base_token_account": "baseVaultBackfill111111111111111111111111111",
        "pool_quote_token_account": "quoteVaultBackfill11111111111111111111111111",
        "creator": "creatorBackfill1111111111111111111111111111",
    }
    accounts = [accounts_by_name.get(name, f"acct-{name}") for name in meta.account_names]
    return {
        "slot": 123,
        "blockTime": 456,
        "transaction": {
            "signatures": [signature],
            "message": {
                "instructions": [
                    {
                        "programId": PUMPSWAP_PROGRAM_ID,
                        "accounts": accounts,
                        "data": base64.b64encode(meta.discriminator + b"payload").decode("ascii"),
                    }
                ]
            },
        },
        "meta": {"err": None, "innerInstructions": []},
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_gap_backfill_requires_explicit_read_only_flag(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit"):
        run_pumpswap_gap_backfill(
            tmp_path,
            client=FakeClient({}),
            explicit_read_only_rpc_flag=False,
            max_signatures=10,
        )


def test_gap_backfill_fetches_transactions_and_writes_level_a_migration(tmp_path: Path) -> None:
    signature = "sig-backfill-create-pool"
    client = FakeClient({signature: _create_pool_tx(signature, "mint-backfill", "pool-backfill")})

    result = run_pumpswap_gap_backfill(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_signatures=10,
    )

    assert result["signatures_found"] == 1
    assert result["transactions_fetched"] == 1
    assert result["level_a_migrations_backfilled"] == 1
    migration_rows = [json.loads(line) for line in (tmp_path / "migration_events.jsonl").read_text().splitlines() if line.strip()]
    assert migration_rows[0]["migration_evidence_level"] == "LEVEL_A"
    assert migration_rows[0]["detection_method"] == "pumpswap_create_pool_instruction"
    assert migration_rows[0]["backfilled_from_read_only_rpc"] is True
    source_gap = _read_json(tmp_path / "source_gap_health.json")
    assert source_gap["source_gap_gate_passed"] is True
    assert source_gap["backfill_succeeded"] is True
    assert source_gap["unbackfilled_gap_count"] == 0


def test_gap_backfill_does_not_clear_gap_when_fetches_fail(tmp_path: Path) -> None:
    class BrokenClient(FakeClient):
        def fetch_transaction(self, signature: str) -> dict:
            return {}

    result = run_pumpswap_gap_backfill(
        tmp_path,
        client=BrokenClient({"sig-missing": {"present": False}}),
        explicit_read_only_rpc_flag=True,
        max_signatures=10,
    )

    assert result["transaction_fetch_failures"] == 1
    source_gap = _read_json(tmp_path / "source_gap_health.json")
    assert source_gap["source_gap_gate_passed"] is False
    assert source_gap["unbackfilled_gap_count"] == 1
    assert "backfill_transaction_fetch_failures" in source_gap["source_gap_blocking_reasons"]


def test_gap_backfill_uses_exact_gap_interval_bounds(tmp_path: Path) -> None:
    signature = "sig-between-gap"
    client = FakeClient({signature: _create_pool_tx(signature, "mint-interval", "pool-interval")})
    (tmp_path / "source_gap_health.json").write_text(
        json.dumps(
            {
                "source_gap_gate_passed": False,
                "unbackfilled_gap_count": 1,
                "source_gap_intervals": [
                    {
                        "last_seen_signature_before_gap": "sig-before-gap",
                        "first_seen_signature_after_gap": "sig-after-gap",
                        "last_seen_slot_before_gap": 100,
                        "first_seen_slot_after_gap": 105,
                        "backfill_status": "not_attempted",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_pumpswap_gap_backfill(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_signatures=10,
    )

    assert result["intervals_backfilled"] == 1
    assert result["cap_exhausted"] is False
    assert client.calls == [
        {
            "address": PUMPSWAP_PROGRAM_ID,
            "limit": 10,
            "before": "sig-after-gap",
            "until": "sig-before-gap",
        }
    ]
    source_gap = _read_json(tmp_path / "source_gap_health.json")
    assert source_gap["source_gap_gate_passed"] is True
    assert source_gap["source_gap_intervals"][0]["backfill_status"] == "succeeded"
