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

from wallets.wallet_evidence_scorecard import build_wallet_evidence_scorecard_report  # noqa: E402


DEFAULT_READINESS = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_readiness_report.json"
DEFAULT_RECOMMENDATIONS = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_recommendations_report.json"
DEFAULT_LIFECYCLE = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_lifecycle_report.json"
DEFAULT_ENRICHMENT = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_scorecard_report.json"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_evidence_scorecard_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    readiness_path: Path | str = DEFAULT_READINESS,
    recommendations_path: Path | str = DEFAULT_RECOMMENDATIONS,
    lifecycle_path: Path | str = DEFAULT_LIFECYCLE,
    enrichment_path: Path | str = DEFAULT_ENRICHMENT,
    wallet_evidence_readiness: dict[str, Any] | None = None,
    wallet_evidence_recommendations: dict[str, Any] | None = None,
    wallet_evidence_lifecycle: dict[str, Any] | None = None,
    wallet_evidence_enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    readiness_path = Path(readiness_path)
    recommendations_path = Path(recommendations_path)
    lifecycle_path = Path(lifecycle_path)
    enrichment_path = Path(enrichment_path)
    report = build_wallet_evidence_scorecard_report(
        wallet_evidence_readiness=wallet_evidence_readiness if wallet_evidence_readiness is not None else read_json(readiness_path),
        wallet_evidence_recommendations=(
            wallet_evidence_recommendations if wallet_evidence_recommendations is not None else read_json(recommendations_path)
        ),
        wallet_evidence_lifecycle=wallet_evidence_lifecycle if wallet_evidence_lifecycle is not None else read_json(lifecycle_path),
        wallet_evidence_enrichment=wallet_evidence_enrichment if wallet_evidence_enrichment is not None else read_json(enrichment_path),
    )
    report["input_paths"] = {
        "wallet_evidence_readiness": relative_path(readiness_path),
        "wallet_evidence_recommendations": relative_path(recommendations_path),
        "wallet_evidence_lifecycle": relative_path(lifecycle_path),
        "wallet_evidence_enrichment": relative_path(enrichment_path),
    }
    report["output_paths"] = {"report": relative_path(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Stage 3 wallet evidence scorecard.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--recommendations", type=Path, default=DEFAULT_RECOMMENDATIONS)
    parser.add_argument("--lifecycle", type=Path, default=DEFAULT_LIFECYCLE)
    parser.add_argument("--enrichment", type=Path, default=DEFAULT_ENRICHMENT)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_evidence_scorecard_report(
        out_path=args.out_path,
        readiness_path=args.readiness,
        recommendations_path=args.recommendations,
        lifecycle_path=args.lifecycle,
        enrichment_path=args.enrichment,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
