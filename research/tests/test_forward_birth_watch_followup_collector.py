import json
from pathlib import Path

from research.mtp_research.validation.forward_birth_watch_followup_collector import (
    MockBirthWatchFollowupFetcher,
    build_birth_watch_followup_plan,
    run_birth_watch_followup_collection,
)


def test_birth_watch_followup_plan_is_bounded_and_dry_run(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {"observation_id": "birth-a", "mint": "mint-a", "freshness_lane": "birth_watch", "event_type": "pumpfun_create"},
            {"observation_id": "birth-b", "mint": "mint-b", "freshness_lane": "birth_watch", "event_type": "pumpfun_create"},
        ],
    )

    plan = build_birth_watch_followup_plan(
        root,
        max_mints=1,
        signatures_per_mint=4,
        transactions_per_mint=2,
        request_ceiling=10,
    )

    assert plan["execute"] is False
    assert plan["selected_mint_count"] == 1
    assert plan["projected_requests"] == 3
    assert plan["request_ceiling_status"] == "within_ceiling"
    assert plan["network_calls_made"] == 0


def test_birth_watch_followup_collection_appends_path_rows_without_new_candidate(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_create",
                "observed_at": 100,
            }
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [{"observation_id": "birth-a", "mint": "mint-a", "event_type": "pumpfun_create", "timestamp": 100, "fdv_proxy": None}],
    )
    fetcher = MockBirthWatchFollowupFetcher(
        {
            "mint-a": [
                {
                    "mint": "mint-a",
                    "source": "helius_birth_watch_followup",
                    "event_type": "pumpfun_trade",
                    "fdv_proxy": 12_500,
                    "price_proxy": 0.0000125,
                    "event_count": 1,
                    "buy_count": 1,
                    "sell_count": 0,
                    "active_wallets": 1,
                    "transaction_signature": "sig-a",
                    "slot": 123,
                    "block_time": 110,
                }
            ]
        },
        requests_used=3,
    )

    result = run_birth_watch_followup_collection(
        root,
        max_mints=1,
        signatures_per_mint=4,
        transactions_per_mint=2,
        request_ceiling=10,
        execute=True,
        fetcher=fetcher,
        observed_at=120,
    )

    candidates = _read_jsonl(obs / "candidates.jsonl")
    paths = _read_jsonl(obs / "candidate_paths.jsonl")

    assert result["execute"] is True
    assert result["mints_with_fdv_followup"] == 1
    assert result["mints_with_trigger_followup"] == 1
    assert len(candidates) == 1
    assert len(paths) == 2
    assert paths[-1]["observation_id"] == "birth-a"
    assert paths[-1]["mint"] == "mint-a"
    assert paths[-1]["freshness_lane"] == "birth_watch"
    assert paths[-1]["fdv_proxy"] == 12_500
    assert paths[-1]["crossed_10k"] is True


def test_birth_watch_followup_collection_requires_execute(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(obs / "candidates.jsonl", [{"observation_id": "birth-a", "mint": "mint-a", "freshness_lane": "birth_watch"}])
    fetcher = MockBirthWatchFollowupFetcher({"mint-a": [{"mint": "mint-a", "fdv_proxy": 12_500}]})

    result = run_birth_watch_followup_collection(root, execute=False, fetcher=fetcher)

    assert result["execute"] is False
    assert result["network_calls_made"] == 0
    assert fetcher.fetch_calls == 0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
