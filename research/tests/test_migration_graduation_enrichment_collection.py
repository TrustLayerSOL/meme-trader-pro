import json
from pathlib import Path

import pytest

from research.mtp_research.validation.migration_graduation_enrichment_collection import (
    LABEL_FIELDS,
    READINESS_BLOCKED,
    READINESS_PARTIAL,
    READINESS_READY,
    load_collection_checkpoint,
    run_migration_graduation_enrichment_collection,
    write_collection_checkpoint,
    _transaction_signature,
)


class FakeMigrationClient:
    def __init__(self, *, signatures: list[dict] | None = None, transactions: dict[str, dict] | None = None):
        self.signatures = signatures or []
        self.transactions = transactions or {}
        self.signature_calls = 0
        self.transaction_calls = 0

    def fetch_signatures_for_address(self, request):
        self.signature_calls += 1
        return _SignatureResult(
            records=[
                _SignatureRecord(
                    signature=row["signature"],
                    block_time=row.get("blockTime"),
                    slot=row.get("slot"),
                    raw_json=row,
                )
                for row in self.signatures
            ],
            next_before=None,
        )

    def fetch_transaction(self, signature: str) -> dict:
        self.transaction_calls += 1
        return dict(self.transactions.get(signature, {}))


class BatchMigrationClient(FakeMigrationClient):
    def __init__(self, *, signatures: list[dict] | None = None, transactions: dict[str, dict] | None = None):
        super().__init__(signatures=signatures, transactions=transactions)
        self.batch_transaction_calls = 0
        self.batch_signatures = []

    def fetch_transactions(self, signatures: list[str]) -> list[dict]:
        self.batch_transaction_calls += 1
        self.batch_signatures.append(list(signatures))
        return [dict(self.transactions.get(signature, {})) for signature in signatures]


class AddressWindowMigrationClient(FakeMigrationClient):
    def __init__(self, *, transactions: list[dict]):
        super().__init__(signatures=[], transactions={})
        self.window_transactions = transactions
        self.address_window_calls = 0

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.address_window_calls += 1
        return {"transactions": list(self.window_transactions), "pagination_token": None}


class _SignatureRecord:
    def __init__(self, *, signature: str, block_time: int | None, slot: int | None, raw_json: dict):
        self.signature = signature
        self.block_time = block_time
        self.slot = slot
        self.raw_json = raw_json


class _SignatureResult:
    def __init__(self, *, records: list[_SignatureRecord], next_before: str | None):
        self.records = records
        self.next_before = next_before


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, *, launch_ts: int = 1_700_000_000) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts + index,
        "launch_time_utc": "2026-05-25T10:00:00+00:00",
        "metadata_json": {
            "creator_deployer": "creator-repeat",
            "creation_signature": f"create-sig-{index}",
            "bonding_curve": f"curve-{index}",
            "associated_bonding_curve": f"assoc-{index}",
        },
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_dir": tmp_path / "raw",
        "jsonl_path": tmp_path / "migration_graduation_pilot_candidates.jsonl",
        "parquet_path": tmp_path / "migration_graduation_pilot_candidates.parquet",
        "checkpoint_path": tmp_path / "checkpoint.json",
        "report_dir": tmp_path / "reports",
    }


def test_dry_run_does_not_call_network_or_write_raw_transactions(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1)])
    fake_client = FakeMigrationClient(signatures=[{"signature": "sig-1", "blockTime": 1_700_000_010}])

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=False,
        mint_limit=1,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    assert fake_client.signature_calls == 0
    assert fake_client.transaction_calls == 0
    assert result["execution"]["mode"] == "dry_run"
    assert result["requests"]["requests_used"] == 0
    assert not (_paths(tmp_path)["raw_dir"] / "migration_graduation_raw_transactions.jsonl").exists()


def test_hard_stop_projection_blocks_before_network_calls(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(i) for i in range(5)])
    fake_client = FakeMigrationClient()

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=5,
        request_ceiling=10_000,
        hard_stop_projected_requests=100,
        window="7d",
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    assert result["readiness_classification"] == READINESS_BLOCKED
    assert result["requests"]["stopped_due_ceiling"] is True
    assert fake_client.signature_calls == 0


def test_request_ceiling_stops_collection_before_exceeding_cap(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1), _candidate(2)])
    fake_client = FakeMigrationClient(signatures=[{"signature": "sig-1", "blockTime": 1_700_000_010}])

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=2,
        request_ceiling=1,
        hard_stop_projected_requests=1000,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    assert result["requests"]["requests_used"] <= 1
    assert result["requests"]["stopped_due_ceiling"] is True
    assert result["readiness_classification"] in {READINESS_BLOCKED, READINESS_PARTIAL}


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"

    write_collection_checkpoint(checkpoint_path, {"completed_mints": ["mint-1"], "requests_used": 7})

    assert load_collection_checkpoint(checkpoint_path) == {"completed_mints": ["mint-1"], "requests_used": 7}
    assert load_collection_checkpoint(tmp_path / "missing.json") == {}


def test_resume_collapses_duplicate_existing_candidate_rows(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [_candidate(1, launch_ts=launch_ts), _candidate(2, launch_ts=launch_ts + 100)],
    )
    paths = _paths(tmp_path)
    _write_jsonl(
        paths["jsonl_path"],
        [
            {"mint": "mint-1", "launch_id": "launch-1", "migration_missing_reason": "old_duplicate"},
            {"mint": "mint-1", "launch_id": "launch-1", "migration_missing_reason": "newer_duplicate"},
        ],
    )
    write_collection_checkpoint(paths["checkpoint_path"], {"completed_mints": ["mint-1"], "requests_used": 0})
    fake_client = FakeMigrationClient(
        signatures=[{"signature": "sig-2", "blockTime": launch_ts + 160}],
        transactions={"sig-2": {"blockTime": launch_ts + 160, "meta": {"logMessages": []}}},
    )

    run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=2,
        output_paths=paths,
        client=fake_client,
    )

    output_rows = [json.loads(line) for line in paths["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert [row["mint"] for row in output_rows] == ["mint-1", "mint-2"]
    assert output_rows[0]["migration_missing_reason"] == "newer_duplicate"


def test_collection_batches_output_flushes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidates_path = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [_candidate(1), _candidate(2), _candidate(3)],
    )
    paths = _paths(tmp_path)
    fake_client = FakeMigrationClient(
        signatures=[{"signature": "sig-unknown", "blockTime": 1_700_000_010}],
        transactions={"sig-unknown": {"blockTime": 1_700_000_010, "meta": {"logMessages": []}}},
    )
    parquet_writes = []

    def fake_write_parquet(rows, path):
        parquet_writes.append((len(rows), path))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("stub", encoding="utf-8")

    monkeypatch.setattr(
        "research.mtp_research.validation.migration_graduation_enrichment_collection._write_parquet",
        fake_write_parquet,
    )

    run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=3,
        output_paths=paths,
        client=fake_client,
        output_flush_interval_mints=10,
    )

    assert parquet_writes == [(3, paths["parquet_path"])]


def test_collection_uses_batch_transaction_hydration_when_available(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1, launch_ts=launch_ts)])
    fake_client = BatchMigrationClient(
        signatures=[
            {"signature": "sig-1", "blockTime": launch_ts + 10},
            {"signature": "sig-2", "blockTime": launch_ts + 20},
            {"signature": "sig-3", "blockTime": launch_ts + 30},
        ],
        transactions={
            "sig-1": {"blockTime": launch_ts + 10, "meta": {"logMessages": []}},
            "sig-2": {"blockTime": launch_ts + 20, "meta": {"logMessages": []}},
            "sig-3": {"blockTime": launch_ts + 30, "meta": {"logMessages": []}},
        },
    )

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=1,
        max_transactions_per_mint=3,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    assert fake_client.batch_transaction_calls == 1
    assert fake_client.transaction_calls == 0
    assert fake_client.batch_signatures == [["sig-1", "sig-2", "sig-3"]]
    assert result["requests"]["requests_used"] == 4
    assert result["collection"]["transactions_fetched"] == 3


def test_collection_prefers_address_window_fetch_when_available(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1, launch_ts=launch_ts)])
    fake_client = AddressWindowMigrationClient(
        transactions=[
            {
                "blockTime": launch_ts + 60,
                "slot": 123,
                "meta": {"logMessages": ["Program log: Instruction: Migrate"]},
                "transaction": {
                    "signatures": ["sig-window"],
                    "message": {"accountKeys": [{"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}]},
                },
            }
        ]
    )

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=1,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    assert fake_client.address_window_calls == 1
    assert fake_client.signature_calls == 0
    assert fake_client.transaction_calls == 0
    assert result["requests"]["requests_used"] == 1
    assert result["collection"]["transactions_fetched"] == 1
    assert result["labels"]["unique_migrated_graduated_mints_detected"] == 1


def test_transaction_signature_extracts_from_window_payload() -> None:
    assert _transaction_signature({"signature": "top-level"}) == "top-level"
    assert _transaction_signature({"transaction": {"signatures": ["nested"]}}) == "nested"
    assert _transaction_signature({"transaction": {"signatures": []}}) is None


def test_execute_preserves_raw_transactions_and_writes_label_schema(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1, launch_ts=launch_ts)])
    fake_client = FakeMigrationClient(
        signatures=[{"signature": "sig-migrate", "blockTime": launch_ts + 60, "slot": 123}],
        transactions={
            "sig-migrate": {
                "slot": 123,
                "blockTime": launch_ts + 60,
                "meta": {"logMessages": ["Program log: Instruction: Migrate"]},
                "transaction": {"message": {"accountKeys": [{"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}]}},
            }
        },
    )

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=1,
        request_ceiling=50,
        hard_stop_projected_requests=1000,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    raw_path = _paths(tmp_path)["raw_dir"] / "migration_graduation_raw_transactions.jsonl"
    assert raw_path.exists()
    raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    assert raw_rows[0]["signature"] == "sig-migrate"

    output_rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert set(LABEL_FIELDS).issubset(output_rows[0])
    assert output_rows[0]["pumpfun_migrate_event_observed"] is True
    assert output_rows[0]["migration_time"] is not None
    assert result["readiness_classification"] == READINESS_READY
    assert result["labels"]["unique_migrated_graduated_mints_detected"] == 1


def test_missing_migration_reason_is_recorded(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1, launch_ts=launch_ts)])
    fake_client = FakeMigrationClient(
        signatures=[{"signature": "sig-unknown", "blockTime": launch_ts + 60}],
        transactions={"sig-unknown": {"blockTime": launch_ts + 60, "meta": {"logMessages": ["Program log: Instruction: Buy"]}}},
    )

    run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=1,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    output_rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert output_rows[0]["migration_missing_reason"] == "not_observed_in_window"
    assert output_rows[0]["dex_pair_detected"] is False


def test_fee_sharing_creator_migration_log_is_not_graduation(tmp_path: Path) -> None:
    launch_ts = 1_700_000_000
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1, launch_ts=launch_ts)])
    fake_client = FakeMigrationClient(
        signatures=[{"signature": "sig-fee-sharing", "blockTime": launch_ts + 60}],
        transactions={
            "sig-fee-sharing": {
                "blockTime": launch_ts + 60,
                "meta": {
                    "logMessages": [
                        "Program log: Instruction: CreateFeeSharingConfig",
                        "Program log: Instruction: MigrateBondingCurveCreator",
                        "Program log: Instruction: UpdateFeeShares",
                    ]
                },
                "transaction": {
                    "message": {
                        "accountKeys": [{"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}]
                    }
                },
            }
        },
    )

    run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=True,
        mint_limit=1,
        output_paths=_paths(tmp_path),
        client=fake_client,
    )

    output_rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert output_rows[0]["pumpfun_migrate_event_observed"] is False
    assert output_rows[0]["liquidity_pool_created_after_launch"] is False
    assert output_rows[0]["migration_missing_reason"] == "not_observed_in_window"


def test_report_declares_no_thesis_backtest_validation_or_trading(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1)])

    result = run_migration_graduation_enrichment_collection(
        candidates_path=candidates_path,
        execute=False,
        mint_limit=1,
        output_paths=_paths(tmp_path),
        client=FakeMigrationClient(),
    )

    assert result["guardrails"] == {
        "thesis_runs": 0,
        "backtests_run": 0,
        "validation_runs": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "trading_logic_added": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
    }
