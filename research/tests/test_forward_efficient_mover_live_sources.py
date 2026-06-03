from pathlib import Path

from research.mtp_research.validation.forward_efficient_mover_observer import (
    ForwardObserverConfig,
    HeliusLiveCandidateSource,
    HeliusLiveSourceConfig,
    HeliusRpcPollingClient,
    HeliusProgramProbeClient,
    MockHeliusEventClient,
    SOL_MINT,
    USDC_MINT,
    build_live_event_candidate,
    default_program_configs,
    mask_helius_endpoint,
    normalize_pumpfun_transaction_event,
    normalize_amm_transaction_event,
    normalize_live_source_event,
    resolve_helius_rpc_url,
    resolve_helius_ws_url,
    run_live_program_probe,
    run_live_source_readiness,
    run_observe,
)


PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


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


def test_build_live_event_candidate_rejects_quote_mints() -> None:
    for mint in (SOL_MINT, USDC_MINT):
        event = normalize_live_source_event(
            {
                "source_adapter": "helius_program_logs_pumpfun",
                "event_type": "pumpfun_trade",
                "mint": mint,
                "fdv_proxy": 1_000_000,
                "event_count": 1,
            }
        )

        assert build_live_event_candidate(event) is None


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


def test_unverified_adapters_require_explicit_enable_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")

    blocked_config = ForwardObserverConfig(data_root=tmp_path, source="helius-pumpswap", max_helius_credits=10)
    blocked_source = HeliusLiveCandidateSource(
        config=HeliusLiveSourceConfig.from_observer_config(blocked_config, load_project_dotenv=False),
        client=MockHeliusEventClient([]),
    )

    assert blocked_source.availability()["available"] is False
    assert blocked_source.availability()["missing_reason"] == "no_verified_program_ids_for_selected_helius_source"

    enabled_config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpswap",
        max_helius_credits=10,
        enable_probed_adapters=True,
    )
    enabled_source = HeliusLiveCandidateSource(
        config=HeliusLiveSourceConfig.from_observer_config(enabled_config, load_project_dotenv=False),
        client=MockHeliusEventClient([]),
    )

    availability = enabled_source.availability()
    assert availability["available"] is True
    assert availability["ready_adapters"] == ["helius_program_logs_pumpswap"]
    assert availability["adapter_enable_gate"] == "explicit_probed_adapter_enable"


def test_helius_rpc_polling_client_hydrates_and_extracts_pumpfun_candidate() -> None:
    calls: list[str] = []

    def fake_post(_url, payload, _timeout):
        calls.append(payload["method"])
        if payload["method"] == "getSignaturesForAddress":
            return {"result": [{"signature": "sig-a", "slot": 100, "blockTime": 1_700_000_000}]}
        assert payload["method"] == "getTransaction"
        return {"result": _pumpfun_buy_transaction()}

    client = HeliusRpcPollingClient("https://mock-helius.invalid/?api-key=test", rpc_post=fake_post)
    events = client.poll_program_events(default_program_configs(), limit=5)

    assert calls == ["getSignaturesForAddress", "getTransaction"]
    assert client.requests_used == 2
    assert events[0]["signature"] == "sig-a"
    assert events[0]["event_type"] == "pumpfun_trade"
    assert events[0]["mint"] == "mint-a"
    assert events[0]["side"] == "buy"
    assert events[0]["token_amount"] == 100.0
    assert events[0]["sol_amount"] == 1.0
    assert events[0]["price_proxy"] == 0.01
    assert events[0]["fdv_proxy"] == 10_000_000.0
    assert events[0]["parse_confidence"] == "hydrated_transaction_token_native_delta"


def test_helius_rpc_polling_client_routes_pumpswap_parser_and_filters_unparseable() -> None:
    calls: list[str] = []

    def fake_post(_url, payload, _timeout):
        calls.append(payload["method"])
        if payload["method"] == "getSignaturesForAddress":
            return {
                "result": [
                    {"signature": "sig-parseable", "slot": 102, "blockTime": 1_700_000_200},
                    {"signature": "sig-unparseable", "slot": 103, "blockTime": 1_700_000_300},
                ]
            }
        assert payload["method"] == "getTransaction"
        if payload["params"][0] == "sig-parseable":
            return {"result": _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")}
        tx = _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
        tx["meta"]["postTokenBalances"] = []
        return {"result": tx}

    config = default_program_configs()["helius_program_logs_pumpswap"]
    enabled_config = config.__class__(
        adapter_name=config.adapter_name,
        program_ids=config.program_ids,
        event_type=config.event_type,
        status="ready",
        notes=config.notes,
    )
    client = HeliusRpcPollingClient("https://mock-helius.invalid/?api-key=test", rpc_post=fake_post, sol_usd_price=100.0)
    events = client.poll_program_events({"helius_program_logs_pumpswap": enabled_config}, limit=5)
    candidates = [build_live_event_candidate(normalize_live_source_event(event)) for event in events]
    candidates = [candidate for candidate in candidates if candidate]

    assert calls == ["getSignaturesForAddress", "getTransaction", "getTransaction"]
    assert len(events) == 2
    assert events[0]["event_type"] == "pumpswap_trade"
    assert events[0]["mint"] == "mint-a"
    assert events[0]["parse_confidence"] == "hydrated_amm_token_quote_delta"
    assert events[1]["mint"] is None
    assert events[1]["missing_reason"] in {"ambiguous_amm_token_or_quote_delta", "zero_token_or_quote_delta_for_fdv_proxy"}
    assert len(candidates) == 1
    assert candidates[0]["source"] == "helius_program_logs_pumpswap"


def test_observe_enabled_pumpswap_writes_only_parseable_amm_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")

    def fake_post(_url, payload, _timeout):
        if payload["method"] == "getSignaturesForAddress":
            return {
                "result": [
                    {"signature": "sig-parseable", "slot": 102, "blockTime": 1_700_000_200},
                    {"signature": "sig-unparseable", "slot": 103, "blockTime": 1_700_000_300},
                ]
            }
        if payload["params"][0] == "sig-parseable":
            return {"result": _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")}
        tx = _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
        tx["meta"]["postTokenBalances"] = []
        return {"result": tx}

    config = ForwardObserverConfig(
        data_root=tmp_path,
        source="helius-pumpswap",
        target_candidates=1,
        max_observe_iterations=1,
        max_helius_credits=10,
        enable_probed_adapters=True,
    )
    live_config = HeliusLiveSourceConfig.from_observer_config(config, load_project_dotenv=False)
    source = HeliusLiveCandidateSource(
        config=live_config,
        client=HeliusRpcPollingClient(
            live_config.rpc_url,
            rpc_post=fake_post,
            sol_usd_price=100.0,
        ),
    )

    result = run_observe(config, source=source)

    assert result["total_candidates_observed"] == 1
    assert result["helius_requests_used"] == 3
    assert result["warnings"] == []
    raw_rows = (config.raw_root / "helius_rpc_raw.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(raw_rows) == 2
    candidate_rows = (config.observation_root / "candidates.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(candidate_rows) == 1


def test_program_probe_client_hydrates_unverified_program_without_candidate_rows() -> None:
    calls: list[str] = []

    def fake_post(_url, payload, _timeout):
        calls.append(payload["method"])
        if payload["method"] == "getSignaturesForAddress":
            return {"result": [{"signature": "sig-probe", "slot": 101, "blockTime": 1_700_000_100}]}
        assert payload["method"] == "getTransaction"
        return {"result": _pumpswap_probe_transaction()}

    client = HeliusProgramProbeClient("https://mock-helius.invalid/?api-key=test", rpc_post=fake_post)
    report = client.probe_programs(
        {"helius_program_logs_pumpswap": default_program_configs()["helius_program_logs_pumpswap"]},
        limit=10,
        hydrate_sample=True,
    )

    assert calls == ["getSignaturesForAddress", "getTransaction"]
    assert client.requests_used == 2
    assert report["signatures_seen"] == 1
    assert report["transactions_hydrated"] == 1
    assert report["candidate_rows_created"] == 0
    assert report["program_instruction_count"] == 1
    assert report["instruction_clusters"][0]["program_id"] == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    assert report["instruction_clusters"][0]["account_count"] == 4
    assert report["instruction_clusters"][0]["example_signatures"] == ["sig-probe"]


def test_program_probe_client_reports_parseable_amm_events_without_candidate_rows() -> None:
    def fake_post(_url, payload, _timeout):
        if payload["method"] == "getSignaturesForAddress":
            return {"result": [{"signature": "sig-amm", "slot": 102, "blockTime": 1_700_000_200}]}
        return {"result": _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")}

    client = HeliusProgramProbeClient(
        "https://mock-helius.invalid/?api-key=test",
        rpc_post=fake_post,
        sol_usd_price=100.0,
    )
    report = client.probe_programs(
        {"helius_program_logs_pumpswap": default_program_configs()["helius_program_logs_pumpswap"]},
        limit=10,
        hydrate_sample=True,
    )

    assert report["parseable_event_count"] == 1
    assert report["parsed_event_examples"][0]["mint"] == "mint-a"
    assert report["parsed_event_examples"][0]["side"] == "buy"
    assert report["parsed_event_examples"][0]["fdv_proxy"] == 1_000_000_000.0
    assert report["candidate_rows_created"] == 0


def test_program_probe_client_hydrates_multiple_programs_balanced() -> None:
    hydrated: list[str] = []

    def fake_post(_url, payload, _timeout):
        if payload["method"] == "getSignaturesForAddress":
            program_id = payload["params"][0]
            return {
                "result": [
                    {"signature": f"{program_id}-sig-1", "slot": 1, "blockTime": 1_700_000_001},
                    {"signature": f"{program_id}-sig-2", "slot": 2, "blockTime": 1_700_000_002},
                ]
            }
        signature = payload["params"][0]
        hydrated.append(signature)
        return {"result": _amm_buy_transaction(program_id=signature.split("-sig-")[0])}

    client = HeliusProgramProbeClient(
        "https://mock-helius.invalid/?api-key=test",
        rpc_post=fake_post,
        sol_usd_price=100.0,
    )
    report = client.probe_programs(
        {"helius_program_logs_raydium": default_program_configs()["helius_program_logs_raydium"]},
        limit=2,
        hydrate_sample=True,
    )

    assert any(signature.startswith("LanMV9") for signature in hydrated)
    assert any(signature.startswith("CPMMoo") for signature in hydrated)
    assert report["transactions_hydrated"] == 4


def test_run_live_program_probe_writes_reports_and_keeps_observer_rows_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HELIUS_API_KEY", "test-secret-key")

    def fake_post(_url, payload, _timeout):
        if payload["method"] == "getSignaturesForAddress":
            return {"result": [{"signature": "sig-probe", "slot": 101, "blockTime": 1_700_000_100}]}
        return {"result": _pumpswap_probe_transaction()}

    config = ForwardObserverConfig(data_root=tmp_path, source="helius-pumpswap", max_helius_credits=10)
    report = run_live_program_probe(
        config,
        source="helius-pumpswap",
        limit=10,
        hydrate_sample=True,
        rpc_post=fake_post,
        load_project_dotenv=False,
    )

    assert report["readiness_classification"] in {
        "program_probe_semantics_unknown",
        "program_probe_semantics_maybe_viable",
        "program_probe_candidate_fields_parseable",
    }
    assert report["candidate_rows_created"] == 0
    assert report["network_calls_made"] == 2
    assert (config.report_root / "live_program_probe_helius-pumpswap.json").exists()
    assert (config.report_root / "live_program_probe_helius-pumpswap.md").exists()
    assert not (config.observation_root / "candidates.jsonl").exists()


def test_normalize_pumpfun_transaction_event_fails_closed_without_fdv() -> None:
    tx = _pumpfun_buy_transaction()
    tx["meta"]["postTokenBalances"] = []

    event = normalize_pumpfun_transaction_event(
        tx,
        source_adapter="helius_program_logs_pumpfun",
        program_id=PUMP_FUN_PROGRAM_ID,
        valuation_supply_proxy=1_000_000_000,
    )

    assert event["mint"] is None
    assert event["fdv_proxy"] is None
    assert event["missing_reason"] == "missing_token_or_native_delta_for_fdv_proxy"


def test_normalize_pumpfun_transaction_event_rejects_quote_token_delta() -> None:
    tx = _pumpfun_buy_transaction()
    tx["meta"]["preTokenBalances"][0]["mint"] = USDC_MINT
    tx["meta"]["postTokenBalances"][0]["mint"] = USDC_MINT

    event = normalize_pumpfun_transaction_event(
        tx,
        source_adapter="helius_program_logs_pumpfun",
        program_id=PUMP_FUN_PROGRAM_ID,
        valuation_supply_proxy=1_000_000_000,
    )

    assert event["mint"] is None
    assert event["fdv_proxy"] is None
    assert event["missing_reason"] == "missing_token_or_native_delta_for_fdv_proxy"


def test_normalize_pumpswap_transaction_event_extracts_single_token_quote_pair() -> None:
    event = normalize_amm_transaction_event(
        _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"),
        source_adapter="helius_program_logs_pumpswap",
        program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
        event_type="pumpswap_trade",
        valuation_supply_proxy=1_000_000_000,
        sol_usd_price=100.0,
    )

    assert event["event_type"] == "pumpswap_trade"
    assert event["mint"] == "mint-a"
    assert event["pool_address"] == "pool-a"
    assert event["wallet"] == "buyer-a"
    assert event["side"] == "buy"
    assert event["token_amount"] == 100.0
    assert event["sol_amount"] == 1.0
    assert event["price_proxy"] == 0.01
    assert event["fdv_proxy"] == 1_000_000_000.0
    assert event["parse_confidence"] == "hydrated_amm_token_quote_delta"


def test_normalize_raydium_transaction_event_extracts_single_token_quote_pair() -> None:
    event = normalize_amm_transaction_event(
        _amm_buy_transaction(program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"),
        source_adapter="helius_program_logs_raydium",
        program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
        event_type="raydium_trade_or_pool_update",
        valuation_supply_proxy=1_000_000_000,
        sol_usd_price=100.0,
    )

    assert event["event_type"] == "raydium_trade_or_pool_update"
    assert event["mint"] == "mint-a"
    assert event["pool_address"] == "pool-a"
    assert event["side"] == "buy"
    assert event["fdv_proxy"] == 1_000_000_000.0
    assert event["parse_confidence"] == "hydrated_amm_token_quote_delta"


def test_normalize_amm_transaction_event_fails_closed_on_multitoken_route() -> None:
    tx = _amm_buy_transaction(program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
    tx["meta"]["preTokenBalances"].append(
        {
            "accountIndex": 5,
            "mint": "mint-b",
            "owner": "buyer-a",
            "uiTokenAmount": {"uiAmountString": "0", "decimals": 6},
        }
    )
    tx["meta"]["postTokenBalances"].append(
        {
            "accountIndex": 5,
            "mint": "mint-b",
            "owner": "buyer-a",
            "uiTokenAmount": {"uiAmountString": "10", "decimals": 6},
        }
    )

    event = normalize_amm_transaction_event(
        tx,
        source_adapter="helius_program_logs_pumpswap",
        program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
        event_type="pumpswap_trade",
        valuation_supply_proxy=1_000_000_000,
        sol_usd_price=100.0,
    )

    assert event["mint"] is None
    assert event["fdv_proxy"] is None
    assert event["missing_reason"] == "ambiguous_amm_token_or_quote_delta"


def test_normalize_amm_transaction_event_uses_single_direction_log_when_owner_pairs_include_pool() -> None:
    tx = _amm_buy_transaction(program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")
    tx["transaction"]["message"]["accountKeys"][0]["signer"] = False

    event = normalize_amm_transaction_event(
        tx,
        source_adapter="helius_program_logs_raydium",
        program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
        event_type="raydium_trade_or_pool_update",
        valuation_supply_proxy=1_000_000_000,
        sol_usd_price=100.0,
    )

    assert event["mint"] == "mint-a"
    assert event["wallet"] == "buyer-a"
    assert event["side"] == "buy"
    assert event["missing_reason"] is None


def test_normalize_amm_transaction_event_uses_native_sol_when_signer_quote_token_missing() -> None:
    tx = _amm_buy_transaction(program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")
    tx["meta"]["preTokenBalances"] = [row for row in tx["meta"]["preTokenBalances"] if row["mint"] != "So11111111111111111111111111111111111111112"]
    tx["meta"]["postTokenBalances"] = [row for row in tx["meta"]["postTokenBalances"] if row["mint"] != "So11111111111111111111111111111111111111112"]
    tx["meta"]["preBalances"] = [2_000_000_000, 10_000_000_000, 0, 0, 0, 0]
    tx["meta"]["postBalances"] = [1_000_000_000, 11_000_000_000, 0, 0, 0, 0]

    event = normalize_amm_transaction_event(
        tx,
        source_adapter="helius_program_logs_raydium",
        program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
        event_type="raydium_trade_or_pool_update",
        valuation_supply_proxy=1_000_000_000,
        sol_usd_price=100.0,
    )

    assert event["mint"] == "mint-a"
    assert event["wallet"] == "buyer-a"
    assert event["side"] == "buy"
    assert event["sol_amount"] == 1.0
    assert event["fdv_proxy"] == 1_000_000_000.0


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


def _pumpfun_buy_transaction() -> dict:
    return {
        "slot": 100,
        "blockTime": 1_700_000_000,
        "transaction": {
            "signatures": ["sig-a"],
            "message": {
                "accountKeys": [
                    {"pubkey": "buyer-a", "signer": True, "writable": True},
                    {"pubkey": "bonding-curve-a", "signer": False, "writable": True},
                    {"pubkey": "token-account-a", "signer": False, "writable": True},
                ],
                "instructions": [
                    {
                        "programId": PUMP_FUN_PROGRAM_ID,
                        "accounts": ["mint-a", "bonding-curve-a", "associated-curve-a", "buyer-a"],
                    }
                ],
            },
        },
        "meta": {
            "err": None,
            "logMessages": ["Program log: Instruction: Buy"],
            "preBalances": [2_000_000_000, 5_000_000_000, 0],
            "postBalances": [1_000_000_000, 6_000_000_000, 0],
            "preTokenBalances": [
                {
                    "accountIndex": 2,
                    "mint": "mint-a",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "0", "decimals": 6},
                }
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 2,
                    "mint": "mint-a",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "100", "decimals": 6},
                }
            ],
        },
    }


def _pumpswap_probe_transaction() -> dict:
    return {
        "slot": 101,
        "blockTime": 1_700_000_100,
        "transaction": {
            "signatures": ["sig-probe"],
            "message": {
                "accountKeys": [
                    {"pubkey": "payer-a", "signer": True, "writable": True},
                    {"pubkey": "pool-a", "signer": False, "writable": True},
                    {"pubkey": "mint-a", "signer": False, "writable": False},
                ],
                "instructions": [
                    {
                        "programId": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "accounts": ["payer-a", "pool-a", "mint-a", "quote-a"],
                        "data": "3Bxs4NN8M2Yn4TLb",
                    }
                ],
            },
        },
        "meta": {
            "err": None,
            "logMessages": ["Program log: Instruction: Swap"],
            "innerInstructions": [],
        },
    }


def _amm_buy_transaction(*, program_id: str) -> dict:
    return {
        "slot": 102,
        "blockTime": 1_700_000_200,
        "transaction": {
            "signatures": ["sig-amm"],
            "message": {
                "accountKeys": [
                    {"pubkey": "buyer-a", "signer": True, "writable": True},
                    {"pubkey": "pool-a", "signer": False, "writable": True},
                    {"pubkey": "buyer-token-a", "signer": False, "writable": True},
                    {"pubkey": "buyer-sol-a", "signer": False, "writable": True},
                    {"pubkey": "pool-token-a", "signer": False, "writable": True},
                    {"pubkey": "pool-sol-a", "signer": False, "writable": True},
                ],
                "instructions": [
                    {
                        "programId": program_id,
                        "accounts": ["buyer-a", "pool-a", "mint-a", "So11111111111111111111111111111111111111112"],
                        "data": "3Bxs4NN8M2Yn4TLb",
                    }
                ],
            },
        },
        "meta": {
            "err": None,
            "logMessages": ["Program log: Instruction: BuyExactIn"],
            "preTokenBalances": [
                {
                    "accountIndex": 2,
                    "mint": "mint-a",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "0", "decimals": 6},
                },
                {
                    "accountIndex": 3,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "2", "decimals": 9},
                },
                {
                    "accountIndex": 4,
                    "mint": "mint-a",
                    "owner": "pool-a",
                    "uiTokenAmount": {"uiAmountString": "1000", "decimals": 6},
                },
                {
                    "accountIndex": 5,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": "pool-a",
                    "uiTokenAmount": {"uiAmountString": "10", "decimals": 9},
                },
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 2,
                    "mint": "mint-a",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "100", "decimals": 6},
                },
                {
                    "accountIndex": 3,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": "buyer-a",
                    "uiTokenAmount": {"uiAmountString": "1", "decimals": 9},
                },
                {
                    "accountIndex": 4,
                    "mint": "mint-a",
                    "owner": "pool-a",
                    "uiTokenAmount": {"uiAmountString": "900", "decimals": 6},
                },
                {
                    "accountIndex": 5,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": "pool-a",
                    "uiTokenAmount": {"uiAmountString": "11", "decimals": 9},
                },
            ],
            "innerInstructions": [],
        },
    }
