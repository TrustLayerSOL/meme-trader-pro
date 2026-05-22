from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.redaction import redact_secrets
from core.rpc_provider import HeliusRpcProvider
from core.rpc_provider import build_public_rpc_providers
from utils.discover_candidate_wallets import RPC_REQUEST_HEADERS


MODE = "FORWARD_FREE_RPC_PROVIDER_ROTATION_REVIEW_ONLY"
DEGRADED_LATENCY_MS = 2_000


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direct_get_slot_probe(provider: HeliusRpcProvider, *, timeout: int = 8) -> dict[str, Any]:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []}).encode("utf-8")
    request = Request(provider.url, data=payload, headers=RPC_REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if response.status != 200:
                return {"ok": False, "http_status": response.status, "error": body[:240]}
            if data.get("error"):
                return {"ok": False, "http_status": response.status, "error": str(data.get("error"))[:240]}
            slot = data.get("result")
            return {"ok": isinstance(slot, int), "http_status": response.status, "slot": slot}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "http_status": exc.code, "error": detail[:240]}
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:240]}


def probe_provider(
    provider: HeliusRpcProvider,
    *,
    probe: Callable[[HeliusRpcProvider], dict[str, Any]] | None = None,
    timeout: int = 8,
) -> dict[str, Any]:
    started = time.monotonic()
    result = probe(provider) if probe else _direct_get_slot_probe(provider, timeout=timeout)
    latency_ms = as_float(result.get("latency_ms"), (time.monotonic() - started) * 1000)
    ok = bool(result.get("ok"))
    status = "offline"
    if ok:
        status = "degraded" if latency_ms >= DEGRADED_LATENCY_MS else "healthy"

    row = {
        "name": provider.name,
        "url": provider.url,
        "safe_url": provider.safe_url,
        "ok": ok,
        "status": status,
        "latency_ms": round(latency_ms, 2),
        "slot": result.get("slot"),
        "http_status": result.get("http_status"),
        "error": redact_secrets(str(result.get("error") or result.get("detail") or ""))[:240],
    }
    if not row["error"]:
        row.pop("error")
    if row["http_status"] is None:
        row.pop("http_status")
    if row["slot"] is None:
        row.pop("slot")
    return row


def rank_provider_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[int, int, float, str]:
        status_rank = {"healthy": 0, "degraded": 1, "offline": 2}.get(str(row.get("status")), 3)
        ok_rank = 0 if row.get("ok") else 1
        return (status_rank, ok_rank, as_float(row.get("latency_ms"), 99_999), str(row.get("name") or ""))

    return sorted(rows, key=key)


def recommend_provider_rotation(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    healthy = [row for row in rows if row.get("status") == "healthy"]
    if healthy:
        return "USE_HEALTHY_FREE_PROVIDER", []
    degraded = [row for row in rows if row.get("status") == "degraded"]
    if degraded:
        return "USE_DEGRADED_FREE_PROVIDER_SMALL_ONLY", ["free_rpc_latency_degraded"]
    return "NO_USABLE_FREE_PROVIDER", ["no_healthy_free_rpc_provider"]


def build_forward_free_rpc_provider_rotation_report(
    *,
    providers: list[HeliusRpcProvider] | None = None,
    free_rpc_urls: str | None = None,
    probe: Callable[[HeliusRpcProvider], dict[str, Any]] | None = None,
    generated_at: float | None = None,
    timeout: int = 8,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    providers = providers if providers is not None else build_public_rpc_providers(free_rpc_urls)
    rows = [
        probe_provider(provider, probe=probe, timeout=timeout)
        for provider in providers
    ]
    ranked = rank_provider_rows(rows)
    recommendation, blockers = recommend_provider_rotation(ranked)
    healthy = [row for row in ranked if row.get("status") == "healthy"]
    degraded = [row for row in ranked if row.get("status") == "degraded"]
    offline = [row for row in ranked if row.get("status") == "offline"]
    recommended = healthy or degraded
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutations": 0,
        "trust_mutations": 0,
        "paid_rpc_allowed": False,
        "providers_tested": len(ranked),
        "healthy_providers": len(healthy),
        "degraded_providers": len(degraded),
        "offline_providers": len(offline),
        "recommended_free_rpc_urls": [row["url"] for row in recommended],
        "recommended_free_rpc_safe_urls": [row["safe_url"] for row in recommended],
        "recommendation": recommendation,
        "blockers": blockers,
        "provider_rows": ranked,
        "next_actions": next_actions_for_recommendation(recommendation),
    }


def next_actions_for_recommendation(recommendation: str) -> list[str]:
    if recommendation == "USE_HEALTHY_FREE_PROVIDER":
        return ["Run a small forward free-RPC canary with only the recommended public endpoint, then compare yield and errors."]
    if recommendation == "USE_DEGRADED_FREE_PROVIDER_SMALL_ONLY":
        return ["Use only tiny manual/on-demand forward cycles; do not start a long public-RPC schedule."]
    return ["Do not run forward public-RPC collection. Wait for paid credits/reset or add another public endpoint and rerun this provider report."]
