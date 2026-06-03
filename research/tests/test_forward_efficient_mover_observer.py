from pathlib import Path

from research.mtp_research.validation.forward_efficient_mover_observer import (
    ForwardObserverConfig,
    MockCandidateSource,
    build_observation_rows,
    calculate_status_tally,
    run_dry_run,
    run_observe,
    write_checkpoint,
    read_checkpoint,
)


def test_dry_run_reports_orico_paths_and_guardrails(tmp_path: Path) -> None:
    config = ForwardObserverConfig(data_root=tmp_path, mode="dry-run")

    report = run_dry_run(config)

    assert report["mode"] == "dry-run"
    assert report["readiness_classification"] == "forward_observer_ready_for_dry_run"
    assert str(tmp_path) in report["observation_root"]
    assert report["guardrails"]["private_key_logic"] is False
    assert report["guardrails"]["wallet_execution"] is False
    assert report["guardrails"]["order_routing"] is False


def test_observe_with_mock_source_writes_observation_files(tmp_path: Path) -> None:
    config = ForwardObserverConfig(
        data_root=tmp_path,
        mode="observe",
        target_candidates=2,
        max_observe_iterations=1,
        status_interval_seconds=1,
    )
    source = MockCandidateSource(
        [
            {
                "mint": "mint-a",
                "token_symbol": "MOCKA",
                "fdv_proxy": 21_000,
                "event_count": 3,
                "buy_count": 3,
                "sell_count": 0,
                "active_wallets": 2,
                "source": "mock",
            },
            {
                "mint": "mint-b",
                "token_symbol": "MOCKB",
                "fdv_proxy": 120_000,
                "event_count": 8,
                "buy_count": 5,
                "sell_count": 3,
                "active_wallets": 5,
                "source": "mock",
            },
        ]
    )

    result = run_observe(config, source=source)
    tally = calculate_status_tally(config.observation_root, target_candidates=2)

    assert result["mode"] == "observe"
    assert tally["total_candidates_observed"] == 2
    assert tally["candidates_that_reached_20k"] == 2
    assert tally["candidates_that_reached_100k"] == 1
    assert tally["event_rows_collected"] == 2
    assert (config.observation_root / "candidates.jsonl").exists()
    assert (config.observation_root / "candidate_paths.jsonl").exists()
    assert (config.observation_root / "candidate_metadata.jsonl").exists()
    assert (config.observation_root / "checkpoint.json").exists()


def test_status_tally_counts_milestones_and_drawdowns(tmp_path: Path) -> None:
    root = tmp_path / "data" / "forward_observation" / "efficient_movers"
    root.mkdir(parents=True)
    (root / "candidates.jsonl").write_text(
        "\n".join(
            [
                '{"observation_id":"obs-a","mint":"mint-a","start_trigger":10000,"status":"completed","trigger_level":"10k"}',
                '{"observation_id":"obs-b","mint":"mint-b","start_trigger":20000,"status":"active","trigger_level":"20k"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "candidate_paths.jsonl").write_text(
        "\n".join(
            [
                '{"observation_id":"obs-a","mint":"mint-a","crossed_20k":true,"crossed_50k":true,"crossed_100k":false,"crossed_500k":false,"crossed_1m":false}',
                '{"observation_id":"obs-b","mint":"mint-b","crossed_20k":true,"crossed_50k":true,"crossed_100k":true,"crossed_500k":true,"crossed_1m":false}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "candidate_drawdowns.jsonl").write_text(
        "\n".join(
            [
                '{"observation_id":"obs-a","first_30pct_drawdown_time":123,"reclaim_prior_high_time":150,"no_reclaim_after_5m":false}',
                '{"observation_id":"obs-b","first_30pct_drawdown_time":124,"reclaim_prior_high_time":null,"no_reclaim_after_5m":true}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tally = calculate_status_tally(root, target_candidates=3)

    assert tally["total_candidates_observed"] == 2
    assert tally["active_candidates_currently_watched"] == 1
    assert tally["completed_candidates"] == 1
    assert tally["candidates_that_reached_500k"] == 1
    assert tally["candidates_with_30pct_drawdown"] == 2
    assert tally["candidates_with_recoveries_after_30pct_drawdown"] == 1
    assert tally["remaining_until_target"] == 1


def test_build_observation_rows_schema_and_drawdown_fields() -> None:
    rows = build_observation_rows(
        {
            "mint": "mint-a",
            "fdv_proxy": 50_000,
            "event_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallets": 3,
            "liquidity_proxy": 1.2,
        },
        start_trigger=10_000,
        observation_id="obs-a",
        observed_at=1_000,
    )

    assert rows["candidate"]["observation_id"] == "obs-a"
    assert rows["path"]["fdv_per_event"] == 10_000
    assert rows["path"]["fdv_per_buy"] == 12_500
    assert rows["path"]["buy_sell_ratio"] == 4
    assert rows["path"]["crossed_50k"] is True
    assert rows["drawdown"]["current_local_high_fdv"] == 50_000
    assert rows["metadata"]["metadata_observed_at"] == 1_000


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    payload = {"active_observations": {"mint-a": "obs-a"}, "api_calls_used": 7}

    write_checkpoint(checkpoint, payload)

    assert read_checkpoint(checkpoint) == payload
