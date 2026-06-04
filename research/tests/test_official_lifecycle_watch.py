import json
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_watch import (
    OFFICIAL_SAMPLE_LABEL,
    OfficialLifecycleConfig,
    OfficialLifecycleStateMachine,
    build_official_lifecycle_quality_audit,
    initialize_official_lifecycle_namespace,
    official_lifecycle_status,
    run_official_lifecycle_smoke,
)


def test_official_namespace_starts_from_zero_and_excludes_quarantine(tmp_path: Path) -> None:
    old = tmp_path / "data" / "forward_observation" / "quarantined" / "pre_lifecycle_watch_forward_sample"
    old.mkdir(parents=True)
    (old / "pre_lifecycle_watch_analysis_dataset.jsonl").write_text('{"mint":"old-mint"}\n', encoding="utf-8")
    config = OfficialLifecycleConfig(data_root=tmp_path)

    manifest = initialize_official_lifecycle_namespace(config)

    assert manifest["sample_label"] == OFFICIAL_SAMPLE_LABEL
    assert manifest["starts_from_zero"] is True
    assert manifest["old_quarantined_sample_excluded"] is True
    assert manifest["initial_counts"]["births"] == 0
    assert config.observation_root.name == OFFICIAL_SAMPLE_LABEL
    assert config.state_path.exists()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state["mints"] == {}
    assert old.exists()


def test_lifecycle_state_transitions_and_active_watch_retention(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    machine = OfficialLifecycleStateMachine(config)

    machine.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
        }
    )
    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 103,
            "fdv_proxy": 12_000,
            "event_count": 1,
            "buy_count": 1,
            "sell_count": 0,
            "active_wallet_count": 1,
            "source_provenance": "mock_observed_path",
        }
    )
    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 104,
            "fdv_proxy": 22_000,
            "event_count": 2,
            "buy_count": 2,
            "sell_count": 0,
            "active_wallet_count": 2,
            "source_provenance": "mock_observed_path",
        }
    )

    assert machine.state["mints"]["mint-a"]["state"] == "trigger_qualified_active_watch"
    assert machine.active_watch_mints() == ["mint-a"]
    assert machine.state["counters"]["official_crossed_20k_count"] == 1

    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 105,
            "fdv_proxy": 30_000,
            "event_count": 3,
            "buy_count": 2,
            "sell_count": 1,
            "active_wallet_count": 2,
            "source_provenance": "mock_observed_path",
        }
    )
    assert machine.active_watch_mints() == ["mint-a"]

    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 106,
            "fdv_proxy": 1_100_000,
            "event_count": 4,
            "buy_count": 3,
            "sell_count": 1,
            "active_wallet_count": 3,
            "source_provenance": "mock_observed_path",
        }
    )
    assert machine.state["mints"]["mint-a"]["state"] == "matured_reached_1m"
    assert machine.active_watch_mints() == []


def test_lifecycle_state_save_merges_concurrent_machine_instances(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    machine_a = OfficialLifecycleStateMachine(config)
    machine_b = OfficialLifecycleStateMachine(config)

    machine_a.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
        }
    )
    machine_b.record_birth(
        {
            "mint": "mint-b",
            "creator": "creator-b",
            "create_signature": "sig-b",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
        }
    )

    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert sorted(state["mints"]) == ["mint-a", "mint-b"]


def test_record_birth_preserves_pumpfun_curve_followup_addresses(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    machine = OfficialLifecycleStateMachine(config)

    machine.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "pool_address": "curve-a",
            "bonding_curve": "curve-a",
            "associated_bonding_curve": "assoc-curve-a",
        }
    )

    birth = _read_jsonl(config.births_path)[0]
    state_row = machine.state["mints"]["mint-a"]
    assert birth["bonding_curve"] == "curve-a"
    assert birth["associated_bonding_curve"] == "assoc-curve-a"
    assert birth["pool_address"] == "curve-a"
    assert state_row["bonding_curve"] == "curve-a"
    assert state_row["associated_bonding_curve"] == "assoc-curve-a"


def test_active_lifecycle_followup_cycle_revisits_birth_watch_until_trigger(tmp_path: Path) -> None:
    from research.mtp_research.validation.official_lifecycle_watch import run_active_lifecycle_followup_cycle

    config = OfficialLifecycleConfig(data_root=tmp_path, followup_poll_seconds=0)
    initialize_official_lifecycle_namespace(config)
    machine = OfficialLifecycleStateMachine(config)
    machine.record_birth(
        {
            "mint": "mint-a",
            "creator": "creator-a",
            "create_signature": "sig-a",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "bonding_curve": "curve-a",
            "associated_bonding_curve": "assoc-curve-a",
        }
    )
    fetcher = _SequentialFetcher(
        {
            "mint-a": [
                {
                    "mint": "mint-a",
                    "fdv_proxy": 22_000,
                    "event_type": "pumpfun_trade",
                    "transaction_signature": "trade-sig-a",
                    "block_time": 110,
                }
            ]
        }
    )

    result = run_active_lifecycle_followup_cycle(
        machine,
        fetcher,
        signatures_per_mint=4,
        transactions_per_mint=2,
        now=110,
    )

    assert result["active_mints_checked"] == 1
    assert result["path_rows_written"] == 1
    assert result["mints_with_fdv_followup"] == 1
    assert fetcher.calls[0]["mint"] == "mint-a"
    assert fetcher.calls[0]["followup_addresses"] == ["curve-a", "assoc-curve-a"]
    assert machine.state["mints"]["mint-a"]["state"] == "trigger_qualified_active_watch"
    assert machine.state["counters"]["official_crossed_20k_count"] == 1
    assert len(_read_jsonl(config.followup_paths_path)) == 1
    assert len(_read_jsonl(config.events_path)) == 1


def test_initial_birth_followups_are_collected_with_curve_addresses() -> None:
    from research.mtp_research.validation.official_lifecycle_watch import collect_initial_birth_followups

    fetcher = _SequentialFetcher(
        {
            "mint-a": [{"mint": "mint-a", "fdv_proxy": 12_000, "block_time": 110}],
            "mint-b": [{"mint": "mint-b", "fdv_proxy": 8_000, "block_time": 111}],
        }
    )

    results = collect_initial_birth_followups(
        [
            {"mint": "mint-a", "bonding_curve": "curve-a", "associated_bonding_curve": "assoc-a"},
            {"mint": "mint-b", "pool_address": "curve-b"},
        ],
        fetcher,
        signatures_per_mint=4,
        transactions_per_mint=2,
        max_workers=2,
    )

    assert [row["mint"] for row in results] == ["mint-a", "mint-b"]
    assert [row["first_fdv"] for row in results] == [12_000, 8_000]
    assert fetcher.calls[0]["followup_addresses"] == ["curve-a", "assoc-a"]
    assert fetcher.calls[1]["followup_addresses"] == ["curve-b"]


def test_official_fresh_birth_gate_rejects_over_5_second_followup() -> None:
    from research.mtp_research.validation.official_lifecycle_watch import is_official_fresh_birth

    candidate = {"mint": "mint-a", "block_time": 100}

    assert is_official_fresh_birth(candidate, 104.9, max_delay_seconds=5.0) is True
    assert is_official_fresh_birth(candidate, 105.1, max_delay_seconds=5.0) is False


def test_stale_births_are_filtered_before_initial_followup_fetch() -> None:
    from research.mtp_research.validation.official_lifecycle_watch import (
        split_fresh_candidates_for_initial_followup,
    )

    candidates = [
        {"mint": "mint-a", "block_time": 100.0},
        {"mint": "mint-b", "block_time": 100.0},
    ]

    fresh, stale = split_fresh_candidates_for_initial_followup(
        candidates,
        first_attempt_time_by_mint={"mint-a": 104.0, "mint-b": 106.0},
        max_delay_seconds=5.0,
    )

    assert [row["mint"] for row in fresh] == ["mint-a"]
    assert fresh[0]["_official_first_followup_attempt_time"] == 104.0
    assert [row["mint"] for row in stale] == ["mint-b"]
    assert stale[0]["rejection_reason"] == "first_followup_exceeded_5s_freshness_gate"


def test_quality_audit_flags_dropped_trigger_watch_and_milestone_ordering(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    initialize_official_lifecycle_namespace(config)
    _write_jsonl(config.births_path, [{"mint": "mint-a", "observation_id": "birth-a", "create_time": 100}])
    _write_jsonl(
        config.followup_paths_path,
        [
            {
                "mint": "mint-a",
                "timestamp": 110,
                "state": "trigger_qualified_active_watch",
                "fdv_proxy": 25_000,
                "crossed_20k": True,
                "crossed_50k": False,
                "crossed_100k": False,
                "crossed_500k": False,
                "crossed_1m": False,
                "source_provenance": "observed_path_row",
            }
        ],
    )
    config.state_path.write_text(
        json.dumps({"sample_label": OFFICIAL_SAMPLE_LABEL, "mints": {}, "counters": {}}, sort_keys=True),
        encoding="utf-8",
    )

    audit, paths = build_official_lifecycle_quality_audit(config)

    assert "crossed_20k_missing_lifecycle_state" in audit["warnings"]
    assert audit["funnel"]["trigger_qualified_active_watch_mints"] == 0
    assert audit["quality_status"] == "official_lifecycle_watch_needs_repair"
    assert paths["json"].exists()
    assert paths["markdown"].exists()


def test_smoke_run_creates_paths_status_and_quality_audit(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path, max_helius_credits_per_run=50_000)

    result = run_official_lifecycle_smoke(config, target_births=3, execute=True)
    status = official_lifecycle_status(config)

    assert result["execute"] is True
    assert result["smoke_births_observed"] == 3
    assert result["under_5s_followup_count"] == 3
    assert config.births_path.exists()
    assert config.followup_paths_path.exists()
    assert config.transitions_path.exists()
    assert config.status_path.exists()
    assert result["active_watches_created"] >= 1
    assert status["births_observed"] == 3
    assert status["credits_used"] == result["estimated_helius_credits_used"]
    assert result["quality_audit_result"]["network_calls_made"] == 0


def test_guardrail_text_has_no_execution_or_trading_logic(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    manifest = initialize_official_lifecycle_namespace(config)
    text = json.dumps(manifest, sort_keys=True).lower()

    for expected in [
        "no_private_key_logic",
        "no_wallet_execution",
        "no_transaction_signing",
        "no_buy_orders",
        "no_sell_orders",
        "no_swaps",
        "no_order_routing",
        "no_live_trading",
        "no_paper_trading",
        "no_validation",
        "no_backtest",
    ]:
        assert expected in text


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class _SequentialFetcher:
    def __init__(self, events_by_mint: dict[str, list[dict]]) -> None:
        self.events_by_mint = events_by_mint
        self.requests_used = 0
        self.raw_transactions: list[dict] = []
        self.calls: list[dict] = []

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
        followup_addresses: list[str] | None = None,
    ) -> list[dict]:
        self.calls.append(
            {
                "mint": mint,
                "signatures_per_mint": signatures_per_mint,
                "transactions_per_mint": transactions_per_mint,
                "followup_addresses": list(followup_addresses or []),
            }
        )
        self.requests_used += 1
        return list(self.events_by_mint.get(mint, []))
