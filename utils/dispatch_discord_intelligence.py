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


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or send sparse MemeTraderPro Discord intelligence events.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--send", action="store_true", help="Actually post events. Default is dry-run.")
    parser.add_argument("--webhook-url", default=os.getenv("MTP_DISCORD_WEBHOOK_URL", ""))
    args = parser.parse_args()
    plan = build_dispatch_plan(read_json(args.report, {}), webhook_url=args.webhook_url, send=args.send)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
