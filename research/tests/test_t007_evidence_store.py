from __future__ import annotations

from pathlib import Path

from research.mtp_research.validation.t007_evidence_model import (
    AccountSnapshotRecord,
    EvidenceRecord,
    LifecycleTransitionRecord,
    MigrationEvidenceLevel,
)
from research.mtp_research.validation.t007_evidence_store import T007EvidenceStore


def test_evidence_record_preserves_raw_transaction_anchor() -> None:
    row = EvidenceRecord(
        signature="sig-a",
        slot=123,
        observed_at=1000.5,
        commitment="confirmed",
        source_lane="pumpswap_transaction_subscribe",
        source_route="accountInclude_pumpswap_program",
        mint="mint-a",
        pool="pool-a",
        evidence_level=MigrationEvidenceLevel.LEVEL_B,
        raw_tx_hash="hash-a",
        raw_tx_json={"meta": {"err": None}},
        rule_hits=["first_swap_after_live_birth"],
        confidence=0.93,
    ).to_json_row()

    assert row["signature"] == "sig-a"
    assert row["evidence_level"] == "LEVEL_B"
    assert row["rule_hits"] == ["first_swap_after_live_birth"]
    assert row["raw_tx_hash"] == "hash-a"


def test_account_snapshot_key_is_pubkey_slot_commitment() -> None:
    row = AccountSnapshotRecord(
        pubkey="pool-a",
        slot=123,
        commitment="confirmed",
        observed_at=1001.0,
        snapshot_hash="snapshot-hash",
        raw_snapshot_json={"lamports": 1},
    )

    assert row.dedupe_key() == ("pool-a", 123, "confirmed")


def test_lifecycle_transition_records_previous_and_next_state() -> None:
    row = LifecycleTransitionRecord(
        mint="mint-a",
        previous_state="CURVE_ACTIVE",
        next_state="MIGRATION_CONFIRMED_LEVEL_B",
        signature="sig-a",
        observed_at=1002.0,
        reason="first_pumpswap_swap_after_live_birth",
    ).to_json_row()

    assert row["previous_state"] == "CURVE_ACTIVE"
    assert row["next_state"] == "MIGRATION_CONFIRMED_LEVEL_B"


def test_evidence_store_dedupes_signature_lane(tmp_path: Path) -> None:
    store = T007EvidenceStore(tmp_path)
    first = store.write_evidence({"signature": "sig-a", "source_lane": "pumpfun_birth", "slot": 1})
    second = store.write_evidence({"signature": "sig-a", "source_lane": "pumpfun_birth", "slot": 1})

    assert first == "written"
    assert second == "duplicate"
    rows = list(store.read_jsonl("evidence_records.jsonl"))
    assert len(rows) == 1


def test_evidence_store_keeps_same_signature_different_lane(tmp_path: Path) -> None:
    store = T007EvidenceStore(tmp_path)

    assert store.write_evidence({"signature": "sig-a", "source_lane": "pumpfun_birth", "slot": 1}) == "written"
    assert store.write_evidence({"signature": "sig-a", "source_lane": "pumpswap_swap", "slot": 1}) == "written"
    assert len(list(store.read_jsonl("evidence_records.jsonl"))) == 2


def test_evidence_store_dedupes_account_snapshots_and_transitions(tmp_path: Path) -> None:
    store = T007EvidenceStore(tmp_path)

    assert store.write_account_snapshot({"pubkey": "pool-a", "slot": 2, "commitment": "confirmed"}) == "written"
    assert store.write_account_snapshot({"pubkey": "pool-a", "slot": 2, "commitment": "confirmed"}) == "duplicate"
    assert store.write_lifecycle_transition(
        {"mint": "mint-a", "next_state": "MIGRATION_CONFIRMED_LEVEL_B", "signature": "sig-a", "reason": "first_swap"}
    ) == "written"
    assert store.write_lifecycle_transition(
        {"mint": "mint-a", "next_state": "MIGRATION_CONFIRMED_LEVEL_B", "signature": "sig-a", "reason": "first_swap"}
    ) == "duplicate"

    assert len(list(store.read_jsonl("account_snapshot_log.jsonl"))) == 1
    assert len(list(store.read_jsonl("lifecycle_transitions.jsonl"))) == 1
