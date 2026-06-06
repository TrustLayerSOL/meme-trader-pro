"""Pump.fun bonding-curve account-state probe helpers.

Paper-only/read-only utilities. This module does not build transactions,
route orders, sign payloads, or execute swaps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Callable
import base64
import hashlib
import json
import time
import urllib.error

from research.mtp_research.validation.forward_efficient_mover_observer import (
    PUMP_FUN_PROGRAM_ID,
    _post_json_rpc,
    resolve_helius_rpc_url,
)


PDA_MARKER = b"ProgramDerivedAddress"
PUMPFUN_CLASSIC_MIN_ACCOUNT_BYTES = 8 + (5 * 8) + 1
DEFAULT_TOKEN_DECIMALS = 6
SOL_DECIMALS = 9
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
getcontext().prec = 50


@dataclass(frozen=True)
class BondingCurveState:
    decode_status: str
    decode_error: str | None = None
    layout_version: str | None = None
    virtual_token_reserves: int | None = None
    virtual_sol_reserves: int | None = None
    real_token_reserves: int | None = None
    real_sol_reserves: int | None = None
    token_total_supply: int | None = None
    complete: bool | None = None
    virtual_quote_reserves: int | None = None
    real_quote_reserves: int | None = None
    quote_mint: str | None = None
    quote_decimals: int | None = None
    token_decimals: int | None = DEFAULT_TOKEN_DECIMALS
    quote_type: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FDVProbeResult:
    probe_status: str
    fdv_source: str = "bonding_curve_account_state"
    fdv_source_confidence: str = "unknown"
    fdv_probe_method: str = "getAccountInfo_processed_bonding_curve"
    mint: str | None = None
    bonding_curve: str | None = None
    fdv_proxy: float | None = None
    price_sol: float | None = None
    fdv_sol: float | None = None
    fdv_usd: float | None = None
    price_quote: float | None = None
    fdv_quote: float | None = None
    fdv_units: str | None = None
    sol_usd: float | None = None
    quote_decimals: int | None = None
    token_decimals: int | None = None
    calculation_status: str | None = None
    calculation_error: str | None = None
    failure_reason: str | None = None
    decode_status: str | None = None
    decode_error: str | None = None
    layout_version: str | None = None
    quote_type: str = "unknown"
    account_state: dict[str, Any] | None = None
    observed_at: float | None = None
    bonding_curve_resolved_at: float | None = None
    get_account_info_started_at: float | None = None
    get_account_info_finished_at: float | None = None
    decode_started_at: float | None = None
    decode_finished_at: float | None = None
    observed_to_bonding_curve_resolved_ms: float | None = None
    bonding_curve_resolved_to_getAccountInfo_ms: float | None = None
    getAccountInfo_latency_ms: float | None = None
    decode_latency_ms: float | None = None
    observed_to_first_fdv_account_state_ms: float | None = None
    helius_rpc_request_count: int = 0
    http_429_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_runtime_event(self, *, timestamp: float | None = None) -> dict[str, Any] | None:
        if self.probe_status != "success" or self.fdv_proxy is None or not self.mint:
            return None
        event_ts = float(timestamp if timestamp is not None else self.decode_finished_at or self.get_account_info_finished_at or time.time())
        observed = float(self.observed_at if self.observed_at is not None else event_ts)
        return {
            "mint": self.mint,
            "timestamp": event_ts,
            "event_observed_at": observed,
            "observed_at": observed,
            "fdv_proxy": float(self.fdv_proxy),
            "fdv_usd": self.fdv_usd,
            "fdv_sol": self.fdv_sol,
            "fdv_quote": self.fdv_quote,
            "fdv_units": self.fdv_units,
            "price_sol": self.price_sol,
            "price_quote": self.price_quote,
            "sol_usd": self.sol_usd,
            "quote_decimals": self.quote_decimals,
            "token_decimals": self.token_decimals,
            "calculation_status": self.calculation_status,
            "quote_type": self.quote_type,
            "account_state": self.account_state,
            "event_count": 1,
            "buy_count": 0,
            "sell_count": 0,
            "active_wallet_count": 1,
            "source_event_type": "first_fdv_account_state",
            "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
            "data_source": self.fdv_source,
            "milestone_provenance": self.fdv_source,
            "fdv_source": self.fdv_source,
            "fdv_source_confidence": self.fdv_source_confidence,
            "fdv_probe_method": self.fdv_probe_method,
            "bonding_curve": self.bonding_curve,
            "first_fdv_source": self.fdv_source,
            "observed_to_bonding_curve_resolved_ms": self.observed_to_bonding_curve_resolved_ms,
            "bonding_curve_resolved_to_getAccountInfo_ms": self.bonding_curve_resolved_to_getAccountInfo_ms,
            "getAccountInfo_latency_ms": self.getAccountInfo_latency_ms,
            "decode_latency_ms": self.decode_latency_ms,
            "observed_to_first_fdv_account_state_ms": self.observed_to_first_fdv_account_state_ms,
            "raw_crossed_10k": float(self.fdv_proxy) >= 10_000,
            "raw_crossed_20k": float(self.fdv_proxy) >= 20_000,
            "raw_crossed_50k": float(self.fdv_proxy) >= 50_000,
        }


class BondingCurveAccountStateProbe:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        rpc_post: Callable[[str, dict[str, Any], int], dict[str, Any]] | None = None,
        sol_usd: float | None = None,
        timeout_seconds: int = 3,
    ) -> None:
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self._rpc_post = rpc_post or _post_json_rpc
        self.sol_usd = sol_usd
        self.timeout_seconds = int(timeout_seconds)
        self.requests_used = 0
        self.http_429_count = 0
        self.failures_by_reason: dict[str, int] = {}
        self.successes = 0

    def probe_birth(self, birth: dict[str, Any], *, now_fn: Callable[[], float] = time.time) -> FDVProbeResult:
        observed = _num(
            birth.get("observed_time")
            or birth.get("observed_at")
            or birth.get("create_log_observed_at")
            or birth.get("log_observed_at")
            or birth.get("timestamp")
        )
        observed_at = float(observed if observed is not None else now_fn())
        mint = str(birth.get("mint") or birth.get("ca") or "").strip()
        if not mint:
            return self._failure("missing_mint", observed_at=observed_at)
        bonding_curve = str(birth.get("bonding_curve") or birth.get("pool_address") or "").strip()
        if not bonding_curve:
            bonding_curve = bonding_curve_pda(mint) or ""
        if not bonding_curve:
            return self._failure("missing_bonding_curve", mint=mint, observed_at=observed_at)
        resolved_at = now_fn()
        started_at = resolved_at
        try:
            response = self._get_account_info(bonding_curve, min_context_slot=_optional_int(birth.get("min_context_slot")))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                self.http_429_count += 1
                return self._failure("rpc_429", mint=mint, bonding_curve=bonding_curve, observed_at=observed_at, resolved_at=resolved_at)
            return self._failure("rpc_error", mint=mint, bonding_curve=bonding_curve, observed_at=observed_at, resolved_at=resolved_at)
        except Exception:
            return self._failure("rpc_error", mint=mint, bonding_curve=bonding_curve, observed_at=observed_at, resolved_at=resolved_at)
        finished_at = now_fn()
        account_data = _account_data_from_get_account_info(response)
        if account_data is None:
            return self._failure(
                "account_not_found",
                mint=mint,
                bonding_curve=bonding_curve,
                observed_at=observed_at,
                resolved_at=resolved_at,
                get_started_at=started_at,
                get_finished_at=finished_at,
            )
        decode_started = finished_at
        state = decode_pump_bonding_curve_account(account_data)
        decode_finished = now_fn()
        fdv = compute_fdv_from_bonding_curve_state(state, sol_usd=self.sol_usd)
        if fdv.probe_status != "success":
            reason = "decode_failed" if state.decode_status != "decoded" else "no_reserve_state"
            return self._failure(
                reason,
                mint=mint,
                bonding_curve=bonding_curve,
                observed_at=observed_at,
                resolved_at=resolved_at,
                get_started_at=started_at,
                get_finished_at=finished_at,
                decode_started_at=decode_started,
                decode_finished_at=decode_finished,
                state=state,
                calculation_error=fdv.calculation_error,
            )
        self.successes += 1
        return FDVProbeResult(
            probe_status="success",
            fdv_source_confidence="high",
            mint=mint,
            bonding_curve=bonding_curve,
            fdv_proxy=fdv.fdv_usd if fdv.fdv_usd is not None else fdv.fdv_sol or fdv.fdv_quote,
            price_sol=fdv.price_sol,
            fdv_sol=fdv.fdv_sol,
            fdv_usd=fdv.fdv_usd,
            price_quote=fdv.price_quote,
            fdv_quote=fdv.fdv_quote,
            fdv_units="usd" if fdv.fdv_usd is not None else ("sol" if fdv.fdv_sol is not None else "quote"),
            sol_usd=self.sol_usd,
            quote_decimals=fdv.quote_decimals,
            token_decimals=fdv.token_decimals,
            calculation_status=fdv.calculation_status,
            decode_status=state.decode_status,
            decode_error=state.decode_error,
            layout_version=state.layout_version,
            quote_type=state.quote_type,
            account_state=state.to_dict(),
            observed_at=observed_at,
            bonding_curve_resolved_at=resolved_at,
            get_account_info_started_at=started_at,
            get_account_info_finished_at=finished_at,
            decode_started_at=decode_started,
            decode_finished_at=decode_finished,
            observed_to_bonding_curve_resolved_ms=_round_ms((resolved_at - observed_at) * 1000.0),
            bonding_curve_resolved_to_getAccountInfo_ms=_round_ms((finished_at - resolved_at) * 1000.0),
            getAccountInfo_latency_ms=_round_ms((finished_at - started_at) * 1000.0),
            decode_latency_ms=_round_ms((decode_finished - decode_started) * 1000.0),
            observed_to_first_fdv_account_state_ms=_round_ms((decode_finished - observed_at) * 1000.0),
            helius_rpc_request_count=self.requests_used,
            http_429_count=self.http_429_count,
        )

    def probe_create_event(self, create_event: dict[str, Any], *, now_fn: Callable[[], float] = time.time) -> FDVProbeResult:
        return self.probe_birth(create_event, now_fn=now_fn)

    def _get_account_info(self, bonding_curve: str, *, min_context_slot: int | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "encoding": "base64",
            "commitment": "processed",
        }
        if min_context_slot is not None:
            options["minContextSlot"] = int(min_context_slot)
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-bonding-curve-get-account-info",
            "method": "getAccountInfo",
            "params": [
                bonding_curve,
                options,
            ],
        }
        self.requests_used += 1
        return self._rpc_post(self.rpc_url or "", payload, self.timeout_seconds)

    def _failure(
        self,
        reason: str,
        *,
        mint: str | None = None,
        bonding_curve: str | None = None,
        observed_at: float | None = None,
        resolved_at: float | None = None,
        get_started_at: float | None = None,
        get_finished_at: float | None = None,
        decode_started_at: float | None = None,
        decode_finished_at: float | None = None,
        state: BondingCurveState | None = None,
        calculation_error: str | None = None,
    ) -> FDVProbeResult:
        self.failures_by_reason[reason] = int(self.failures_by_reason.get(reason) or 0) + 1
        return FDVProbeResult(
            probe_status="failed",
            fdv_source_confidence="none",
            mint=mint,
            bonding_curve=bonding_curve,
            calculation_error=calculation_error,
            failure_reason=reason,
            decode_status=state.decode_status if state else None,
            decode_error=state.decode_error if state else None,
            layout_version=state.layout_version if state else None,
            quote_type=state.quote_type if state else "unknown",
            account_state=state.to_dict() if state else None,
            observed_at=observed_at,
            bonding_curve_resolved_at=resolved_at,
            get_account_info_started_at=get_started_at,
            get_account_info_finished_at=get_finished_at,
            decode_started_at=decode_started_at,
            decode_finished_at=decode_finished_at,
            observed_to_bonding_curve_resolved_ms=_duration_ms(observed_at, resolved_at),
            bonding_curve_resolved_to_getAccountInfo_ms=_duration_ms(resolved_at, get_finished_at),
            getAccountInfo_latency_ms=_duration_ms(get_started_at, get_finished_at),
            decode_latency_ms=_duration_ms(decode_started_at, decode_finished_at),
            observed_to_first_fdv_account_state_ms=_duration_ms(observed_at, decode_finished_at or get_finished_at),
            helius_rpc_request_count=self.requests_used,
            http_429_count=self.http_429_count,
        )

    def metrics(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "failures": sum(self.failures_by_reason.values()),
            "failures_by_reason": dict(sorted(self.failures_by_reason.items())),
            "requests_used": self.requests_used,
            "http_429_count": self.http_429_count,
        }


def bonding_curve_pda(mint: str | None, *, program_id: str = PUMP_FUN_PROGRAM_ID) -> str | None:
    mint_bytes = _base58_decode(str(mint or ""))
    program_bytes = _base58_decode(str(program_id or ""))
    if mint_bytes is None or len(mint_bytes) != 32 or program_bytes is None or len(program_bytes) != 32:
        return None
    seed = b"bonding-curve"
    for bump in range(255, -1, -1):
        candidate = hashlib.sha256(seed + mint_bytes + bytes([bump]) + program_bytes + PDA_MARKER).digest()
        if not _ed25519_compressed_point_on_curve(candidate):
            return _base58_encode(candidate)
    return None


def decode_pump_bonding_curve_account(account_data: bytes | str | list[Any] | None) -> BondingCurveState:
    raw = _coerce_account_data_bytes(account_data)
    if raw is None:
        return BondingCurveState(decode_status="decode_failed", decode_error="account_data_missing")
    if len(raw) < PUMPFUN_CLASSIC_MIN_ACCOUNT_BYTES:
        return BondingCurveState(decode_status="decode_failed", decode_error="account_data_too_short")
    classic = _decode_reserve_tuple_at(raw, 8, layout_version="pumpfun_classic_v1")
    if classic is not None:
        return classic
    for offset in range(16, len(raw) - 40, 8):
        scanned = _decode_reserve_tuple_at(raw, offset, layout_version="pumpfun_extended_scan_v1")
        if scanned is not None:
            return scanned
    return BondingCurveState(decode_status="decode_failed", decode_error="no_reserve_state")


def _decode_reserve_tuple_at(raw: bytes, offset: int, *, layout_version: str) -> BondingCurveState | None:
    values = [_read_u64(raw, offset + index * 8) for index in range(5)]
    if any(value is None for value in values):
        return None
    virtual_token, virtual_sol, real_token, real_sol, total_supply = [int(value or 0) for value in values]
    if not _plausible_bonding_curve_reserves(virtual_token, virtual_sol, real_token, real_sol, total_supply):
        return None
    complete = bool(raw[offset + 40]) if offset + 40 < len(raw) else None
    return BondingCurveState(
        decode_status="decoded",
        layout_version=layout_version,
        virtual_token_reserves=virtual_token,
        virtual_sol_reserves=virtual_sol,
        real_token_reserves=real_token,
        real_sol_reserves=real_sol,
        token_total_supply=total_supply,
        complete=complete,
        token_decimals=DEFAULT_TOKEN_DECIMALS,
        quote_type="sol",
    )


def _plausible_bonding_curve_reserves(
    virtual_token: int,
    virtual_sol: int,
    real_token: int,
    real_sol: int,
    total_supply: int,
) -> bool:
    if virtual_token <= 0 or virtual_sol <= 0 or total_supply <= 0:
        return False
    if total_supply < 1_000_000 or virtual_token < 1_000_000 or virtual_sol < 1_000_000:
        return False
    if real_token < 0 or real_sol < 0:
        return False
    if real_token > total_supply:
        return False
    if virtual_token > total_supply * 10:
        return False
    return True


def compute_fdv_from_bonding_curve_state(curve_state: BondingCurveState, *, sol_usd: float | None = None) -> FDVProbeResult:
    if curve_state.decode_status != "decoded":
        return FDVProbeResult(
            probe_status="failed",
            fdv_source_confidence="none",
            calculation_error=f"decode_failed:{curve_state.decode_error}",
            decode_status=curve_state.decode_status,
            decode_error=curve_state.decode_error,
            layout_version=curve_state.layout_version,
            quote_type=curve_state.quote_type,
            account_state=curve_state.to_dict(),
        )
    token_decimals = int(curve_state.token_decimals if curve_state.token_decimals is not None else DEFAULT_TOKEN_DECIMALS)
    token_reserves = curve_state.virtual_token_reserves
    token_supply = curve_state.token_total_supply
    if token_reserves is None or token_reserves <= 0 or token_supply is None or token_supply <= 0:
        return _calculation_failure(curve_state, "missing_token_reserves_or_supply")
    if curve_state.quote_type == "sol":
        sol_reserves = curve_state.virtual_sol_reserves
        if sol_reserves is None or sol_reserves <= 0:
            return _calculation_failure(curve_state, "missing_sol_reserves")
        price_sol_decimal = (Decimal(sol_reserves) * (Decimal(10) ** token_decimals)) / (
            Decimal(token_reserves) * (Decimal(10) ** SOL_DECIMALS)
        )
        fdv_sol_decimal = price_sol_decimal * (Decimal(token_supply) / (Decimal(10) ** token_decimals))
        fdv_usd_decimal = fdv_sol_decimal * Decimal(str(sol_usd)) if sol_usd is not None else None
        return FDVProbeResult(
            probe_status="success",
            fdv_source_confidence="high",
            fdv_proxy=_round_num(fdv_usd_decimal if fdv_usd_decimal is not None else fdv_sol_decimal),
            price_sol=_round_num(price_sol_decimal),
            fdv_sol=_round_num(fdv_sol_decimal),
            fdv_usd=_round_num(fdv_usd_decimal) if fdv_usd_decimal is not None else None,
            fdv_units="usd" if fdv_usd_decimal is not None else "sol",
            sol_usd=sol_usd,
            quote_decimals=SOL_DECIMALS,
            token_decimals=token_decimals,
            calculation_status="fdv_usd_available" if fdv_usd_decimal is not None else "fdv_sol_only",
            calculation_error=None if fdv_usd_decimal is not None else "fdv_usd_unavailable",
            decode_status=curve_state.decode_status,
            decode_error=curve_state.decode_error,
            layout_version=curve_state.layout_version,
            quote_type=curve_state.quote_type,
            account_state=curve_state.to_dict(),
        )
    quote_reserves = curve_state.virtual_quote_reserves
    quote_decimals = curve_state.quote_decimals
    if quote_reserves is None or quote_reserves <= 0 or quote_decimals is None:
        return _calculation_failure(curve_state, "quote_token_usd_conversion_unavailable")
    price_quote_decimal = (Decimal(quote_reserves) * (Decimal(10) ** token_decimals)) / (
        Decimal(token_reserves) * (Decimal(10) ** int(quote_decimals))
    )
    fdv_quote_decimal = price_quote_decimal * (Decimal(token_supply) / (Decimal(10) ** token_decimals))
    return FDVProbeResult(
        probe_status="success",
        fdv_source_confidence="high",
        fdv_proxy=_round_num(fdv_quote_decimal),
        price_quote=_round_num(price_quote_decimal),
        fdv_quote=_round_num(fdv_quote_decimal),
        fdv_units="quote",
        quote_decimals=int(quote_decimals),
        token_decimals=token_decimals,
        calculation_status="fdv_quote_only",
        calculation_error="fdv_usd_unavailable",
        decode_status=curve_state.decode_status,
        decode_error=curve_state.decode_error,
        layout_version=curve_state.layout_version,
        quote_type=curve_state.quote_type,
        account_state=curve_state.to_dict(),
    )


def bonding_curve_resolution_audit(config: Any, *, source_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(source_root).expanduser() if source_root is not None else config.root / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    hydration = _read_jsonl(root / "hydration_results.jsonl")
    births = _read_jsonl(root / "births.jsonl")
    paths = _read_jsonl(root / "followup_paths.jsonl")
    create_rows = [
        row
        for row in [*hydration, *births]
        if _is_confirmed_create_row(row)
    ]
    unique = _unique_by_mint_or_signature(create_rows)
    pda_derivable = 0
    pda_matches = 0
    missing_pda_matches: list[dict[str, Any]] = []
    for row in unique:
        mint = str(row.get("mint") or _nested(row, "candidate", "mint") or "").strip()
        known_curve = str(row.get("bonding_curve") or row.get("pool_address") or _nested(row, "candidate", "bonding_curve") or "").strip()
        derived = bonding_curve_pda(mint)
        if derived:
            pda_derivable += 1
            if known_curve and derived == known_curve:
                pda_matches += 1
            elif known_curve:
                missing_pda_matches.append({"mint": mint, "known_bonding_curve": known_curve, "derived_bonding_curve": derived})
    audit = {
        "report_id": "bonding_curve_resolution_audit",
        "updated_at": _utc_now(),
        "source_root": str(root),
        "pumpfun_create_rows": len(unique),
        "mint_available": sum(1 for row in unique if row.get("mint") or _nested(row, "candidate", "mint")),
        "bonding_curve_available": sum(1 for row in unique if row.get("bonding_curve") or row.get("pool_address") or _nested(row, "candidate", "bonding_curve")),
        "associated_bonding_curve_available": sum(1 for row in unique if row.get("associated_bonding_curve") or _nested(row, "candidate", "associated_bonding_curve")),
        "creator_available": sum(1 for row in unique if row.get("creator") or _nested(row, "candidate", "creator")),
        "create_instruction_accounts_parsed": sum(1 for row in unique if row.get("parse_confidence") or _nested(row, "candidate", "parse_confidence")),
        "bonding_curve_pda_derivable": pda_derivable,
        "bonding_curve_pda_matches_known": pda_matches,
        "bonding_curve_pda_mismatch_examples": missing_pda_matches[:10],
        "path_rows": len(paths),
        "path_rows_with_curve_or_pool_fields": sum(1 for row in paths if row.get("bonding_curve") or row.get("pool_address") or row.get("curve") or row.get("pool")),
        "getTransaction_required_for_create_resolution_today": True,
        "getTransaction_first_fdv_hot_path_required_after_probe": False,
        "metadata_hot_path_allowed": False,
        "no_new_paid_source": True,
        "paper_only": True,
    }
    _write_json(config.bonding_curve_resolution_audit_json_path, audit)
    config.bonding_curve_resolution_audit_md_path.write_text(_bonding_curve_resolution_audit_md(audit), encoding="utf-8")
    return audit


def write_bonding_curve_first_fdv_probe_summary(
    config: Any,
    *,
    status: dict[str, Any],
    collector_result: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "report_id": "bonding_curve_first_fdv_probe_summary",
        "updated_at": _utc_now(),
        "runtime_label": status.get("runtime_label"),
        "paper_only": True,
        "live_trading_enabled": False,
        "no_new_paid_source": True,
        "first_fdv_probe_sources": status.get("first_fdv_probe_sources") or {},
        "first_fdv_queue": status.get("first_fdv_queue") or {},
        "event_to_rule_latency_p50_p90_p99": status.get("event_to_rule_p50_p90_p99"),
        "confirmed_10k_watches": int(status.get("confirmed_10k_watches") or 0),
        "confirmed_20k_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "paper_buys": int(status.get("paper_buys") or 0),
        "paper_sells": int(status.get("paper_sells") or 0),
        "collector_result": collector_result or {},
        "baseline_comparison": baseline or {},
        "accountSubscribe_bonding_curve_status": "accountSubscribe_bonding_curve_not_implemented",
        "active_account_subscriptions": 0,
    }
    _write_json(config.bonding_curve_first_fdv_probe_summary_json_path, summary)
    config.bonding_curve_first_fdv_probe_summary_md_path.write_text(_bonding_curve_first_fdv_probe_summary_md(summary), encoding="utf-8")
    return summary


def _calculation_failure(curve_state: BondingCurveState, reason: str) -> FDVProbeResult:
    return FDVProbeResult(
        probe_status="failed",
        fdv_source_confidence="none",
        quote_decimals=curve_state.quote_decimals if curve_state.quote_type != "sol" else SOL_DECIMALS,
        token_decimals=curve_state.token_decimals,
        calculation_status="failed",
        calculation_error=reason,
        decode_status=curve_state.decode_status,
        decode_error=curve_state.decode_error,
        layout_version=curve_state.layout_version,
        quote_type=curve_state.quote_type,
        account_state=curve_state.to_dict(),
    )


def _account_data_from_get_account_info(response: dict[str, Any]) -> bytes | None:
    result = response.get("result") if isinstance(response, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        return None
    return _coerce_account_data_bytes(value.get("data"))


def _coerce_account_data_bytes(account_data: bytes | str | list[Any] | None) -> bytes | None:
    if isinstance(account_data, bytes):
        return account_data
    if isinstance(account_data, str):
        try:
            return base64.b64decode(account_data)
        except Exception:
            return None
    if isinstance(account_data, list) and account_data:
        raw = account_data[0]
        encoding = str(account_data[1] if len(account_data) > 1 else "base64").lower()
        if isinstance(raw, str) and encoding == "base64":
            try:
                return base64.b64decode(raw)
            except Exception:
                return None
    return None


def _read_u64(raw: bytes, offset: int) -> int | None:
    if offset + 8 > len(raw):
        return None
    return int.from_bytes(raw[offset : offset + 8], "little")


def _ed25519_compressed_point_on_curve(candidate: bytes) -> bool:
    if len(candidate) != 32:
        return False
    p = 2**255 - 19
    y = int.from_bytes(candidate, "little") & ((1 << 255) - 1)
    if y >= p:
        return False
    d = (-121665 * pow(121666, p - 2, p)) % p
    y2 = (y * y) % p
    numerator = (y2 - 1) % p
    denominator = (d * y2 + 1) % p
    if denominator == 0:
        return False
    x2 = (numerator * pow(denominator, p - 2, p)) % p
    if x2 == 0:
        return True
    return pow(x2, (p - 1) // 2, p) == 1


def _base58_decode(value: str) -> bytes | None:
    if not value:
        return None
    decoded = 0
    try:
        for char in value:
            decoded = decoded * 58 + _BASE58_ALPHABET.index(char)
    except ValueError:
        return None
    leading_zeroes = len(value) - len(value.lstrip("1"))
    payload = decoded.to_bytes((decoded.bit_length() + 7) // 8, "big") if decoded else b""
    return b"\x00" * leading_zeroes + payload


def _base58_encode(raw: bytes) -> str:
    value = int.from_bytes(raw, "big")
    encoded = ""
    while value:
        value, rem = divmod(value, 58)
        encoded = _BASE58_ALPHABET[rem] + encoded
    leading_zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeroes + (encoded or "1")


def _is_confirmed_create_row(row: dict[str, Any]) -> bool:
    status = str(row.get("hydration_status") or row.get("status") or "").lower()
    if status in {"hydrated_create_confirmed", "official_accepted", "confirmed", "official"}:
        return True
    if row.get("mint") and (row.get("bonding_curve") or row.get("pool_address")):
        return True
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    return bool(candidate.get("mint") and (candidate.get("bonding_curve") or candidate.get("pool_address")))


def _unique_by_mint_or_signature(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("mint") or _nested(row, "candidate", "mint") or row.get("signature") or len(unique))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _nested(row: dict[str, Any], *keys: str) -> Any:
    value: Any = row
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bonding_curve_resolution_audit_md(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Bonding Curve Resolution Audit",
            "",
            f"- Updated: `{audit['updated_at']}`",
            f"- Source root: `{audit['source_root']}`",
            f"- Pump.fun create rows: `{audit['pumpfun_create_rows']}`",
            f"- Mint available: `{audit['mint_available']}`",
            f"- Bonding curve available: `{audit['bonding_curve_available']}`",
            f"- Associated bonding curve available: `{audit['associated_bonding_curve_available']}`",
            f"- Creator available: `{audit['creator_available']}`",
            f"- Create instruction accounts parsed: `{audit['create_instruction_accounts_parsed']}`",
            f"- PDA derivable: `{audit['bonding_curve_pda_derivable']}`",
            f"- PDA matches known curve: `{audit['bonding_curve_pda_matches_known']}`",
            f"- Path rows with curve/pool fields: `{audit['path_rows_with_curve_or_pool_fields']}`",
            f"- getTransaction required for create resolution today: `{audit['getTransaction_required_for_create_resolution_today']}`",
            f"- getTransaction required for first-FDV after probe: `{audit['getTransaction_first_fdv_hot_path_required_after_probe']}`",
            "",
            "Read-only audit. No paid provider, metadata hot path, wallet execution, swaps, or routing added.",
        ]
    ) + "\n"


def _bonding_curve_first_fdv_probe_summary_md(summary: dict[str, Any]) -> str:
    sources = summary.get("first_fdv_probe_sources") or {}
    queue = summary.get("first_fdv_queue") or {}
    return "\n".join(
        [
            "# Bonding Curve First-FDV Probe Summary",
            "",
            f"- Updated: `{summary['updated_at']}`",
            f"- Paper-only: `{summary['paper_only']}`",
            f"- No new paid source: `{summary['no_new_paid_source']}`",
            f"- Bonding curve account-state successes: `{sources.get('bonding_curve_account_state_successes')}`",
            f"- Bonding curve account-state failures: `{sources.get('bonding_curve_account_state_failures')}`",
            f"- First-FDV source mix: `{sources.get('source_mix')}`",
            f"- getAccountInfo p50/p90/p99: `{sources.get('getAccountInfo_p50_p90_p99')}`",
            f"- Decode p50/p90/p99: `{sources.get('decode_p50_p90_p99')}`",
            f"- Observed to account-state FDV p50/p90/p99: `{sources.get('observed_to_first_fdv_account_state_p50_p90_p99')}`",
            f"- First path latency p50/p90/p99: `{queue.get('first_path_latency_p50_p90_p99')}`",
            f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
            f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys/sells: `{summary['paper_buys']}` / `{summary['paper_sells']}`",
            f"- accountSubscribe status: `{summary['accountSubscribe_bonding_curve_status']}`",
            "",
            "Paper-only. Confirmed milestone safety remains required for entries.",
        ]
    ) + "\n"


def _duration_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return _round_ms(max(0.0, (float(end) - float(start)) * 1000.0))


def _round_ms(value: float) -> float:
    return round(float(value), 3)


def _round_num(value: float) -> float:
    return round(float(value), 6)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    parsed = _num(value)
    return int(parsed) if parsed is not None else None


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
