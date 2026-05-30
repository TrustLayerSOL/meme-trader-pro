from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_baseline_comparison import compare_wallet_reports


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    report = compare_wallet_reports(
        quant_report=read_json(ROOT / "data" / "wallet_quant_report.json", {}),
        outcome_ledger=read_json(ROOT / "data" / "wallet_outcome_ledger.json", {}),
    )
    out = ROOT / "data" / "wallet_baseline_comparison.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "wrote {} wallets={} overlap={} counts={}".format(
            out.relative_to(ROOT),
            report["counts"]["wallets"],
            report["counts"]["overlap"],
            report["comparison_counts"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
