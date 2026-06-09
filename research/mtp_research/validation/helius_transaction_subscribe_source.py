"""Helius Developer transactionSubscribe source for Pump.fun create events."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import base64
import json
import os
import threading
import time
import urllib.error

from research.mtp_research.validation.forward_birth_watch_followup_collector import rpc_url_to_websocket_url
from research.mtp_research.validation.forward_efficient_mover_observer import (
    _post_json_rpc,
    resolve_helius_api_key,
    resolve_helius_rpc_url,
    resolve_helius_ws_url,
)
from research.mtp_research.validation.pumpfun_bonding_curve import (
    PUMP_FUN_PROGRAM_ID,
    bonding_curve_pda,
    is_pumpfun_create_discriminator,
    mint_authority_pda,
)


TRANSACTION_SUBSCRIBE_REQUEST_ID = "mtp-pumpfun-transaction-subscribe"
CAPABILITY_TRANSACTION_ID = "mtp-transaction-subscribe-capability"
CAPABILITY_ACCOUNT_ID = "mtp-account-subscribe-capability"
CAPABILITY_GET_ACCOUNT_ID = "mtp-get-account-info-capability"
ACCOUNT_SUBSCRIBE_REQUEST_PREFIX = "live-watch"
ACCOUNT_NOT_FOUND_RETRY_DELAYS_SECONDS = (0.1, 0.25, 0.5, 1.0, 2.0)
_JSONL_WRITE_LOCK = threading.Lock()


def build_transaction_subscribe_request(*, request_id: str = TRANSACTION_SUBSCRIBE_REQUEST_ID) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "transactionSubscribe",
        "params": [
            {
                "failed": False,
                "accountRequired": [PUMP_FUN_PROGRAM_ID, mint_authority_pda()],
            },
            {
                "commitment": "processed",
                "transactionDetails": "full",
                "showRewards": False,
                "maxSupportedTransactionVersion": 0,
                "encoding": "jsonParsed",
            },
        ],
    }


def build_account_subscribe_request(pubkey: str, *, request_id: str | None = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id or f"{ACCOUNT_SUBSCRIBE_REQUEST_PREFIX}-{pubkey}",
        "method": "accountSubscribe",
        "params": [
            pubkey,
            {
                "commitment": "processed",
                "encoding": "base64",
            },
        ],
    }


class HeliusTransactionSubscribeCreateSource:
    source_adapter = "helius_transaction_subscribe_pumpfun_create"

    def __init__(
        self,
        *,
        config: Any,
        websocket_url: str | None = None,
        ws_connect: Any | None = None,
        now_fn: Callable[[], float] = time.time,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.config = config
        self.websocket_url = websocket_url or resolve_helius_ws_url()
        self._ws_connect = ws_connect or _websocket_connect
        self.now_fn = now_fn
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.requests_used = 0
        self.reconnect_count = 0

    def availability(self) -> dict[str, Any]:
        if not self.websocket_url:
            return {
                "source": self.source_adapter,
                "available": False,
                "missing_reason": "missing_helius_websocket_url",
                "transactionSubscribe": False,
            }
        return {
            "source": self.source_adapter,
            "available": True,
            "transactionSubscribe": True,
            "websocket_url": _mask_endpoint(self.websocket_url),
        }

    def fetch_create_events(
        self,
        *,
        max_events: int = 25,
        max_seconds: float = 30.0,
        on_create_event: Callable[[dict[str, Any]], None] | None = None,
        on_idle: Callable[[], None] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        deadline = time.monotonic() + max(0.1, float(max_seconds))
        while len(rows) < max(0, int(max_events)) and time.monotonic() < deadline:
            try:
                with self._ws_connect(
                    self.websocket_url,
                    open_timeout=min(5.0, self.timeout_seconds),
                    close_timeout=1.0,
                ) as websocket:
                    request = build_transaction_subscribe_request()
                    websocket.send(json.dumps(request))
                    self.requests_used += 1
                    while len(rows) < max(0, int(max_events)) and time.monotonic() < deadline:
                        try:
                            message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
                        except TimeoutError:
                            if on_idle is not None:
                                on_idle()
                            continue
                        except BaseException as exc:
                            if not _is_reconnectable_websocket_close(exc):
                                raise
                            self._record_websocket_reconnect(exc)
                            if on_idle is not None:
                                on_idle()
                            break
                        raw = json.loads(message) if isinstance(message, str) else message
                        if not isinstance(raw, dict):
                            continue
                        _append_jsonl(self.config.pumpfun_transaction_subscribe_raw_path, {**raw, "source": "transactionSubscribe"})
                        if raw.get("id") == TRANSACTION_SUBSCRIBE_REQUEST_ID:
                            continue
                        decoded = decode_pumpfun_transaction_subscribe_notification(raw, observed_at=self.now_fn())
                        if not decoded:
                            continue
                        for row in decoded:
                            _append_jsonl(self.config.pumpfun_create_stream_events_path, row)
                            rows.append(row)
                            if on_create_event is not None:
                                on_create_event(row)
                            if on_idle is not None:
                                on_idle()
                            if len(rows) >= max(0, int(max_events)):
                                break
            except BaseException as exc:
                if not _is_reconnectable_websocket_close(exc):
                    raise
                self._record_websocket_reconnect(exc)
                if on_idle is not None:
                    on_idle()
        return rows

    def _record_websocket_reconnect(self, exc: BaseException) -> None:
        self.reconnect_count += 1
        _append_jsonl(
            self.config.pumpfun_transaction_subscribe_raw_path,
            {
                "source": "transactionSubscribe",
                "event": "websocket_reconnect",
                "reason": type(exc).__name__,
                "message": str(exc),
                "reconnect_count": self.reconnect_count,
                "observed_at": self.now_fn(),
            },
        )


class HeliusBondingCurveLiveWatchSource:
    source_adapter = "helius_account_subscribe_bonding_curve_live_watch"

    def __init__(
        self,
        *,
        config: Any,
        websocket_url: str | None = None,
        ws_connect: Any | None = None,
        now_fn: Callable[[], float] = time.time,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.config = config
        self.websocket_url = websocket_url or resolve_helius_ws_url()
        self._ws_connect = ws_connect or _websocket_connect
        self.now_fn = now_fn
        self.timeout_seconds = max(0.1, float(timeout_seconds))

    def watch_create_event(
        self,
        create_event: dict[str, Any],
        *,
        probe: Any,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        max_updates: int = 25,
        max_seconds: float = 15.0,
    ) -> list[dict[str, Any]]:
        mint = str(create_event.get("mint") or "").strip()
        bonding_curve = str(create_event.get("bonding_curve") or "").strip()
        if not mint or not bonding_curve or not self.websocket_url:
            return []
        request_id = f"{ACCOUNT_SUBSCRIBE_REQUEST_PREFIX}-{bonding_curve}"
        rows: list[dict[str, Any]] = []
        subscription_id: int | None = None
        deadline = time.monotonic() + max(0.1, float(max_seconds))
        with self._ws_connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
            websocket.send(json.dumps(build_account_subscribe_request(bonding_curve, request_id=request_id)))
            while len(rows) < max(0, int(max_updates)) and time.monotonic() < deadline:
                try:
                    message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
                except TimeoutError:
                    continue
                payload = json.loads(message) if isinstance(message, str) else message
                if not isinstance(payload, dict):
                    continue
                if payload.get("id") == request_id:
                    subscription_id = _optional_int(payload.get("result"))
                    continue
                if not _account_notification_matches(payload, subscription_id):
                    continue
                observed_at = self.now_fn()
                slot = _slot(_find_result(payload) or {})
                account_data = _account_data_from_account_notification(payload)
                result = probe.decode_account_update(
                    mint=mint,
                    bonding_curve=bonding_curve,
                    account_data=account_data,
                    observed_at=observed_at,
                    slot=slot,
                    now_fn=self.now_fn,
                    fdv_probe_method="accountSubscribe_processed_bonding_curve",
                )
                row = _live_watch_probe_row(create_event, result, observed_at=observed_at, slot=slot)
                _append_jsonl(self.config.bonding_curve_account_probe_events_path, row)
                rows.append(row)
                runtime_event = result.to_runtime_event(timestamp=getattr(result, "decode_finished_at", None) or observed_at) if getattr(result, "probe_status", None) == "success" else None
                if runtime_event is not None:
                    runtime_event["event_id"] = f"fdv_live_{create_event.get('event_id') or create_event.get('signature')}_{int(observed_at * 1000)}"
                    runtime_event["source_event_type"] = "fdv_path_update"
                    runtime_event["source_adapter"] = self.source_adapter
                    runtime_event["source_provenance"] = self.source_adapter
                    runtime_event["data_source"] = "bonding_curve_account_state"
                    runtime_event["milestone_provenance"] = "bonding_curve_account_state"
                    runtime_event["probe_phase"] = "near_entry_live_watch"
                    runtime_event["probe_scheduled_during_stream"] = True
                    runtime_event["near_entry_live_watch"] = True
                    runtime_event["live_watch_started_at"] = observed_at
                    runtime_event["live_watch_arm_usd"] = create_event.get("live_watch_arm_usd")
                    runtime_event["pumpfun_create_verified"] = str(create_event.get("parser_status") or "") == "decoded"
                    runtime_event["bonding_curve_pda_verified"] = bool(create_event.get("bonding_curve_verified"))
                    runtime_event["bonding_curve_decode_status"] = "success"
                    _copy_fdv_probe_fields(result, runtime_event)
                    if event_callback is not None:
                        event_callback(runtime_event)
        return rows


def decode_pumpfun_transaction_subscribe_notification(payload: dict[str, Any], *, observed_at: float | None = None) -> list[dict[str, Any]]:
    result = _find_result(payload)
    if not isinstance(result, dict):
        return []
    slot = _slot(result)
    signature = _signature(result)
    tx = _transaction_payload(result)
    message = ((tx.get("transaction") or {}).get("message") or tx.get("message") or {}) if isinstance(tx, dict) else {}
    observed = float(observed_at if observed_at is not None else time.time())
    rows: list[dict[str, Any]] = []
    for index, instruction in enumerate(message.get("instructions") or []):
        if not isinstance(instruction, dict):
            continue
        program_id = instruction.get("programId") or instruction.get("program_id")
        if program_id != PUMP_FUN_PROGRAM_ID:
            continue
        data = _instruction_data_bytes(instruction.get("data"))
        instruction_type = is_pumpfun_create_discriminator(data)
        if instruction_type is None:
            continue
        accounts = instruction.get("accounts") or []
        if not isinstance(accounts, list):
            accounts = []
        mint = _account_string(accounts, 0)
        curve_from_ix = _account_string(accounts, 2)
        creator = _account_string(accounts, 5)
        curve_pda = bonding_curve_pda(mint)
        bonding_curve = curve_from_ix if curve_from_ix and curve_from_ix == curve_pda else curve_pda
        parser_error = None
        parser_status = "decoded"
        if not mint:
            parser_status = "decode_failed"
            parser_error = "missing_mint_account"
        elif not bonding_curve:
            parser_status = "decode_failed"
            parser_error = "missing_bonding_curve"
        rows.append(
            {
                "event_id": f"txsub_{signature}_{slot}_{index}",
                "signature": signature,
                "slot": slot,
                "observed_at": observed,
                "mint": mint,
                "bonding_curve": bonding_curve,
                "bonding_curve_from_ix": curve_from_ix,
                "bonding_curve_pda": curve_pda,
                "bonding_curve_verified": bool(curve_from_ix and curve_pda and curve_from_ix == curve_pda),
                "creator": creator,
                "instruction_type": instruction_type,
                "parser_status": parser_status,
                "parser_error": parser_error,
                "source": "transactionSubscribe",
                "getTransaction_used": False,
            }
        )
    return rows


def helius_transaction_subscribe_capability_audit(
    config: Any,
    *,
    endpoints: list[dict[str, str | None]] | None = None,
    ws_connect: Any | None = None,
    rpc_post: Any | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    endpoints = endpoints or _default_capability_endpoints()
    ws_connect = ws_connect or _websocket_connect
    rpc_post = rpc_post or _post_json_rpc
    results: list[dict[str, Any]] = []
    for endpoint in endpoints:
        result = _audit_endpoint(endpoint, ws_connect=ws_connect, rpc_post=rpc_post, timeout_seconds=timeout_seconds)
        results.append(result)
    recommended = next(
        (
            row
            for row in results
            if row.get("transactionSubscribe_supported")
            and row.get("getAccountInfo_processed_supported")
        ),
        results[0] if results else {},
    )
    audit = {
        "report_id": "helius_transaction_subscribe_capability_audit",
        "updated_at": _utc_now(),
        "endpoints": results,
        "recommended_endpoint": recommended,
        "paper_only": True,
        "no_new_paid_source": True,
    }
    _write_json(config.helius_transaction_subscribe_capability_audit_json_path, audit)
    config.helius_transaction_subscribe_capability_audit_md_path.write_text(_capability_audit_md(audit), encoding="utf-8")
    return audit


def run_bonding_curve_account_probe_for_create_event(
    config: Any,
    create_event: dict[str, Any],
    *,
    probe: Any,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    now_fn: Callable[[], float] = time.time,
    sleep_fn: Callable[[float], None] = time.sleep,
    account_not_found_retry_delays: tuple[float, ...] = ACCOUNT_NOT_FOUND_RETRY_DELAYS_SECONDS,
    follow_up_probe_delays: tuple[float, ...] = (),
    include_mint_account_owner: bool = True,
) -> dict[str, Any]:
    started = now_fn()
    create_observed_at = _num(create_event.get("observed_at") or create_event.get("create_log_observed_at") or create_event.get("timestamp"))
    if include_mint_account_owner:
        mint_owner = _resolve_mint_account_owner(probe, str(create_event.get("mint") or ""), min_context_slot=_optional_int(create_event.get("slot")))
    else:
        mint_owner = {
            "mint_account_owner": None,
            "token_program": None,
            "mint_account_owner_status": "deferred_first_fdv_hot_path",
        }
    attempt_started_at = started
    probe_input = {
        **create_event,
        "observed_time": create_event.get("observed_at"),
        "create_log_observed_at": create_event.get("observed_at"),
        "min_context_slot": create_event.get("slot"),
    }
    attempts: list[dict[str, Any]] = []
    retry_delays_ms: list[float] = []
    result: Any | None = None
    first_response = attempt_started_at
    for retry_index in range(len(tuple(account_not_found_retry_delays)) + 1):
        result = probe.probe_create_event(probe_input, now_fn=now_fn)
        first_response = now_fn()
        status = str(getattr(result, "probe_status", "failed") or "failed")
        failure_reason = getattr(result, "failure_reason", None)
        attempts.append(
            {
                "attempt_index": retry_index,
                "started_at": attempt_started_at,
                "finished_at": first_response,
                "probe_status": status,
                "failure_reason": failure_reason,
            }
        )
        if status == "success" or failure_reason != "account_not_found":
            break
        if retry_index >= len(tuple(account_not_found_retry_delays)):
            break
        delay = float(tuple(account_not_found_retry_delays)[retry_index])
        retry_delays_ms.append(_round_ms(delay * 1000.0))
        sleep_fn(delay)
        attempt_started_at = now_fn()
    status = str(getattr(result, "probe_status", "failed") or "failed")
    first_failure_reason = attempts[0].get("failure_reason") if attempts else None
    account_not_found_retry_count = len(retry_delays_ms)
    recovered_by_retry = bool(status == "success" and first_failure_reason == "account_not_found" and account_not_found_retry_count > 0)
    runtime_event = result.to_runtime_event(timestamp=first_response) if status == "success" else None
    first_curve_state_at = (
        _num(getattr(result, "decode_finished_at", None)) or _num(getattr(result, "get_account_info_finished_at", None)) or first_response
        if status == "success"
        else None
    )
    first_fdv_emitted_at = first_curve_state_at if runtime_event is not None else None
    if runtime_event is not None:
        runtime_event["event_id"] = f"fdv_{create_event.get('event_id') or create_event.get('signature')}_{int(first_response * 1000)}"
        runtime_event["source_event_type"] = "fdv_path_update"
        runtime_event["source_adapter"] = "helius_transaction_subscribe_bonding_curve_probe"
        runtime_event["source_provenance"] = "helius_transaction_subscribe_bonding_curve_probe"
        runtime_event["path_evidence_count"] = int(runtime_event.get("path_evidence_count") or 1)
        runtime_event["create_observed_at"] = create_observed_at
        runtime_event["probe_started_at"] = started
        runtime_event["first_curve_state_at"] = first_curve_state_at
        runtime_event["first_fdv_emitted_at"] = first_fdv_emitted_at
        runtime_event["observed_to_probe_started_ms"] = _duration_ms(create_observed_at, started)
        runtime_event["probe_started_to_first_curve_state_ms"] = _duration_ms(started, first_curve_state_at)
        runtime_event["observed_to_first_fdv_emitted_ms"] = _duration_ms(create_observed_at, first_fdv_emitted_at)
        runtime_event["probe_attempt_count"] = len(attempts)
        runtime_event["account_not_found_retry_count"] = account_not_found_retry_count
        runtime_event["account_not_found_recovered_by_retry"] = recovered_by_retry
        runtime_event["first_failure_reason"] = first_failure_reason
        runtime_event["retry_delays_ms"] = retry_delays_ms
        runtime_event["pumpfun_create_verified"] = str(create_event.get("parser_status") or "") == "decoded"
        runtime_event["bonding_curve_pda_verified"] = bool(create_event.get("bonding_curve_verified"))
        runtime_event["bonding_curve_decode_status"] = "success"
        runtime_event.update(mint_owner)
        _copy_fdv_probe_fields(result, runtime_event)
    winning = "getAccountInfo_processed" if status == "success" else "none"
    confirmation_follow_up = bool(create_event.get("confirmation_follow_up_scheduled"))
    phase_override = str(create_event.get("probe_phase_override") or "").strip()
    row = {
        "event_id": f"probe_{create_event.get('event_id') or create_event.get('signature')}_{int(started * 1000)}",
        "probe_phase": phase_override or ("confirmation_initial" if confirmation_follow_up else "initial"),
        "confirmation_follow_up_scheduled": confirmation_follow_up,
        "post_birth_watch_follow_up_scheduled": bool(create_event.get("post_birth_watch_follow_up_scheduled")),
        "post_birth_watch_follow_up_index": create_event.get("post_birth_watch_follow_up_index"),
        "post_birth_watch_due_delay_seconds": create_event.get("post_birth_watch_due_delay_seconds"),
        "post_birth_watch_lane": create_event.get("post_birth_watch_lane"),
        "hot_watch_follow_up_scheduled": bool(create_event.get("hot_watch_follow_up_scheduled")),
        "hot_watch_follow_up_index": create_event.get("hot_watch_follow_up_index"),
        "hot_watch_due_delay_seconds": create_event.get("hot_watch_due_delay_seconds"),
        "hot_watch_mode": create_event.get("hot_watch_mode"),
        "account_not_found_retry_follow_up_scheduled": bool(create_event.get("account_not_found_retry_follow_up_scheduled")),
        "account_not_found_retry_follow_up_index": create_event.get("account_not_found_retry_follow_up_index"),
        "account_not_found_retry_due_delay_seconds": create_event.get("account_not_found_retry_due_delay_seconds"),
        "mint": create_event.get("mint"),
        "bonding_curve": create_event.get("bonding_curve"),
        "source_create_signature": create_event.get("signature"),
        "create_slot": create_event.get("slot"),
        "create_observed_at": create_observed_at,
        "probe_scheduled_during_stream": bool(create_event.get("probe_scheduled_during_stream")),
        "pumpfun_create_verified": str(create_event.get("parser_status") or "") == "decoded",
        "bonding_curve_pda_verified": bool(create_event.get("bonding_curve_verified")),
        "bonding_curve_decode_status": "success" if status == "success" else "failed",
        "probe_started_at": started,
        "account_subscribe_started_at": None,
        "get_account_info_started_at": started,
        "first_curve_state_at": first_curve_state_at,
        "first_fdv_emitted_at": first_fdv_emitted_at,
        "first_response_at": first_response,
        "winning_probe_source": winning,
        "probe_attempt_count": len(attempts),
        "account_not_found_retry_count": account_not_found_retry_count,
        "account_not_found_recovered_by_retry": recovered_by_retry,
        "account_not_found_final_failure": bool(status != "success" and getattr(result, "failure_reason", None) == "account_not_found"),
        "first_failure_reason": first_failure_reason,
        "final_failure_reason": None if status == "success" else getattr(result, "failure_reason", None),
        "retry_delays_ms": retry_delays_ms,
        "attempts": attempts,
        "observed_to_probe_started_ms": _duration_ms(create_observed_at, started),
        "probe_started_to_first_curve_state_ms": _duration_ms(started, first_curve_state_at),
        "observed_to_first_fdv_emitted_ms": _duration_ms(create_observed_at, first_fdv_emitted_at),
        "getAccountInfo_latency_ms": getattr(result, "getAccountInfo_latency_ms", None),
        "accountSubscribe_latency_ms": getattr(result, "accountSubscribe_latency_ms", None),
        "account_data_slot": getattr(result, "account_data_slot", None),
        "account_data_encoding": "base64",
        "probe_status": status,
        "probe_error": None if status == "success" else getattr(result, "failure_reason", None),
        "helius_rpc_request_count": int(getattr(result, "helius_rpc_request_count", None) or getattr(probe, "requests_used", 0) or 0),
        "http_429_count": int(getattr(result, "http_429_count", None) or getattr(probe, "http_429_count", 0) or 0),
        **mint_owner,
    }
    _copy_fdv_probe_fields(result, row)
    if runtime_event is not None:
        _copy_fdv_probe_fields(runtime_event, row)
    _append_jsonl(config.bonding_curve_account_probe_events_path, row)
    if runtime_event is not None and event_callback is not None:
        event_callback(runtime_event)
    if status == "success" and runtime_event is not None and follow_up_probe_delays:
        for follow_up_index, delay in enumerate(tuple(follow_up_probe_delays), start=1):
            sleep_fn(float(delay))
            follow_started = now_fn()
            follow_result = probe.probe_create_event(probe_input, now_fn=now_fn)
            follow_response = now_fn()
            follow_status = str(getattr(follow_result, "probe_status", "failed") or "failed")
            follow_event = follow_result.to_runtime_event(timestamp=follow_response) if follow_status == "success" else None
            follow_curve_state_at = (
                _num(getattr(follow_result, "decode_finished_at", None))
                or _num(getattr(follow_result, "get_account_info_finished_at", None))
                or follow_response
                if follow_status == "success"
                else None
            )
            follow_fdv_emitted_at = follow_curve_state_at if follow_event is not None else None
            if follow_event is not None:
                follow_event["event_id"] = f"fdv_follow_{create_event.get('event_id') or create_event.get('signature')}_{follow_up_index}_{int(follow_response * 1000)}"
                follow_event["source_event_type"] = "fdv_path_update"
                follow_event["source_adapter"] = "helius_transaction_subscribe_bonding_curve_probe"
                follow_event["source_provenance"] = "helius_transaction_subscribe_bonding_curve_probe"
                follow_event["path_evidence_count"] = int(follow_event.get("path_evidence_count") or (follow_up_index + 1))
                follow_event["create_observed_at"] = create_observed_at
                follow_event["probe_started_at"] = follow_started
                follow_event["first_curve_state_at"] = follow_curve_state_at
                follow_event["first_fdv_emitted_at"] = follow_fdv_emitted_at
                follow_event["observed_to_probe_started_ms"] = _duration_ms(create_observed_at, follow_started)
                follow_event["probe_started_to_first_curve_state_ms"] = _duration_ms(follow_started, follow_curve_state_at)
                follow_event["observed_to_first_fdv_emitted_ms"] = _duration_ms(create_observed_at, follow_fdv_emitted_at)
                follow_event["probe_attempt_count"] = 1
                follow_event["account_not_found_retry_count"] = 0
                follow_event["account_not_found_recovered_by_retry"] = False
                follow_event["first_failure_reason"] = None
                follow_event["retry_delays_ms"] = []
                follow_event["pumpfun_create_verified"] = str(create_event.get("parser_status") or "") == "decoded"
                follow_event["bonding_curve_pda_verified"] = bool(create_event.get("bonding_curve_verified"))
                follow_event["bonding_curve_decode_status"] = "success"
                follow_event.update(mint_owner)
                _copy_fdv_probe_fields(follow_result, follow_event)
            follow_row = {
                "event_id": f"probe_follow_{create_event.get('event_id') or create_event.get('signature')}_{follow_up_index}_{int(follow_started * 1000)}",
                "probe_phase": "confirmation_follow_up" if confirmation_follow_up else "follow_up",
                "confirmation_follow_up_scheduled": confirmation_follow_up,
                "follow_up_index": follow_up_index,
                "follow_up_delay_seconds": float(delay),
                "mint": create_event.get("mint"),
                "bonding_curve": create_event.get("bonding_curve"),
                "source_create_signature": create_event.get("signature"),
                "create_slot": create_event.get("slot"),
                "create_observed_at": create_observed_at,
                "probe_scheduled_during_stream": bool(create_event.get("probe_scheduled_during_stream")),
                "pumpfun_create_verified": str(create_event.get("parser_status") or "") == "decoded",
                "bonding_curve_pda_verified": bool(create_event.get("bonding_curve_verified")),
                "bonding_curve_decode_status": "success" if follow_status == "success" else "failed",
                "probe_started_at": follow_started,
                "account_subscribe_started_at": None,
                "get_account_info_started_at": follow_started,
                "first_curve_state_at": follow_curve_state_at,
                "first_fdv_emitted_at": follow_fdv_emitted_at,
                "first_response_at": follow_response,
                "winning_probe_source": "getAccountInfo_processed" if follow_status == "success" else "none",
                "probe_attempt_count": 1,
                "account_not_found_retry_count": 0,
                "account_not_found_recovered_by_retry": False,
                "account_not_found_final_failure": bool(follow_status != "success" and getattr(follow_result, "failure_reason", None) == "account_not_found"),
                "first_failure_reason": getattr(follow_result, "failure_reason", None) if follow_status != "success" else None,
                "final_failure_reason": None if follow_status == "success" else getattr(follow_result, "failure_reason", None),
                "retry_delays_ms": [],
                "attempts": [
                    {
                        "attempt_index": 0,
                        "started_at": follow_started,
                        "finished_at": follow_response,
                        "probe_status": follow_status,
                        "failure_reason": getattr(follow_result, "failure_reason", None),
                    }
                ],
                "observed_to_probe_started_ms": _duration_ms(create_observed_at, follow_started),
                "probe_started_to_first_curve_state_ms": _duration_ms(follow_started, follow_curve_state_at),
                "observed_to_first_fdv_emitted_ms": _duration_ms(create_observed_at, follow_fdv_emitted_at),
                "getAccountInfo_latency_ms": getattr(follow_result, "getAccountInfo_latency_ms", None),
                "accountSubscribe_latency_ms": getattr(follow_result, "accountSubscribe_latency_ms", None),
                "account_data_slot": getattr(follow_result, "account_data_slot", None),
                "account_data_encoding": "base64",
                "probe_status": follow_status,
                "probe_error": None if follow_status == "success" else getattr(follow_result, "failure_reason", None),
                "helius_rpc_request_count": int(getattr(follow_result, "helius_rpc_request_count", None) or getattr(probe, "requests_used", 0) or 0),
                "http_429_count": int(getattr(follow_result, "http_429_count", None) or getattr(probe, "http_429_count", 0) or 0),
                **mint_owner,
            }
            _copy_fdv_probe_fields(follow_result, follow_row)
            if follow_event is not None:
                _copy_fdv_probe_fields(follow_event, follow_row)
            _append_jsonl(config.bonding_curve_account_probe_events_path, follow_row)
            if follow_event is not None and event_callback is not None:
                event_callback(follow_event)
    return row


def _copy_fdv_probe_fields(source: Any, target: dict[str, Any]) -> None:
    for key in [
        "fdv_proxy",
        "fdv_usd",
        "fdv_sol",
        "fdv_quote",
        "fdv_units",
        "price_sol",
        "price_quote",
        "sol_usd",
        "quote_decimals",
        "token_decimals",
        "calculation_status",
        "calculation_error",
        "quote_type",
        "account_state",
        "token_program",
        "mint_account_owner",
        "mint_account_owner_status",
        "account_data_slot",
        "account_data_hash",
    ]:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)
        if value is not None:
            target[key] = value


def _resolve_mint_account_owner(probe: Any, mint: str, *, min_context_slot: int | None = None) -> dict[str, Any]:
    if not mint:
        return {"mint_account_owner": None, "token_program": None, "mint_account_owner_status": "missing_mint"}
    rpc_post = getattr(probe, "_rpc_post", None)
    rpc_url = getattr(probe, "rpc_url", "") or ""
    if rpc_post is None:
        return {"mint_account_owner": None, "token_program": None, "mint_account_owner_status": "unavailable"}
    options: dict[str, Any] = {"encoding": "base64", "commitment": "processed"}
    if min_context_slot is not None:
        options["minContextSlot"] = int(min_context_slot)
    payload = {
        "jsonrpc": "2.0",
        "id": "mtp-mint-owner-get-account-info",
        "method": "getAccountInfo",
        "params": [mint, options],
    }
    try:
        if hasattr(probe, "requests_used"):
            probe.requests_used += 1
        response = rpc_post(rpc_url, payload, getattr(probe, "timeout_seconds", 3))
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and hasattr(probe, "http_429_count"):
            probe.http_429_count += 1
        return {"mint_account_owner": None, "token_program": None, "mint_account_owner_status": f"rpc_error_{getattr(exc, 'code', 'unknown')}"}
    except Exception:
        return {"mint_account_owner": None, "token_program": None, "mint_account_owner_status": "rpc_error"}
    value = ((response or {}).get("result") or {}).get("value") if isinstance(response, dict) else None
    if not isinstance(value, dict):
        return {"mint_account_owner": None, "token_program": None, "mint_account_owner_status": "account_not_found"}
    owner = value.get("owner")
    return {"mint_account_owner": owner, "token_program": owner, "mint_account_owner_status": "found" if owner else "owner_missing"}


def _audit_endpoint(endpoint: dict[str, str | None], *, ws_connect: Any, rpc_post: Any, timeout_seconds: int) -> dict[str, Any]:
    websocket_url = endpoint.get("websocket_url")
    rpc_url = endpoint.get("rpc_url")
    row: dict[str, Any] = {
        "name": endpoint.get("name"),
        "websocket_url": _mask_endpoint(websocket_url),
        "rpc_url": _mask_endpoint(rpc_url),
        "transactionSubscribe_supported": False,
        "accountSubscribe_supported": False,
        "getAccountInfo_processed_supported": False,
        "errors": [],
    }
    if websocket_url:
        try:
            with ws_connect(websocket_url, open_timeout=min(5.0, timeout_seconds), close_timeout=1.0) as websocket:
                websocket.send(json.dumps(build_transaction_subscribe_request(request_id=CAPABILITY_TRANSACTION_ID)))
                tx_response = _recv_matching(websocket, CAPABILITY_TRANSACTION_ID, timeout_seconds=timeout_seconds)
                row["transactionSubscribe_supported"] = "result" in tx_response and "error" not in tx_response
                if tx_response.get("error"):
                    row["errors"].append(f"transactionSubscribe:{tx_response.get('error')}")
                websocket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": CAPABILITY_ACCOUNT_ID,
                            "method": "accountSubscribe",
                            "params": [
                                mint_authority_pda(),
                                {"commitment": "processed", "encoding": "base64"},
                            ],
                        }
                    )
                )
                account_response = _recv_matching(websocket, CAPABILITY_ACCOUNT_ID, timeout_seconds=timeout_seconds)
                row["accountSubscribe_supported"] = "result" in account_response and "error" not in account_response
                if account_response.get("error"):
                    row["errors"].append(f"accountSubscribe:{account_response.get('error')}")
        except Exception as exc:
            row["errors"].append(f"websocket:{type(exc).__name__}:{exc}")
    if rpc_url:
        try:
            response = rpc_post(
                rpc_url,
                {
                    "jsonrpc": "2.0",
                    "id": CAPABILITY_GET_ACCOUNT_ID,
                    "method": "getAccountInfo",
                    "params": [
                        mint_authority_pda(),
                        {"commitment": "processed", "encoding": "base64"},
                    ],
                },
                timeout_seconds,
            )
            row["getAccountInfo_processed_supported"] = isinstance(response, dict) and "error" not in response
            if isinstance(response, dict) and response.get("error"):
                row["errors"].append(f"getAccountInfo:{response.get('error')}")
        except Exception as exc:
            row["errors"].append(f"getAccountInfo:{type(exc).__name__}:{exc}")
    return row


def _default_capability_endpoints() -> list[dict[str, str | None]]:
    api_key = resolve_helius_api_key(load_project_dotenv=True)
    endpoints: list[dict[str, str | None]] = []
    if api_key:
        endpoints.append(
            {
                "name": "helius_beta",
                "websocket_url": f"wss://beta.helius-rpc.com/?api-key={api_key}",
                "rpc_url": f"https://beta.helius-rpc.com/?api-key={api_key}",
            }
        )
    rpc_url = resolve_helius_rpc_url(load_project_dotenv=True)
    endpoints.append(
        {
            "name": "configured",
            "websocket_url": resolve_helius_ws_url(load_project_dotenv=False) or rpc_url_to_websocket_url(rpc_url),
            "rpc_url": rpc_url,
        }
    )
    return endpoints


def _recv_matching(websocket: Any, request_id: str, *, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    while time.monotonic() < deadline:
        message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
        payload = json.loads(message) if isinstance(message, str) else message
        if isinstance(payload, dict) and payload.get("id") == request_id:
            return payload
    return {"error": "capability_timeout"}


def _account_notification_matches(payload: dict[str, Any], subscription_id: int | None) -> bool:
    params = payload.get("params")
    if not isinstance(params, dict):
        return False
    if subscription_id is None:
        return payload.get("method") == "accountNotification"
    return payload.get("method") == "accountNotification" and _optional_int(params.get("subscription")) == subscription_id


def _account_data_from_account_notification(payload: dict[str, Any]) -> bytes | None:
    result = _find_result(payload)
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    if isinstance(data, list) and data:
        encoded = data[0]
    else:
        encoded = data
    if isinstance(encoded, str):
        try:
            return base64.b64decode(encoded)
        except Exception:
            return None
    if isinstance(encoded, bytes):
        return encoded
    return None


def _live_watch_probe_row(create_event: dict[str, Any], result: Any, *, observed_at: float, slot: int | None) -> dict[str, Any]:
    status = str(getattr(result, "probe_status", "failed") or "failed")
    row = {
        "event_id": f"probe_live_{create_event.get('event_id') or create_event.get('signature')}_{int(observed_at * 1000)}",
        "probe_phase": "near_entry_live_watch",
        "near_entry_live_watch": True,
        "mint": create_event.get("mint"),
        "bonding_curve": create_event.get("bonding_curve"),
        "source_create_signature": create_event.get("signature"),
        "create_slot": create_event.get("slot"),
        "create_observed_at": create_event.get("observed_at"),
        "probe_scheduled_during_stream": True,
        "pumpfun_create_verified": str(create_event.get("parser_status") or "") == "decoded",
        "bonding_curve_pda_verified": bool(create_event.get("bonding_curve_verified")),
        "bonding_curve_decode_status": "success" if status == "success" else "failed",
        "probe_started_at": observed_at,
        "account_subscribe_started_at": observed_at,
        "get_account_info_started_at": None,
        "first_curve_state_at": getattr(result, "decode_finished_at", None) or observed_at if status == "success" else None,
        "first_fdv_emitted_at": getattr(result, "decode_finished_at", None) or observed_at if status == "success" else None,
        "first_response_at": getattr(result, "decode_finished_at", None) or observed_at,
        "winning_probe_source": "accountSubscribe_processed" if status == "success" else "none",
        "probe_attempt_count": 1,
        "account_not_found_retry_count": 0,
        "account_not_found_recovered_by_retry": False,
        "account_not_found_final_failure": False,
        "first_failure_reason": getattr(result, "failure_reason", None) if status != "success" else None,
        "final_failure_reason": None if status == "success" else getattr(result, "failure_reason", None),
        "retry_delays_ms": [],
        "observed_to_probe_started_ms": _duration_ms(create_event.get("observed_at"), observed_at),
        "probe_started_to_first_curve_state_ms": _duration_ms(observed_at, getattr(result, "decode_finished_at", None) or observed_at if status == "success" else None),
        "observed_to_first_fdv_emitted_ms": _duration_ms(create_event.get("observed_at"), getattr(result, "decode_finished_at", None) or observed_at if status == "success" else None),
        "getAccountInfo_latency_ms": None,
        "accountSubscribe_latency_ms": _duration_ms(observed_at, getattr(result, "decode_finished_at", None) or observed_at if status == "success" else None),
        "account_data_slot": getattr(result, "account_data_slot", None) or slot,
        "account_data_encoding": "base64",
        "probe_status": status,
        "probe_error": None if status == "success" else getattr(result, "failure_reason", None),
        "helius_rpc_request_count": int(getattr(result, "helius_rpc_request_count", None) or 0),
        "http_429_count": int(getattr(result, "http_429_count", None) or 0),
    }
    _copy_fdv_probe_fields(result, row)
    for key in ["account_data_slot", "account_data_hash"]:
        value = getattr(result, key, None)
        if value is not None:
            row[key] = value
    return row


def _find_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("result"), dict):
        return payload.get("result")
    params = payload.get("params")
    if isinstance(params, dict) and isinstance(params.get("result"), dict):
        return params.get("result")
    return None


def _slot(result: dict[str, Any]) -> int | None:
    if result.get("slot") is not None:
        return int(result.get("slot"))
    context = result.get("context")
    if isinstance(context, dict) and context.get("slot") is not None:
        return int(context.get("slot"))
    return None


def _signature(result: dict[str, Any]) -> str:
    if result.get("signature"):
        return str(result.get("signature"))
    tx = _transaction_payload(result)
    signatures = ((tx.get("transaction") or {}).get("signatures") or tx.get("signatures") or []) if isinstance(tx, dict) else []
    return str(signatures[0]) if signatures else ""


def _transaction_payload(result: dict[str, Any]) -> dict[str, Any]:
    tx = result.get("transaction")
    if isinstance(tx, dict):
        return tx
    value = result.get("value")
    if isinstance(value, dict) and isinstance(value.get("transaction"), dict):
        return value["transaction"]
    return result


def _instruction_data_bytes(data: Any) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, list):
        try:
            return bytes(int(item) & 0xFF for item in data)
        except (TypeError, ValueError):
            return None
    if isinstance(data, str):
        return _base58_decode(data)
    return None


def _account_string(accounts: list[Any], index: int) -> str | None:
    if index >= len(accounts):
        return None
    value = accounts[index]
    if isinstance(value, dict):
        value = value.get("pubkey") or value.get("account") or value.get("address")
    value = str(value or "")
    return value or None


def _base58_decode(value: str) -> bytes | None:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    decoded = 0
    try:
        for char in value:
            decoded = decoded * 58 + alphabet.index(char)
    except ValueError:
        return None
    leading_zeroes = len(value) - len(value.lstrip("1"))
    payload = decoded.to_bytes((decoded.bit_length() + 7) // 8, "big") if decoded else b""
    return b"\x00" * leading_zeroes + payload


def _websocket_connect(*args: Any, **kwargs: Any) -> Any:
    from websockets.sync.client import connect

    return connect(*args, **kwargs)


def _is_reconnectable_websocket_close(exc: BaseException) -> bool:
    try:
        from websockets.exceptions import ConnectionClosed
    except Exception:
        return type(exc).__name__ in {"ConnectionClosed", "ConnectionClosedOK", "ConnectionClosedError"}
    return isinstance(exc, ConnectionClosed) or type(exc).__name__ in {
        "ConnectionClosed",
        "ConnectionClosedOK",
        "ConnectionClosedError",
    }


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _duration_ms(start: float | int | str | None, end: float | int | str | None) -> float | None:
    started = _num(start)
    ended = _num(end)
    if started is None or ended is None:
        return None
    return round((ended - started) * 1000.0, 3)


def _round_ms(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _capability_audit_md(audit: dict[str, Any]) -> str:
    lines = [
        "# Helius transactionSubscribe Capability Audit",
        "",
        f"- Updated: `{audit['updated_at']}`",
        f"- Recommended endpoint: `{(audit.get('recommended_endpoint') or {}).get('name')}`",
        "",
        "| Endpoint | transactionSubscribe | accountSubscribe | getAccountInfo processed | Errors |",
        "|---|---:|---:|---:|---|",
    ]
    for row in audit.get("endpoints") or []:
        lines.append(
            f"| `{row.get('name')}` | `{row.get('transactionSubscribe_supported')}` | `{row.get('accountSubscribe_supported')}` | `{row.get('getAccountInfo_processed_supported')}` | `{row.get('errors')}` |"
        )
    lines.append("")
    lines.append("Read-only capability audit using existing Helius Developer RPC/WebSocket access.")
    return "\n".join(lines) + "\n"


def _mask_endpoint(endpoint: str | None) -> str | None:
    if not endpoint:
        return endpoint
    api_key = os.getenv("HELIUS_API_KEY")
    masked = endpoint
    if api_key:
        masked = masked.replace(api_key, "***")
    if "api-key=" in masked:
        return masked.split("api-key=", 1)[0] + "api-key=***"
    return masked


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
