#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.json_store import read_json
from wallets.wallet_missing_market_context import build_wallet_missing_market_context_targets


DEFAULT_ENRICHMENT_REPORT = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_OUT = ROOT / "data" / "wallet_backfills" / "wallet_missing_market_context_report.json"


def write_wallet_missing_market_context_targets(
    *,
    out_path: Path | str = DEFAULT_OUT,
    enrichment_report_path: Path | str = DEFAULT_ENRICHMENT_REPORT,
    wallet_evidence_enrichment: Any | None = None,
    before_seconds: float = 3600.0,
    after_seconds: float = 3600.0,
    limit: int | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    report = build_wallet_missing_market_context_targets(
        wallet_evidence_enrichment=(
            wallet_evidence_enrichment
            if wallet_evidence_enrichment is not None
            else read_json(Path(enrichment_report_path), {"evidence_records": []})
        ),
        before_seconds=before_seconds,
        after_seconds=after_seconds,
        limit=limit,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only targets for wallet evidence missing market context.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--enrichment-report", type=Path, default=DEFAULT_ENRICHMENT_REPORT)
    parser.add_argument("--before-seconds", type=float, default=3600.0)
    parser.add_argument("--after-seconds", type=float, default=3600.0)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_missing_market_context_targets(
        out_path=args.out,
        enrichment_report_path=args.enrichment_report,
        before_seconds=args.before_seconds,
        after_seconds=args.after_seconds,
        limit=args.limit,
    )
    summary = report["summary"]
    print(
        "wrote {} target_mints={} missing_rows={} wallets_affected={}".format(
            Path(args.out).relative_to(ROOT),
            summary["target_mints"],
            summary["missing_market_context_rows"],
            summary["wallets_affected"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
