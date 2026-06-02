import csv
import json
from pathlib import Path

from research.mtp_research.validation.p0_helius_early_buyer_collection import (
    READINESS_PARTIAL,
    READINESS_READY,
    load_early_buyer_collection_checkpoint,
    run_p0_early_buyer_wallet_history_collection,
)


class FakeEarlyBuyerClient:
    def __init__(self, transactions_by_wallet: dict[str, list[dict]]):
        self.transactions_by_wallet = transactions_by_wallet
        self.calls = []

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.calls.append({"address": address, **kwargs})
        return {"transactions": list(self.transactions_by_wallet.get(address, [])), "pagination_token": None}


def _write_targets(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_path": tmp_path / "raw" / "early_buyer_wallet_history_raw_transactions.jsonl",
        "jsonl_path": tmp_path / "early_buyer_wallet_history.jsonl",
        "parquet_path": tmp_path / "early_buyer_wallet_history.parquet",
        "checkpoint_path": tmp_path / "early_buyer_wallet_history_checkpoint.json",
        "report_dir": tmp_path / "reports",
    }


def _target(wallet: str, launch_id: str = "launch-a", first_seen: int = 1_700_000_000) -> dict:
    return {
        "wallet": wallet,
        "current_launch_id": launch_id,
        "current_mint": "mint-a",
        "current_milestone_tier": "reached_500k_but_never_1m",
        "first_seen_in_launch_time": first_seen,
        "launch_age_seconds": 10,
        "reason_selected": "early_buyer_before_20k_trigger",
    }


def _tx(signature: str, block_time: int, counterparty: str = "counterparty-a") -> dict:
    return {
        "signature": signature,
        "blockTime": block_time,
        "nativeTransfers": [{"fromUserAccount": counterparty, "toUserAccount": "wallet-a", "amount": 1}],
        "tokenTransfers": [{"fromUserAccount": "wallet-a", "toUserAccount": counterparty, "mint": "mint-x", "tokenAmount": "2"}],
    }


def test_dry_run_writes_report_and_does_not_call_network(tmp_path: Path) -> None:
    targets = _write_targets(tmp_path / "targets.csv", [_target("wallet-a")])
    fake = FakeEarlyBuyerClient({"wallet-a": [_tx("sig-a", 1_699_999_000)]})

    report = run_p0_early_buyer_wallet_history_collection(
        target_csv_path=targets,
        execute=False,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    assert fake.calls == []
    assert report["execution"]["mode"] == "dry_run"
    assert report["requests"]["requests_used"] == 0
    assert report["network_calls_made"] == 0
    assert report["guardrails"]["thesis_runs"] == 0
    assert (_paths(tmp_path)["report_dir"] / "early_buyer_wallet_history_pilot_summary.json").exists()


def test_execute_fetches_bounded_wallet_history_and_preserves_raw(tmp_path: Path, monkeypatch) -> None:
    targets = _write_targets(tmp_path / "targets.csv", [_target("wallet-a"), _target("wallet-b", "launch-b")])
    fake = FakeEarlyBuyerClient(
        {
            "wallet-a": [_tx("sig-a", 1_699_999_000), _tx("sig-b", 1_699_998_000, "counterparty-b")],
            "wallet-b": [],
        }
    )
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_helius_early_buyer_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    report = run_p0_early_buyer_wallet_history_collection(
        target_csv_path=targets,
        execute=True,
        max_wallets=2,
        lookback_days=7,
        max_pages_per_wallet=1,
        max_transactions_per_wallet=5,
        max_total_transactions=10,
        request_ceiling=10,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_wallet = {row["wallet"]: row for row in rows}
    assert report["readiness_classification"] in {READINESS_READY, READINESS_PARTIAL}
    assert report["collection"]["wallets_completed"] == 2
    assert report["requests"]["requests_used"] == 2
    assert report["collection"]["transactions_fetched"] == 2
    assert by_wallet["wallet-a"]["prior_transaction_count"] == 2
    assert by_wallet["wallet-a"]["prior_distinct_counterparties"] == 2
    assert by_wallet["wallet-a"]["prior_distinct_mints"] == 1
    assert by_wallet["wallet-b"]["history_missing_reason"] == "no_prior_transactions_in_lookback_window"
    assert report["raw"]["raw_transactions_preserved"] == 2
    assert load_early_buyer_collection_checkpoint(_paths(tmp_path)["checkpoint_path"])["completed_wallets"] == ["wallet-a", "wallet-b"]


def test_request_ceiling_stops_before_second_wallet(tmp_path: Path, monkeypatch) -> None:
    targets = _write_targets(tmp_path / "targets.csv", [_target("wallet-a"), _target("wallet-b", "launch-b")])
    fake = FakeEarlyBuyerClient({"wallet-a": [_tx("sig-a", 1_699_999_000)], "wallet-b": [_tx("sig-b", 1_699_999_000)]})
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_helius_early_buyer_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    report = run_p0_early_buyer_wallet_history_collection(
        target_csv_path=targets,
        execute=True,
        max_wallets=2,
        request_ceiling=1,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    assert [call["address"] for call in fake.calls] == ["wallet-a"]
    assert report["requests"]["stopped_due_ceiling"] is True
    assert report["collection"]["wallets_completed"] == 1
