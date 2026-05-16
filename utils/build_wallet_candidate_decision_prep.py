from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_decision_prep import build_wallet_candidate_decision_prep


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Build draft-only wallet candidate review decisions from the current audit queue.")
    parser.add_argument("--wallet", action="append", default=[], help="Wallet to include. Can be repeated.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    report = build_wallet_candidate_decision_prep(
        read_json(ROOT / "data" / "wallet_candidate_audit.json", {}),
        selected_wallets=args.wallet or None,
        limit=args.limit,
    )
    out = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_decision_prep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = report["summary"]
    print(
        "wrote {} proposed={} blocked={} promotion={} demotion={}".format(
            out.relative_to(ROOT),
            summary["proposed_decisions"],
            summary["blocked_candidates"],
            summary["approve_promotion"],
            summary["approve_demotion"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
