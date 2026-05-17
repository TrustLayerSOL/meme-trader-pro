from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def discord_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": str(event.get("message") or ""),
        "username": "MemeTraderPro Research",
        "allowed_mentions": {"parse": []},
    }


def post_discord_webhook(webhook_url: str, payload: dict[str, Any], timeout: float = 5.0) -> int:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return int(getattr(response, "status", 0) or 0)


def build_dispatch_plan(
    report: dict[str, Any],
    *,
    webhook_url: str | None,
    send: bool = False,
    timeout: float = 5.0,
) -> dict[str, Any]:
    events = [row for row in as_list(report.get("discord_events")) if isinstance(row, dict)]
    enabled = bool(send and webhook_url and report.get("mode") == "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY")
    block_reasons: list[str] = []
    if not webhook_url:
        block_reasons.append("missing_webhook_url")
    if not send:
        block_reasons.append("dry_run")
    if report.get("mode") != "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY":
        block_reasons.append("invalid_report_mode")

    sent = 0
    failed: list[dict[str, Any]] = []
    if enabled:
        for row in events:
            try:
                status = post_discord_webhook(str(webhook_url), discord_payload(row), timeout=timeout)
                if 200 <= status < 300:
                    sent += 1
                else:
                    failed.append({"event_id": row.get("event_id"), "status": status})
            except Exception as exc:  # pragma: no cover - network failures are environment-specific.
                failed.append({"event_id": row.get("event_id"), "error": str(exc)})

    return {
        "mode": "DISCORD_DISPATCH_PLAN",
        "review_only": True,
        "live_execution_locked": True,
        "dispatch_enabled": enabled,
        "events_ready": len(events),
        "events_sent": sent,
        "events_failed": len(failed),
        "events_blocked": 0 if enabled else len(events),
        "block_reasons": block_reasons,
        "failed_events": failed,
    }

