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

from wallets.wallet_evidence_lifecycle import build_wallet_evidence_lifecycle_report  # noqa: E402


DEFAULT_EVIDENCE_PATH = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_lifecycle_report.json"


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_evidence_lifecycle_report(
    *,
    out_path: Path | str = DEFAULT_REPORT_PATH,
    evidence_path: Path | str = DEFAULT_EVIDENCE_PATH,
    evidence_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    evidence_path = Path(evidence_path)
    report = build_wallet_evidence_lifecycle_report(
        evidence_records=evidence_records if evidence_records is not None else read_jsonl(evidence_path),
    )
    report["input_paths"] = {"wallet_history_evidence": relative_path(evidence_path)}
    report["output_paths"] = {"report": relative_path(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-only wallet evidence lifecycle report.")
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--out-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_evidence_lifecycle_report(
        out_path=args.out_path,
        evidence_path=args.evidence_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
