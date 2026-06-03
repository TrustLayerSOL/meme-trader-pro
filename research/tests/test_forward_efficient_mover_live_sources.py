from pathlib import Path

from research.mtp_research.validation.forward_efficient_mover_observer import (
    ForwardObserverConfig,
    HeliusLiveCandidateSource,
    HeliusLiveSourceConfig,
    MockHeliusEventClient,
    build_live_event_candidate,
    default_program_configs,
    mask_helius_endpoint,
    normalize_live_source_event,
    resolve_helius_rpc_url,
    resolve_helius_ws_url,
    run_live_source_readiness,
    run_observe,
)


def test_helius_url_resolution_masks_key(monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")
    monkeypatch.delenv("HELIUS_RPC_URL", raising=False)
    monkeypatch.delenv("HELIUS_WS_URL", raising=False)

    rpc = resolve_helius_rpc_url(load_project_dotenv=False)
    ws = resolve_helius_ws_url(load_project_dotenv=False)

    assert rpc == "https://mainnet.helius-rpc.com/?api-key=test-secret-key"
    assert ws == "wss://mainnet.helius-rpc.com/?api-key=test-secret-key"
    assert mask_helius_endpoint(rpc) == "https://mainnet.helius-rpc.com/?api-key=***masked***"
    assert "test-secret-key" not in mask_helius_endpoint(ws)


def test_live_readiness_blocks_without_helius_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.delenv("HELIUS_RPC_URL", raising=False)
    monkeypatch.delenv("HELIUS_WS_URL", raising=False)
    config = ForwardObserverConfig(data_root=tmp_path)

    report = run_live_source_readiness(config, perform_network_checks=False, load_project_dotenv=False)

    assert report["readiness_classification"] == "live_source_blocked_no_helius_config"
    assert report["helius"]["api_key_present"] is False
    assert "api-key" not in report["helius"]["rpc_endpoint_masked"]
    assert (config.report_root / "live_source_readiness.json").exists()
    assert (config.report_root / "live_source_readiness.md").exists()


def test_default_program_configs_fail_closed_for_unverified_ids() -> None:
    configs = default_program_configs()

    assert configs["helius_program_logs_pumpfun"].status == "ready"
    assert configs["helius_program_logs_pumpswap"].status == "needs_probe_verification"
    assert configs["helius_program_logs_raydium"].status == "needs_probe_verification"
    assert configs["helius_program_logs_pumpfun"].program_ids == ["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"]


def test_normalized_live_event_schema_preserves_missing_fields() -> None:
    event = normalize_live_source_event(
        {
            "source_adapter": "helius_program_logs_pumpfun",
            "signature": "sig-a",
            "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
            "event_type": "pumpfun_trade",
            "mint": "mint-a",
            "fdv_proxy": 21_000,
            "buy_count": 2,
            "sell_count": 1,
        }
    )

    assert event["source"] == "helius"
    assert event["source_adapter"] == "helius_program_logs_pumpfun"
    assert event["event_type"] == "pumpfun_trade"
    assert event["mint"] == "mint-a"
    assert event["fdv_proxy"] == 21_000
    assert event["pool_address"] is None
    assert event["parse_confidence"] == "event_payload"
    assert event["missing_reason"] is None


def test_build_live_event_candidate_for_trigger_crossing() -> None:
    event = normalize_live_source_event(
        {
            "source_adapter": "helius_program_logs_pumpfun",
            "event_type": "pumpfun_trade",
            "mint": "mint-a",
            "fdv_proxy": 32_000,
            "event_count": 4,
            "buy_count": 3,
            "sell_count": 1,
            "active_wallet_count": 3,
        }
    )

    candidate = build_live_event_candidate(event)

    assert candidate["mint"] == "mint-a"
    assert candidate["source"] == "helius_program_logs_pumpfun"
    assert candidate["fdv_proxy"] == 32_000
    assert candidate["event_count"] == 4
    assert candidate["buy_count"] == 3
    assert candidate["sell_count"] == 1
    assert candidate["active_wallets"] == 3


def test_observe_with_mocked_helius_live_source_writes_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")
    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-all",
        target_candidates=1,
        max_observe_iterations=1,
        max_helius_credits=10,
    )
    source = HeliusLiveCandidateSource(
        config=HeliusLiveSourceConfig.from_observer_config(config, load_project_dotenv=False),
        client=MockHeliusEventClient(
            [
                {
                    "source_adapter": "helius_program_logs_pumpfun",
                    "event_type": "pumpfun_trade",
                    "mint": "mint-a",
                    "signature": "sig-a",
                    "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                    "fdv_proxy": 25_000,
                    "event_count": 3,
                    "buy_count": 2,
                    "sell_count": 1,
                    "active_wallet_count": 2,
                }
            ]
        ),
    )

    result = run_observe(config, source=source)

    assert result["total_candidates_observed"] == 1
    assert result["helius_requests_used"] == 1
    assert result["readiness_classification"] == "forward_observer_ready_for_observation"
    assert (config.raw_root / "helius_rpc_raw.jsonl").exists()


def test_live_source_budget_cap_blocks_fetch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")
    config = ForwardObserverConfig(data_root=tmp_path, source="helius-all", max_helius_credits=0)
    source = HeliusLiveCandidateSource(
        config=HeliusLiveSourceConfig.from_observer_config(config, load_project_dotenv=False),
        client=MockHeliusEventClient([{"mint": "mint-a", "fdv_proxy": 30_000}]),
    )

    assert source.availability()["available"] is False
    assert source.availability()["missing_reason"] == "max_helius_credits_zero_or_negative"


def test_forward_observer_live_stack_has_no_execution_logic() -> None:
    module_paths = [
        Path("research/mtp_research/validation/forward_efficient_mover_observer.py"),
        Path("research/mtp_research/validation/run_forward_efficient_mover_observer.py"),
    ]
    forbidden = [
        "sendtransaction",
        "signtransaction",
        "jupiter swap",
        "place_order",
        "submit_order",
        "order_routing",
        "auto_buy",
        "auto_sell",
    ]

    for path in module_paths:
        text = path.read_text(encoding="utf-8").lower()
        text = text.replace("no_order_routing", "")
        text = text.replace("no_auto_buy_sell", "")
        text = text.replace('"order_routing"', "")
        for pattern in forbidden:
            assert pattern not in text, f"{pattern} found in {path}"
