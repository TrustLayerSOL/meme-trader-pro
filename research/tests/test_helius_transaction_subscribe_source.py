from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.helius_transaction_subscribe_source import (
    HeliusBondingCurveLiveWatchSource,
    HeliusTransactionSubscribeCreateSource,
    build_account_subscribe_request,
    build_transaction_subscribe_request,
    decode_pumpfun_transaction_subscribe_notification,
    helius_transaction_subscribe_capability_audit,
    run_bonding_curve_account_probe_for_create_event,
)
from research.mtp_research.validation.pumpfun_bonding_curve import (
    PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX,
    PUMP_FUN_PROGRAM_ID,
    bonding_curve_pda,
    mint_authority_pda,
)
from research.mtp_research.validation.rule_runtime_v1 import RuleRuntimeConfig, initialize_rule_runtime


def _base58_encode(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = int.from_bytes(raw, "big")
    encoded = ""
    while value:
        value, rem = divmod(value, 58)
        encoded = alphabet[rem] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + (encoded or "1")


class FakeWebSocket:
    def __init__(self, messages: list[dict] | None = None) -> None:
        self.messages = [json.dumps(row) for row in (messages or [])]
        self.sent: list[dict] = []

    def __enter__(self) -> "FakeWebSocket":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self, timeout: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise TimeoutError("empty")


def test_transaction_subscribe_payload_filters_pumpfun_create_authority() -> None:
    payload = build_transaction_subscribe_request(request_id="test-sub")

    assert payload["method"] == "transactionSubscribe"
    assert payload["params"][0]["failed"] is False
    assert payload["params"][0]["accountRequired"] == [PUMP_FUN_PROGRAM_ID, mint_authority_pda()]
    assert payload["params"][1]["commitment"] == "processed"
    assert payload["params"][1]["transactionDetails"] == "full"
    assert payload["params"][1]["showRewards"] is False
    assert payload["params"][1]["encoding"] == "jsonParsed"
    assert payload["params"][1]["maxSupportedTransactionVersion"] == 0


def test_account_subscribe_payload_watches_bonding_curve_processed_base64() -> None:
    payload = build_account_subscribe_request("curve-a", request_id="watch-a")

    assert payload["method"] == "accountSubscribe"
    assert payload["id"] == "watch-a"
    assert payload["params"][0] == "curve-a"
    assert payload["params"][1]["commitment"] == "processed"
    assert payload["params"][1]["encoding"] == "base64"


def test_decode_transaction_subscribe_create_v2_without_get_transaction() -> None:
    mint = "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump"
    curve = bonding_curve_pda(mint)
    notification = {
        "params": {
            "result": {
                "signature": "sig-a",
                "slot": 123,
                "transaction": {
                    "transaction": {
                        "signatures": ["sig-a"],
                        "message": {
                            "instructions": [
                                {
                                    "programId": PUMP_FUN_PROGRAM_ID,
                                    "accounts": [mint, "payer", curve, "assoc", "metadata", "creator-a"],
                                    "data": _base58_encode(bytes.fromhex(PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX) + b"payload"),
                                }
                            ]
                        },
                    }
                },
            }
        }
    }

    rows = decode_pumpfun_transaction_subscribe_notification(notification, observed_at=100.0)

    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == "txsub_sig-a_123_0"
    assert row["signature"] == "sig-a"
    assert row["slot"] == 123
    assert row["observed_at"] == 100.0
    assert row["mint"] == mint
    assert row["bonding_curve_from_ix"] == curve
    assert row["bonding_curve_pda"] == curve
    assert row["bonding_curve"] == curve
    assert row["bonding_curve_verified"] is True
    assert row["creator"] == "creator-a"
    assert row["instruction_type"] == "create_v2"
    assert row["parser_status"] == "decoded"
    assert row["source"] == "transactionSubscribe"


def test_capability_audit_reports_supported_methods_and_writes_reports(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    sockets: list[FakeWebSocket] = []

    def ws_connect(_url: str, **_kwargs: object) -> FakeWebSocket:
        ws = FakeWebSocket(
            [
                {"id": "mtp-transaction-subscribe-capability", "result": 1},
                {"id": "mtp-account-subscribe-capability", "result": 2},
            ]
        )
        sockets.append(ws)
        return ws

    def rpc_post(_url: str, payload: dict, _timeout: int) -> dict:
        assert payload["method"] == "getAccountInfo"
        assert payload["params"][1]["commitment"] == "processed"
        return {"result": {"value": None}}

    audit = helius_transaction_subscribe_capability_audit(
        config,
        endpoints=[{"name": "fake", "websocket_url": "wss://fake", "rpc_url": "https://fake"}],
        ws_connect=ws_connect,
        rpc_post=rpc_post,
    )

    assert audit["recommended_endpoint"]["name"] == "fake"
    assert audit["endpoints"][0]["transactionSubscribe_supported"] is True
    assert audit["endpoints"][0]["accountSubscribe_supported"] is True
    assert audit["endpoints"][0]["getAccountInfo_processed_supported"] is True
    assert config.helius_transaction_subscribe_capability_audit_json_path.exists()
    assert "Helius transactionSubscribe Capability Audit" in config.helius_transaction_subscribe_capability_audit_md_path.read_text(encoding="utf-8")


def test_source_writes_raw_and_decoded_create_stream_rows(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    mint = "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump"
    curve = bonding_curve_pda(mint)
    notification = {
        "params": {
            "result": {
                "signature": "sig-a",
                "slot": 123,
                "transaction": {
                    "transaction": {
                        "signatures": ["sig-a"],
                        "message": {
                            "instructions": [
                                {
                                    "programId": PUMP_FUN_PROGRAM_ID,
                                    "accounts": [mint, "payer", curve, "assoc", "metadata", "creator-a"],
                                    "data": _base58_encode(bytes.fromhex(PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX)),
                                }
                            ]
                        },
                    }
                },
            }
        }
    }

    def ws_connect(_url: str, **_kwargs: object) -> FakeWebSocket:
        return FakeWebSocket([{"id": "mtp-pumpfun-transaction-subscribe", "result": 1}, notification])

    source = HeliusTransactionSubscribeCreateSource(
        config=config,
        websocket_url="wss://fake",
        ws_connect=ws_connect,
        now_fn=iter([100.0, 100.1, 100.2]).__next__,
    )
    rows = source.fetch_create_events(max_events=1, max_seconds=1)

    assert len(rows) == 1
    assert rows[0]["mint"] == mint
    assert config.pumpfun_transaction_subscribe_raw_path.exists()
    assert config.pumpfun_create_stream_events_path.exists()
    assert "transactionSubscribe" in config.pumpfun_transaction_subscribe_raw_path.read_text(encoding="utf-8")


def test_source_invokes_create_callback_while_stream_is_active(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    mint = "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump"
    curve = bonding_curve_pda(mint)

    def notification(signature: str, slot: int) -> dict:
        return {
            "params": {
                "result": {
                    "signature": signature,
                    "slot": slot,
                    "transaction": {
                        "transaction": {
                            "signatures": [signature],
                            "message": {
                                "instructions": [
                                    {
                                        "programId": PUMP_FUN_PROGRAM_ID,
                                        "accounts": [mint, "payer", curve, "assoc", "metadata", "creator-a"],
                                        "data": _base58_encode(bytes.fromhex(PUMP_FUN_CREATE_V2_DISCRIMINATOR_HEX)),
                                    }
                                ]
                            },
                        }
                    },
                }
            }
        }

    websocket = FakeWebSocket(
        [
            {"id": "mtp-pumpfun-transaction-subscribe", "result": 1},
            notification("sig-a", 123),
            notification("sig-b", 124),
        ]
    )

    def ws_connect(_url: str, **_kwargs: object) -> FakeWebSocket:
        return websocket

    callback_rows: list[tuple[str, int]] = []

    def on_create_event(row: dict) -> None:
        callback_rows.append((row["signature"], len(websocket.messages)))

    source = HeliusTransactionSubscribeCreateSource(
        config=config,
        websocket_url="wss://fake",
        ws_connect=ws_connect,
        now_fn=iter([100.0, 100.1, 100.2, 100.3]).__next__,
    )
    rows = source.fetch_create_events(max_events=2, max_seconds=1, on_create_event=on_create_event)

    assert [row["signature"] for row in rows] == ["sig-a", "sig-b"]
    assert callback_rows[0] == ("sig-a", 1)
    assert callback_rows[1] == ("sig-b", 0)


def test_get_account_info_probe_row_uses_min_context_slot_and_emits_runtime_event(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    seen_payloads: list[dict] = []

    class FakeProbe:
        requests_used = 1
        http_429_count = 0
        rpc_url = "https://fake-rpc"
        timeout_seconds = 3

        def _rpc_post(self, _rpc_url: str, payload: dict, _timeout: int) -> dict:
            assert payload["method"] == "getAccountInfo"
            assert payload["params"][0] == "mint-a"
            return {"result": {"value": {"owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}}}

        def probe_create_event(self, create_event: dict, *, now_fn: object) -> object:
            seen_payloads.append(create_event)

            class Result:
                probe_status = "success"
                failure_reason = None
                getAccountInfo_latency_ms = 7.0
                accountSubscribe_latency_ms = None

                def to_runtime_event(self, timestamp: float | None = None) -> dict:
                    return {
                        "event_id": "fdv-a",
                        "mint": create_event["mint"],
                        "timestamp": timestamp or 101.0,
                        "event_observed_at": create_event["observed_at"],
                        "fdv_proxy": 9_000.0,
                        "fdv_usd": 9_000.0,
                        "fdv_sol": 90.0,
                        "fdv_units": "usd",
                        "price_sol": 0.00009,
                        "sol_usd": 100.0,
                        "token_decimals": 6,
                        "quote_decimals": 9,
                        "calculation_status": "fdv_usd_available",
                        "quote_type": "sol",
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                        "fdv_probe_method": "getAccountInfo_processed_bonding_curve",
                    }

            return Result()

    emitted: list[dict] = []
    create_event = {
        "event_id": "txsub_sig-a_123_0",
        "signature": "sig-a",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "mint-a",
        "bonding_curve": "curve-a",
    }

    row = run_bonding_curve_account_probe_for_create_event(
        config,
        create_event,
        probe=FakeProbe(),
        event_callback=emitted.append,
        now_fn=iter([100.5, 100.7]).__next__,
    )

    assert seen_payloads[0]["min_context_slot"] == 123
    assert row["winning_probe_source"] == "getAccountInfo_processed"
    assert row["probe_status"] == "success"
    assert row["source_create_signature"] == "sig-a"
    assert row["create_observed_at"] == 100.0
    assert row["observed_to_probe_started_ms"] == 500.0
    assert row["probe_started_to_first_curve_state_ms"] == 200.0
    assert row["observed_to_first_fdv_emitted_ms"] == 700.0
    assert row["fdv_proxy"] == 9_000.0
    assert row["fdv_usd"] == 9_000.0
    assert row["fdv_sol"] == 90.0
    assert row["fdv_units"] == "usd"
    assert row["calculation_status"] == "fdv_usd_available"
    assert row["mint_account_owner"] == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    assert row["token_program"] == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    assert row["mint_account_owner_status"] == "found"
    assert emitted[0]["fdv_usd"] == 9_000.0
    assert emitted[0]["fdv_sol"] == 90.0
    assert emitted[0]["fdv_units"] == "usd"
    assert emitted[0]["token_program"] == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    assert emitted[0]["source_adapter"] == "helius_transaction_subscribe_bonding_curve_probe"
    assert json.loads(config.bonding_curve_account_probe_events_path.read_text(encoding="utf-8").splitlines()[0])["probe_status"] == "success"


def test_probe_helper_can_defer_mint_owner_lookup_for_first_fdv_hot_path(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)

    class FakeProbe:
        requests_used = 0
        http_429_count = 0
        rpc_url = "https://fake-rpc"
        timeout_seconds = 3

        def _rpc_post(self, _rpc_url: str, payload: dict, _timeout: int) -> dict:
            raise AssertionError(f"mint owner lookup should be deferred, got {payload}")

        def probe_create_event(self, create_event: dict, *, now_fn: object) -> object:
            class Result:
                probe_status = "success"
                failure_reason = None
                getAccountInfo_latency_ms = 7.0
                accountSubscribe_latency_ms = None

                def to_runtime_event(self, timestamp: float | None = None) -> dict:
                    return {
                        "event_id": "fdv-a",
                        "mint": create_event["mint"],
                        "timestamp": timestamp or 101.0,
                        "event_observed_at": create_event["observed_at"],
                        "fdv_proxy": 9_000.0,
                        "fdv_usd": 9_000.0,
                        "fdv_units": "usd",
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                        "fdv_probe_method": "getAccountInfo_processed_bonding_curve",
                    }

            return Result()

    emitted: list[dict] = []
    create_event = {
        "event_id": "txsub_sig-a_123_0",
        "signature": "sig-a",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "mint-a",
        "bonding_curve": "curve-a",
    }

    row = run_bonding_curve_account_probe_for_create_event(
        config,
        create_event,
        probe=FakeProbe(),
        event_callback=emitted.append,
        now_fn=iter([100.5, 100.7]).__next__,
        include_mint_account_owner=False,
    )

    assert row["probe_status"] == "success"
    assert row["observed_to_probe_started_ms"] == 500.0
    assert row["mint_account_owner"] is None
    assert row["token_program"] is None
    assert row["mint_account_owner_status"] == "deferred_first_fdv_hot_path"
    assert emitted[0]["mint_account_owner_status"] == "deferred_first_fdv_hot_path"


def test_probe_helper_emits_follow_up_account_state_rows_for_confirmation(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)

    class FakeProbe:
        requests_used = 1
        http_429_count = 0

        def __init__(self) -> None:
            self.calls = 0

        def probe_create_event(self, create_event: dict, *, now_fn: object) -> object:
            self.calls += 1
            fdv = 21_000.0 if self.calls == 1 else 22_000.0

            class Result:
                probe_status = "success"
                failure_reason = None
                fdv_proxy = fdv
                fdv_usd = fdv
                fdv_sol = fdv / 100.0
                fdv_quote = None
                fdv_units = "usd"
                price_sol = 0.0001
                price_quote = None
                sol_usd = 100.0
                quote_decimals = 9
                token_decimals = 6
                calculation_status = "fdv_usd_available"
                quote_type = "sol"
                account_state = {"virtual_token_reserves": 1, "virtual_sol_reserves": 1}
                getAccountInfo_latency_ms = 5.0
                accountSubscribe_latency_ms = None
                decode_finished_at = 100.0 + self.calls
                helius_rpc_request_count = 1
                http_429_count = 0

                def to_runtime_event(self, timestamp: float | None = None) -> dict:
                    return {
                        "event_id": f"fdv-follow-{fdv}",
                        "mint": create_event["mint"],
                        "timestamp": timestamp or self.decode_finished_at,
                        "event_observed_at": create_event["observed_at"],
                        "fdv_proxy": self.fdv_proxy,
                        "fdv_usd": self.fdv_usd,
                        "fdv_sol": self.fdv_sol,
                        "fdv_units": self.fdv_units,
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                    }

            return Result()

    emitted: list[dict] = []
    sleep_calls: list[float] = []
    probe = FakeProbe()
    row = run_bonding_curve_account_probe_for_create_event(
        config,
        {
            "event_id": "txsub_sig-follow_123_0",
            "signature": "sig-follow",
            "slot": 123,
            "observed_at": 100.0,
            "mint": "mint-follow",
            "bonding_curve": "curve-follow",
        },
        probe=probe,
        event_callback=emitted.append,
        now_fn=iter([100.0, 100.01, 101.0, 101.01]).__next__,
        sleep_fn=sleep_calls.append,
        account_not_found_retry_delays=(),
        follow_up_probe_delays=(0.25,),
    )

    rows = [json.loads(line) for line in config.bonding_curve_account_probe_events_path.read_text(encoding="utf-8").splitlines()]
    assert probe.calls == 2
    assert sleep_calls == [0.25]
    assert row["probe_status"] == "success"
    assert [event["fdv_usd"] for event in emitted] == [21_000.0, 22_000.0]
    assert [row["probe_phase"] for row in rows] == ["initial", "follow_up"]
    assert rows[1]["fdv_units"] == "usd"


def test_account_not_found_retry_recovers_fast_first_fdv(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    seen_payloads: list[dict] = []

    class FakeProbe:
        requests_used = 2
        http_429_count = 0

        def __init__(self) -> None:
            self.calls = 0

        def probe_create_event(self, create_event: dict, *, now_fn: object) -> object:
            self.calls += 1
            seen_payloads.append(create_event)

            if self.calls == 1:
                class MissingResult:
                    probe_status = "failed"
                    failure_reason = "account_not_found"
                    getAccountInfo_latency_ms = 5.0
                    accountSubscribe_latency_ms = None
                    helius_rpc_request_count = 1
                    http_429_count = 0

                return MissingResult()

            class SuccessResult:
                probe_status = "success"
                failure_reason = None
                getAccountInfo_latency_ms = 8.0
                accountSubscribe_latency_ms = None
                decode_finished_at = 100.22
                helius_rpc_request_count = 2
                http_429_count = 0

                def to_runtime_event(self, timestamp: float | None = None) -> dict:
                    return {
                        "event_id": "fdv-retry",
                        "mint": create_event["mint"],
                        "timestamp": timestamp or 100.22,
                        "event_observed_at": create_event["observed_at"],
                        "fdv_proxy": 9_500.0,
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                    }

            return SuccessResult()

    emitted: list[dict] = []
    sleep_calls: list[float] = []
    probe = FakeProbe()
    create_event = {
        "event_id": "txsub_sig-retry_123_0",
        "signature": "sig-retry",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "mint-retry",
        "bonding_curve": "curve-retry",
    }

    row = run_bonding_curve_account_probe_for_create_event(
        config,
        create_event,
        probe=probe,
        event_callback=emitted.append,
        now_fn=iter([100.0, 100.01, 100.11, 100.22]).__next__,
        sleep_fn=sleep_calls.append,
        account_not_found_retry_delays=(0.1, 0.25),
    )

    assert probe.calls == 2
    assert sleep_calls == [0.1]
    assert seen_payloads[0]["min_context_slot"] == 123
    assert seen_payloads[1]["min_context_slot"] == 123
    assert row["probe_status"] == "success"
    assert row["probe_attempt_count"] == 2
    assert row["account_not_found_retry_count"] == 1
    assert row["account_not_found_recovered_by_retry"] is True
    assert row["first_failure_reason"] == "account_not_found"
    assert row["retry_delays_ms"] == [100.0]
    assert row["observed_to_probe_started_ms"] == 0.0
    assert row["probe_started_to_first_curve_state_ms"] == 220.0
    assert row["observed_to_first_fdv_emitted_ms"] == 220.0
    assert emitted[0]["account_not_found_recovered_by_retry"] is True
    assert json.loads(config.bonding_curve_account_probe_events_path.read_text(encoding="utf-8").splitlines()[0])["account_not_found_recovered_by_retry"] is True


def test_live_watch_account_subscribe_emits_fdv_path_update(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)

    class FakeProbe:
        def __init__(self) -> None:
            self.calls = 0

        def decode_account_update(self, **kwargs: object) -> object:
            self.calls += 1
            mint = str(kwargs["mint"])
            bonding_curve = str(kwargs["bonding_curve"])

            class Result:
                probe_status = "success"
                failure_reason = None
                fdv_proxy = 21_500.0
                fdv_usd = 21_500.0
                fdv_sol = 215.0
                fdv_quote = None
                fdv_units = "usd"
                price_sol = 0.000215
                price_quote = None
                sol_usd = 100.0
                quote_decimals = 9
                token_decimals = 6
                calculation_status = "fdv_usd_available"
                quote_type = "sol"
                account_state = {"virtual_token_reserves": 1, "virtual_sol_reserves": 1}
                decode_finished_at = 200.01
                account_data_slot = 456
                account_data_hash = "hash-live"
                helius_rpc_request_count = 0
                http_429_count = 0

                def to_runtime_event(self, timestamp: float | None = None) -> dict:
                    return {
                        "event_id": "fdv-live",
                        "mint": mint,
                        "timestamp": timestamp or 200.01,
                        "event_observed_at": 200.0,
                        "fdv_proxy": self.fdv_proxy,
                        "fdv_usd": self.fdv_usd,
                        "fdv_sol": self.fdv_sol,
                        "fdv_units": self.fdv_units,
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_account_subscribe_bonding_curve_live_watch",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                    }

            return Result()

    websocket = FakeWebSocket(
        [
            {"id": "live-watch-curve-live", "result": 77},
            {
                "method": "accountNotification",
                "params": {
                    "subscription": 77,
                    "result": {
                        "context": {"slot": 456},
                        "value": {"data": ["AQID", "base64"]},
                    },
                },
            },
        ]
    )

    def ws_connect(_url: str, **_kwargs: object) -> FakeWebSocket:
        return websocket

    emitted: list[dict] = []
    source = HeliusBondingCurveLiveWatchSource(
        config=config,
        websocket_url="wss://fake",
        ws_connect=ws_connect,
        now_fn=iter([200.0, 200.01]).__next__,
    )
    rows = source.watch_create_event(
        {
            "event_id": "txsub-live",
            "signature": "sig-live",
            "slot": 123,
            "observed_at": 199.5,
            "mint": "mint-live",
            "bonding_curve": "curve-live",
        },
        probe=FakeProbe(),
        event_callback=emitted.append,
        max_updates=1,
        max_seconds=1,
    )

    assert websocket.sent[0]["method"] == "accountSubscribe"
    assert rows[0]["probe_phase"] == "near_entry_live_watch"
    assert rows[0]["winning_probe_source"] == "accountSubscribe_processed"
    assert rows[0]["fdv_usd"] == 21_500.0
    assert emitted[0]["source_adapter"] == "helius_account_subscribe_bonding_curve_live_watch"
    assert emitted[0]["fdv_usd"] == 21_500.0
