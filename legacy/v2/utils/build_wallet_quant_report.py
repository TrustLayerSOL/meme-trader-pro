from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.wallet_quant import build_wallet_quant_report


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def main() -> int:
    report = build_wallet_quant_report(
        tracked_wallets=read_json(ROOT / "data" / "tracked_wallets.json", []),
        paper_watch_wallets=read_json(ROOT / "data" / "paper_watch_wallets.json", {"wallets": []}),
        performance=read_json(ROOT / "data" / "wallet_performance.json", {"wallets": {}}),
        behavior=read_json(ROOT / "data" / "wallet_behavior.json", {"wallets": {}}),
    )
    out = ROOT / "data" / "wallet_quant_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {out.relative_to(ROOT)} wallets={report['counts']['wallets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
