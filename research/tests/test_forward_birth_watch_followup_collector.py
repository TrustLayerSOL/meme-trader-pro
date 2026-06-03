import json
from pathlib import Path

from research.mtp_research.validation.forward_birth_watch_followup_collector import (
    MockBirthWatchCandidateSource,
    MockBirthWatchFollowupFetcher,
    build_birth_watch_followup_plan,
    run_immediate_birth_followup_observation,
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


def test_immediate_birth_followup_writes_freshness_sidecar_files(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    source = MockBirthWatchCandidateSource(
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "source": "helius_program_logs_pumpfun_create_scanner",
                "launch_time": 100,
                "block_time": 100,
                "transaction_signature": "create-sig-a",
            }
        ]
    )
    fetcher = MockBirthWatchFollowupFetcher(
        {
            "mint-a": [
                {
                    "mint": "mint-a",
                    "source": "helius_birth_watch_immediate_followup",
                    "event_type": "pumpfun_trade",
                    "fdv_proxy": 9_500,
                    "price_proxy": 0.0000095,
                    "event_count": 1,
                    "buy_count": 1,
                    "sell_count": 0,
                    "active_wallets": 1,
                    "transaction_signature": "trade-sig-a",
                    "slot": 123,
                    "block_time": 104,
                }
            ]
        },
        requests_used=2,
    )

    result = run_immediate_birth_followup_observation(
        root,
        target_births=1,
        followup_duration_seconds=10,
        followup_poll_seconds=0,
        max_followup_passes_per_mint=2,
        max_runtime_minutes=1,
        max_helius_credits=100,
        execute=True,
        candidate_source=source,
        fetcher=fetcher,
        time_fn=_time_sequence([100, 100, 104, 104, 104]),
        sleep_fn=lambda _: None,
    )

    obs = root / "data" / "forward_observation" / "efficient_movers"
    mints = _read_jsonl(obs / "birth_watch_mints.jsonl")
    paths = _read_jsonl(obs / "birth_followup_paths.jsonl")
    events = _read_jsonl(obs / "birth_followup_events.jsonl")
    status = json.loads((obs / "birth_followup_status.json").read_text(encoding="utf-8"))

    assert result["execute"] is True
    assert result["smoke_birth_count"] == 1
    assert result["immediate_followup_started_count"] == 1
    assert result["first_followup_path_rows"] == 1
    assert result["first_followup_before_10k_count"] == 1
    assert result["readiness_classification"] == "freshness_repair_ready_for_100_birth_smoke"
    assert mints[0]["create_signature"] == "create-sig-a"
    assert mints[0]["followup_started_immediately"] is True
    assert paths[0]["first_followup_before_10k"] is True
    assert paths[0]["freshness_class"] == "true_birth_observed"
    assert events[0]["transaction_signature"] == "trade-sig-a"
    assert status["birth_watch_mints"] == 1
    assert status["median_seconds_create_to_first_followup_attempt"] == 0


def test_immediate_birth_followup_is_dry_run_without_execute(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    source = MockBirthWatchCandidateSource([{"mint": "mint-a", "event_type": "pumpfun_create", "freshness_lane": "birth_watch"}])
    fetcher = MockBirthWatchFollowupFetcher({"mint-a": [{"mint": "mint-a", "fdv_proxy": 9_500}]})

    result = run_immediate_birth_followup_observation(
        root,
        target_births=1,
        execute=False,
        candidate_source=source,
        fetcher=fetcher,
    )

    assert result["execute"] is False
    assert result["network_calls_made"] == 0
    assert fetcher.fetch_calls == 0


def test_immediate_birth_followup_loads_and_writes_source_checkpoint(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    (obs / "checkpoint.json").write_text('{"birth_scan_processed_signatures":["old-sig"]}', encoding="utf-8")
    source = _CheckpointAwareBirthSource()
    fetcher = MockBirthWatchFollowupFetcher({"mint-a": []})

    result = run_immediate_birth_followup_observation(
        root,
        target_births=1,
        followup_duration_seconds=0,
        followup_poll_seconds=0,
        max_followup_passes_per_mint=1,
        execute=True,
        candidate_source=source,
        fetcher=fetcher,
        time_fn=_time_sequence([100, 100, 100]),
        sleep_fn=lambda _: None,
    )

    checkpoint = json.loads((obs / "checkpoint.json").read_text(encoding="utf-8"))
    assert result["smoke_birth_count"] == 1
    assert source.loaded_checkpoint["birth_scan_processed_signatures"] == ["old-sig"]
    assert checkpoint["birth_scan_processed_signatures"] == ["new-sig"]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _time_sequence(values: list[int]):
    iterator = iter(values)
    last = values[-1]

    def _next() -> int:
        nonlocal last
        try:
            last = next(iterator)
        except StopIteration:
            pass
        return last

    return _next


class _CheckpointAwareBirthSource:
    requests_used = 0

    def __init__(self) -> None:
        self.loaded_checkpoint = {}

    def availability(self) -> dict:
        return {"source": "checkpoint-aware", "available": True, "read_only": True}

    def load_checkpoint(self, checkpoint: dict) -> None:
        self.loaded_checkpoint = checkpoint

    def checkpoint_updates(self) -> dict:
        return {"birth_scan_processed_signatures": ["new-sig"]}

    def fetch_candidates(self) -> list[dict]:
        return [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "source": "checkpoint-aware",
                "launch_time": 100,
                "block_time": 100,
                "transaction_signature": "create-sig-a",
            }
        ]
