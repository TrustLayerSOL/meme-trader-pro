from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_CHANNEL = "#research-updates"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_channel(channel: str | None) -> str:
    cleaned = str(channel or DEFAULT_CHANNEL).strip()
    if not cleaned:
        return DEFAULT_CHANNEL
    return cleaned if cleaned.startswith("#") else f"#{cleaned}"


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
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MemeTraderPro/1.0 DiscordIntelligence",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return int(getattr(response, "status", 0) or 0)


def build_dispatch_plan(
    report: dict[str, Any],
    *,
    webhook_url: str | None,
    channel_webhooks: dict[str, str] | None = None,
    send: bool = False,
    timeout: float = 5.0,
) -> dict[str, Any]:
    events = [row for row in as_list(report.get("discord_events")) if isinstance(row, dict)]
    normalized_webhooks = {
        normalize_channel(channel): str(url)
        for channel, url in (channel_webhooks or {}).items()
        if str(url or "").strip()
    }
    valid_report = report.get("mode") == "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY"
    enabled = bool(send and valid_report and (webhook_url or normalized_webhooks))
    block_reasons: list[str] = []
    if not webhook_url and not normalized_webhooks:
        block_reasons.append("missing_webhook_url")
    if not send:
        block_reasons.append("dry_run")
    if not valid_report:
        block_reasons.append("invalid_report_mode")

    sent = 0
    failed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    if enabled:
        for row in events:
            channel = normalize_channel(row.get("channel"))
            event_webhook = normalized_webhooks.get(channel) or webhook_url
            if not event_webhook:
                blocked.append(
                    {
                        "event_id": row.get("event_id"),
                        "channel": channel,
                        "reason": "missing_channel_webhook",
                    }
                )
                continue
            try:
                status = post_discord_webhook(str(event_webhook), discord_payload(row), timeout=timeout)
                if 200 <= status < 300:
                    sent += 1
                else:
                    failed.append({"event_id": row.get("event_id"), "channel": channel, "status": status})
            except Exception as exc:  # pragma: no cover - network failures are environment-specific.
                failed.append({"event_id": row.get("event_id"), "channel": channel, "error": str(exc)})

    return {
        "mode": "DISCORD_DISPATCH_PLAN",
        "review_only": True,
        "live_execution_locked": True,
        "dispatch_enabled": enabled,
        "events_ready": len(events),
        "events_sent": sent,
        "events_failed": len(failed),
        "events_blocked": len(blocked) if enabled else len(events),
        "block_reasons": block_reasons,
        "blocked_events": blocked,
        "failed_events": failed,
    }
