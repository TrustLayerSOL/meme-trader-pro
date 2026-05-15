#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.json_store import read_json
from wallets.wallet_candidate_quality import build_wallet_candidate_quality_report


def write_wallet_candidate_quality_report(
    *,
    out_path: Path | str = ROOT / "data" / "wallet_candidate_quality_report.json",
    candidate_wallets: Any | None = None,
    paper_watch_wallets: Any | None = None,
    bad_wallets: Any | None = None,
    wallet_behavior: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    report = build_wallet_candidate_quality_report(
        candidate_wallets=candidate_wallets if candidate_wallets is not None else read_json(ROOT / "data" / "candidate_wallets.json", {"candidates": []}),
        paper_watch_wallets=paper_watch_wallets if paper_watch_wallets is not None else read_json(ROOT / "data" / "paper_watch_wallets.json", {"wallets": []}),
        bad_wallets=bad_wallets if bad_wallets is not None else read_json(ROOT / "data" / "bad_wallets.json", []),
        wallet_behavior=wallet_behavior if wallet_behavior is not None else read_json(ROOT / "data" / "wallet_behavior.json", {"wallets": {}}),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    out = ROOT / "data" / "wallet_candidate_quality_report.json"
    report = write_wallet_candidate_quality_report(out_path=out)
    summary = report["summary"]
    print(
        "wrote {} active={} blocked={} strong={} paper_watch={} hold={} reject={}".format(
            out.relative_to(ROOT),
            summary["active_candidates"],
            summary["blocked_candidates"],
            summary["strong_observation"],
            summary["paper_watch_review"],
            summary["hold_review"],
            summary["reject_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
