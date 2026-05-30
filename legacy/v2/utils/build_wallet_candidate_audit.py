from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_audit import build_wallet_candidate_audit


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    report = build_wallet_candidate_audit(
        outcome_ledger=read_json(ROOT / "data" / "wallet_outcome_ledger.json", {}),
        baseline_comparison=read_json(ROOT / "data" / "wallet_baseline_comparison.json", {}),
        review_decisions=read_json(ROOT / "data" / "wallet_review_decisions.json", {}),
        tracked_wallets=read_json(ROOT / "data" / "tracked_wallets.json", []),
        stage4_review=read_json(ROOT / "data" / "reports" / "wallet_backfills" / "wallet_stage4_review_report.json", {}),
    )
    out = ROOT / "data" / "wallet_candidate_audit.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "wrote {} candidates={} promotion={} demotion={}".format(
            out.relative_to(ROOT),
            report["counts"]["candidates"],
            report["counts"]["promotion_review"],
            report["counts"]["demotion_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
