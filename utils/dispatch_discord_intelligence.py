#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from notifications.discord_dispatcher import build_dispatch_plan


DEFAULT_REPORT = ROOT / "data" / "reports" / "notifications" / "discord_intelligence_layer_report.json"
DEFAULT_WEBHOOK_CONFIG = ROOT / "data" / "discord_webhooks.local.json"
CHANNEL_WEBHOOK_ENV = {
    "#wallet-review": "MTP_DISCORD_WEBHOOK_WALLET_REVIEW",
    "#behavioral-patterns": "MTP_DISCORD_WEBHOOK_BEHAVIORAL_PATTERNS",
    "#replay-validation": "MTP_DISCORD_WEBHOOK_REPLAY_VALIDATION",
    "#regime-monitor": "MTP_DISCORD_WEBHOOK_REGIME_MONITOR",
    "#wallet-degradation": "MTP_DISCORD_WEBHOOK_WALLET_DEGRADATION",
    "#research-updates": "MTP_DISCORD_WEBHOOK_RESEARCH_UPDATES",
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def load_channel_webhooks(path: Path) -> dict[str, str]:
    config = read_json(path, {})
    source = config.get("webhooks") if isinstance(config.get("webhooks"), dict) else config
    webhooks = {
        str(channel): str(url)
        for channel, url in source.items()
        if str(channel or "").strip() and str(url or "").strip()
    }
    for channel, env_name in CHANNEL_WEBHOOK_ENV.items():
        value = os.getenv(env_name, "")
        if value:
            webhooks[channel] = value
    return webhooks


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or send sparse MemeTraderPro Discord intelligence events.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--send", action="store_true", help="Actually post events. Default is dry-run.")
    parser.add_argument("--webhook-url", default=os.getenv("MTP_DISCORD_WEBHOOK_URL", ""))
    parser.add_argument(
        "--webhook-config",
        type=Path,
        default=DEFAULT_WEBHOOK_CONFIG,
        help="Local JSON mapping of Discord channel names to webhook URLs. This file must stay out of git.",
    )
    args = parser.parse_args()
    plan = build_dispatch_plan(
        read_json(args.report, {}),
        webhook_url=args.webhook_url,
        channel_webhooks=load_channel_webhooks(args.webhook_config),
        send=args.send,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
