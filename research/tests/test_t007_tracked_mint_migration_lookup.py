from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import pytest

from research.mtp_research.validation.t007_lifecycle_readiness_gate_v2 import evaluate_t007_lifecycle_readiness_v2
from research.mtp_research.validation.t007_protocol_idl_registry import PUMPSWAP_PROGRAM_ID, load_protocol_idl_registry
from research.mtp_research.validation.t007_tracked_mint_migration_lookup import (
    TrackedMintMigrationLookupClient,
    run_tracked_mint_migration_lookup,
)


class FakeTrackedLookupClient(TrackedMintMigrationLookupClient):
    def __init__(self, tx_by_address: dict[str, list[dict]]) -> None:
        self.tx_by_address = tx_by_address
        self.calls: list[dict] = []

    def fetch_transactions_for_address(self, address: str, *, limit: int, slot_gte: int | None = None, slot_lte: int | None = None) -> list[dict]:
        self.calls.append({"address": address, "limit": limit, "slot_gte": slot_gte, "slot_lte": slot_lte})
        return list(self.tx_by_address.get(address, []))[:limit]

    def fetch_account_info(self, address: str) -> bytes | None:
        return None


class FakeTrackedLookupClientWithPool(FakeTrackedLookupClient):
    def __init__(self, tx_by_address: dict[str, list[dict]], pool_data_by_address: dict[str, bytes]) -> None:
        super().__init__(tx_by_address)
        self.pool_data_by_address = pool_data_by_address

    def fetch_account_info(self, address: str) -> bytes | None:
        return self.pool_data_by_address.get(address)


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _create_pool_tx(signature: str, mint: str, pool: str) -> dict:
    registry = load_protocol_idl_registry()
    meta = registry.instruction_by_name("pump_amm", "create_pool")
    accounts_by_name = {
        "pool": pool,
        "base_mint": mint,
        "quote_mint": "So11111111111111111111111111111111111111112",
        "pool_base_token_account": "baseVaultTracked111111111111111111111111111",
        "pool_quote_token_account": "quoteVaultTracked11111111111111111111111111",
        "creator": "creatorTracked1111111111111111111111111111",
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


def _pumpswap_buy_tx(signature: str, mint: str, pool: str) -> dict:
    registry = load_protocol_idl_registry()
    meta = registry.instruction_by_name("pump_amm", "buy")
    accounts_by_name = {"pool": pool, "base_mint": mint}
    accounts = [accounts_by_name.get(name, f"acct-{name}") for name in meta.account_names]
    return {
        "slot": 124,
        "blockTime": 457,
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


def _pool_account_data() -> bytes:
    registry = load_protocol_idl_registry()
    disc = registry.account_by_name("pump_amm", "Pool").discriminator
    pubkeys = [bytes([value]) * 32 for value in range(1, 7)]
    coin_creator = bytes([7]) * 32
    return b"".join(
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


def test_tracked_lookup_requires_explicit_read_only_rpc(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit"):
        run_tracked_mint_migration_lookup(
            tmp_path,
            client=FakeTrackedLookupClient({}),
            explicit_read_only_rpc_flag=False,
            max_transactions_per_address=10,
        )


def test_tracked_lookup_client_reads_helius_result_data_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer

    calls: list[dict] = []

    def fake_post_json_rpc(url: str, payload: dict, timeout_seconds: int) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {"jsonrpc": "2.0", "result": {"data": [{"signature": "sig-data-shape", "slot": 123}]}}

    monkeypatch.setattr(observer, "_post_json_rpc", fake_post_json_rpc)
    client = TrackedMintMigrationLookupClient(rpc_url="https://helius.example", timeout_seconds=7)

    rows = client.fetch_transactions_for_address("mint-data-shape", limit=25, slot_gte=100, slot_lte=200)

    assert rows == [{"signature": "sig-data-shape", "slot": 123}]
    assert calls[0]["payload"]["method"] == "getTransactionsForAddress"
    assert calls[0]["payload"]["params"][1]["transactionDetails"] == "full"
    assert calls[0]["payload"]["params"][1]["encoding"] == "jsonParsed"
    assert calls[0]["payload"]["params"][1]["filters"]["slot"] == {"gte": 100, "lte": 200}
    assert calls[0]["timeout_seconds"] == 7


def test_tracked_lookup_client_follows_helius_pagination_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer

    calls: list[dict] = []

    def fake_post_json_rpc(url: str, payload: dict, timeout_seconds: int) -> dict:
        calls.append(payload)
        if len(calls) == 1:
            return {"jsonrpc": "2.0", "result": {"data": [{"signature": "sig-page-1"}], "paginationToken": "page-2"}}
        return {"jsonrpc": "2.0", "result": {"data": [{"signature": "sig-page-2"}]}}

    monkeypatch.setattr(observer, "_post_json_rpc", fake_post_json_rpc)
    client = TrackedMintMigrationLookupClient(rpc_url="https://helius.example")

    rows = client.fetch_transactions_for_address("mint-paged", limit=2)

    assert [row["signature"] for row in rows] == ["sig-page-1", "sig-page-2"]
    assert calls[1]["params"][1]["paginationToken"] == "page-2"


def test_tracked_lookup_client_raises_on_rpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer

    def fake_post_json_rpc(url: str, payload: dict, timeout_seconds: int) -> dict:
        return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "method not found"}}

    monkeypatch.setattr(observer, "_post_json_rpc", fake_post_json_rpc)
    client = TrackedMintMigrationLookupClient(rpc_url="https://helius.example")

    with pytest.raises(RuntimeError, match="getTransactionsForAddress"):
        client.fetch_transactions_for_address("mint-error", limit=10)


def test_tracked_lookup_resolves_level_a_for_tracked_mint_and_writes_event_sourced_artifacts(tmp_path: Path) -> None:
    _append(
        tmp_path / "tracked_mint_registry.jsonl",
        {
            "mint": "mint-tracked",
            "birth_signature": "birth-sig",
            "birth_slot": 100,
            "bonding_curve": "curve-tracked",
            "associated_bonding_curve": "abc-tracked",
            "creator": "creator-tracked",
            "graduation_candidate": True,
        },
    )
    client = FakeTrackedLookupClient({"mint-tracked": [_create_pool_tx("sig-create-pool", "mint-tracked", "pool-tracked")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    assert summary["tracked_mint_lookup_gate_passed"] is True
    assert summary["level_a_migrations_resolved"] == 1
    assert summary["migration_lookup_terminal_count"] == 1
    assert (tmp_path / "raw_observations.jsonl").exists()
    migration_rows = [json.loads(line) for line in (tmp_path / "migration_events.jsonl").read_text().splitlines() if line.strip()]
    assert migration_rows[0]["mint"] == "mint-tracked"
    assert migration_rows[0]["migration_evidence_level"] == "LEVEL_A"
    binding_rows = [json.loads(line) for line in (tmp_path / "pool_binding_results.jsonl").read_text().splitlines() if line.strip()]
    assert binding_rows[0]["pool_binding_confidence"] == "confirmed"
    assert binding_rows[0]["pool_or_pair_address"] == "pool-tracked"


def test_tracked_lookup_fetches_pool_account_snapshot_for_level_a_pool(tmp_path: Path) -> None:
    _append(
        tmp_path / "tracked_mint_registry.jsonl",
        {
            "mint": "mint-with-pool",
            "bonding_curve": "curve-with-pool",
            "graduation_candidate": True,
        },
    )
    client = FakeTrackedLookupClientWithPool(
        {"mint-with-pool": [_create_pool_tx("sig-create-pool-state", "mint-with-pool", "pool-with-state")]},
        {"pool-with-state": _pool_account_data()},
    )

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    assert summary["pool_account_snapshots_fetched"] == 1
    pool_rows = [json.loads(line) for line in (tmp_path / "pool_state_snapshots.jsonl").read_text().splitlines() if line.strip()]
    assert pool_rows[0]["pool_or_pair_address"] == "pool-with-state"
    assert pool_rows[0]["pool_account_decode_status"] == "decoded"


def test_tracked_lookup_only_queries_high_progress_candidates_with_slot_window(tmp_path: Path) -> None:
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-low", "bonding_curve": "curve-low"})
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-high", "bonding_curve": "curve-high"})
    _append(
        tmp_path / "true_curve_threshold_crossings.jsonl",
        {
            "mint": "mint-low",
            "threshold_pct": 90.0,
            "crossing_slot": 1000,
            "progress_pct": 90.0,
        },
    )
    _append(
        tmp_path / "true_curve_threshold_crossings.jsonl",
        {
            "mint": "mint-high",
            "threshold_pct": 95.0,
            "crossing_slot": 2000,
            "progress_pct": 95.0,
        },
    )
    client = FakeTrackedLookupClient({"mint-high": [_create_pool_tx("sig-high", "mint-high", "pool-high")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    called_addresses = {call["address"] for call in client.calls}
    assert "mint-low" not in called_addresses
    assert "curve-low" not in called_addresses
    assert "mint-high" in called_addresses
    high_mint_call = next(call for call in client.calls if call["address"] == "mint-high")
    assert high_mint_call["slot_gte"] == 0
    assert high_mint_call["slot_lte"] == 22000
    assert summary["graduation_candidates_total"] == 1


def test_tracked_lookup_rejects_wrong_mint_as_not_migrated(tmp_path: Path) -> None:
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-wanted", "graduation_candidate": True})
    client = FakeTrackedLookupClient({"mint-wanted": [_create_pool_tx("sig-wrong", "mint-other", "pool-other")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    assert summary["tracked_mint_lookup_gate_passed"] is True
    assert summary["level_a_migrations_resolved"] == 0
    result_rows = [json.loads(line) for line in (tmp_path / "migration_lookup_results.jsonl").read_text().splitlines() if line.strip()]
    assert result_rows[-1]["lookup_status"] == "NOT_MIGRATED_WITHIN_WINDOW"
    assert not (tmp_path / "migration_events.jsonl").exists()


def test_tracked_lookup_skips_non_graduation_candidates_without_rpc(tmp_path: Path) -> None:
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-skip", "graduation_candidate": False})
    client = FakeTrackedLookupClient({"mint-skip": [_create_pool_tx("sig-should-not-fetch", "mint-skip", "pool-skip")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    assert client.calls == []
    assert summary["tracked_mint_lookup_gate_passed"] is True
    result_rows = [json.loads(line) for line in (tmp_path / "migration_lookup_results.jsonl").read_text().splitlines() if line.strip()]
    assert result_rows[-1]["lookup_status"] == "NOT_GRADUATION_CANDIDATE"


def test_tracked_lookup_does_not_upgrade_level_b_swap_context_to_level_a(tmp_path: Path) -> None:
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-level-b", "graduation_candidate": True})
    client = FakeTrackedLookupClient({"mint-level-b": [_pumpswap_buy_tx("sig-buy", "mint-level-b", "pool-level-b")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=10,
    )

    assert summary["level_a_migrations_resolved"] == 0
    assert summary["level_b_migrations_inferred"] == 1
    result_rows = [json.loads(line) for line in (tmp_path / "migration_lookup_results.jsonl").read_text().splitlines() if line.strip()]
    assert result_rows[-1]["lookup_status"] == "LEVEL_B_INFERRED"
    assert result_rows[-1]["evidence_level"] == "LEVEL_B"
    assert not (tmp_path / "migration_events.jsonl").exists()


def test_tracked_lookup_cap_exhaustion_fails_gate(tmp_path: Path) -> None:
    _append(tmp_path / "tracked_mint_registry.jsonl", {"mint": "mint-cap", "graduation_candidate": True})
    client = FakeTrackedLookupClient({"mint-cap": [_create_pool_tx("sig-cap", "mint-other", "pool-other")]})

    summary = run_tracked_mint_migration_lookup(
        tmp_path,
        client=client,
        explicit_read_only_rpc_flag=True,
        max_transactions_per_address=1,
    )

    assert summary["tracked_mint_lookup_gate_passed"] is False
    assert summary["migration_lookup_cap_exhausted_count"] == 1
    assert "tracked_mint_lookup_cap_exhausted" in summary["tracked_mint_lookup_blocking_reasons"]


def test_tracked_lookup_gate_demotes_global_pumpswap_completeness_requirement() -> None:
    gate = evaluate_t007_lifecycle_readiness_v2(
        {
            "tracked_mint_migration_lookup_enabled": True,
            "tracked_mints_total": 10,
            "graduation_candidates_total": 0,
            "migration_lookup_terminal_count": 10,
            "tracked_mint_lookup_gate_passed": True,
            "level_a_migration_count": 0,
            "source_gap_gate_passed": True,
            "unbackfilled_gap_count": 0,
            "summary_raw_counter_match": True,
            "decoder_schema_ok": True,
            "watcher_schema_ok": True,
            "valuation_ladder_suppressed": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "mayhem_untouched": True,
        }
    )

    assert gate["decision_label"] == "T007_TRACKED_MINT_PIPELINE_READY_NO_GRADUATION_VOLUME"
    assert gate["can_run_10m_feature_proof"] is True
    assert gate["can_run_60m_thesis_scan"] is False
    assert "level_a_migration_count_zero" not in gate["blocking_reasons"]
    assert gate["global_pumpswap_completeness_required"] is False


def test_tracked_lookup_reclassifies_source_gaps_as_coverage_warning_after_terminal_lookup() -> None:
    gate = evaluate_t007_lifecycle_readiness_v2(
        {
            "tracked_mint_migration_lookup_enabled": True,
            "tracked_mints_total": 10,
            "graduation_candidates_total": 2,
            "migration_lookup_terminal_count": 10,
            "tracked_mint_lookup_gate_passed": True,
            "level_a_migration_count": 1,
            "pool_state_ready_count": 1,
            "source_gap_gate_passed": False,
            "unbackfilled_gap_count": 4,
            "summary_raw_counter_match": True,
            "decoder_schema_ok": True,
            "watcher_schema_ok": True,
            "valuation_ladder_suppressed": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "mayhem_untouched": True,
        }
    )

    assert gate["decision_label"] == "T007_TRACKED_MINT_LEVEL_A_PROOF_READY"
    assert gate["can_run_60m_thesis_scan"] is True
    assert "source_gap_gate_failed" not in gate["blocking_reasons"]
    assert "unbackfilled_gap_count_nonzero" not in gate["blocking_reasons"]
    assert "source_gap_reclassified_as_tracked_coverage_warning" in gate["coverage_warnings"]
