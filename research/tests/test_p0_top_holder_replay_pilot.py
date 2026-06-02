import csv
import json
from pathlib import Path

from research.mtp_research.validation.p0_top_holder_replay_pilot import (
    READINESS_PARTIAL,
    READINESS_READY,
    run_p0_top_holder_replay_pilot,
)


class FakeMintHistoryClient:
    def __init__(self, transactions_by_mint: dict[str, list[dict]]):
        self.transactions_by_mint = transactions_by_mint
        self.calls = []

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.calls.append({"address": address, **kwargs})
        return {"transactions": list(self.transactions_by_mint.get(address, [])), "pagination_token": None}


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
        "raw_path": tmp_path / "raw" / "top_holder_raw_transactions.jsonl",
        "jsonl_path": tmp_path / "top_holder_replay.jsonl",
        "parquet_path": tmp_path / "top_holder_replay.parquet",
        "checkpoint_path": tmp_path / "top_holder_replay_checkpoint.json",
        "report_dir": tmp_path / "reports",
    }


def _target(mint: str = "mint-a", milestone: str = "20k", milestone_time: int = 1_700_000_120, age: int = 120) -> dict:
    return {
        "launch_id": "launch-a",
        "mint": mint,
        "milestone": milestone,
        "milestone_time": milestone_time,
        "milestone_age_seconds": age,
        "milestone_tier": "reached_500k_but_never_1m",
        "reason_selected": "500k_plus_runner",
    }


def _balance_tx(signature: str, block_time: int, mint: str, owner: str, pre: str | None, post: str | None) -> dict:
    pre_rows = []
    post_rows = []
    if pre is not None:
        pre_rows.append({"accountIndex": 1, "mint": mint, "owner": owner, "uiTokenAmount": {"uiAmountString": pre, "decimals": 6}})
    if post is not None:
        post_rows.append({"accountIndex": 1, "mint": mint, "owner": owner, "uiTokenAmount": {"uiAmountString": post, "decimals": 6}})
    return {
        "signature": signature,
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {"signatures": [signature], "message": {"accountKeys": ["payer", "token-account"]}},
        "meta": {"err": None, "preTokenBalances": pre_rows, "postTokenBalances": post_rows},
    }


def test_dry_run_does_not_call_network(tmp_path: Path) -> None:
    targets = _write_targets(tmp_path / "targets.csv", [_target()])
    fake = FakeMintHistoryClient({"mint-a": [_balance_tx("sig-a", 1_700_000_010, "mint-a", "wallet-a", None, "10")]})

    report = run_p0_top_holder_replay_pilot(
        target_csv_path=targets,
        execute=False,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    assert fake.calls == []
    assert report["execution"]["mode"] == "dry_run"
    assert report["network_calls_made"] == 0
    assert report["guardrails"]["thesis_runs"] == 0
    assert (_paths(tmp_path)["report_dir"] / "top_holder_replay_pilot_summary.json").exists()


def test_execute_replays_top_holder_balances_at_milestones(tmp_path: Path, monkeypatch) -> None:
    targets = _write_targets(
        tmp_path / "targets.csv",
        [_target("mint-a", "20k", 1_700_000_120, 120), _target("mint-a", "100k", 1_700_000_240, 240)],
    )
    fake = FakeMintHistoryClient(
        {
            "mint-a": [
                _balance_tx("sig-a", 1_700_000_010, "mint-a", "wallet-a", None, "100"),
                _balance_tx("sig-b", 1_700_000_100, "mint-a", "wallet-b", None, "50"),
                _balance_tx("sig-c", 1_700_000_200, "mint-a", "wallet-a", "100", "80"),
            ]
        }
    )
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_top_holder_replay_pilot._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    report = run_p0_top_holder_replay_pilot(
        target_csv_path=targets,
        execute=True,
        max_mints=1,
        max_pages_per_mint=1,
        max_transactions_per_mint=10,
        request_ceiling=10,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_milestone = {row["milestone"]: row for row in rows}
    assert report["readiness_classification"] in {READINESS_READY, READINESS_PARTIAL}
    assert by_milestone["20k"]["holder_count_proxy"] == 2
    assert by_milestone["20k"]["top_holder_owner"] == "wallet-a"
    assert by_milestone["20k"]["top_holder_share_proxy"] == 100 / 150
    assert by_milestone["100k"]["top_holder_balance_proxy"] == 80
    assert by_milestone["100k"]["top_10_holder_share_proxy"] == 1.0
    assert report["replay_quality"]["milestones_with_holder_proxy"] == 2
    assert report["raw"]["raw_transactions_preserved"] == 3


def test_unknown_or_missing_deltas_fail_closed(tmp_path: Path, monkeypatch) -> None:
    targets = _write_targets(tmp_path / "targets.csv", [_target("mint-a")])
    fake = FakeMintHistoryClient({"mint-a": [{"signature": "sig-empty", "blockTime": 1_700_000_010}]})
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_top_holder_replay_pilot._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    report = run_p0_top_holder_replay_pilot(
        target_csv_path=targets,
        execute=True,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert rows[0]["holder_snapshot_missing_reason"] == "no_token_balance_deltas_before_milestone"
    assert rows[0]["top_holder_share_proxy"] is None
    assert report["warnings"] == ["no_top_holder_proxy_reconstructed"]
