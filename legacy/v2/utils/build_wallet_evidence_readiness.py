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

from research.wallet_evidence_readiness import build_wallet_evidence_readiness_report  # noqa: E402
from utils.build_wallet_candidate_backfill_targets import read_jsonl  # noqa: E402


DEFAULT_CANDIDATE_TARGETS = ROOT / "data" / "wallet_candidate_backfill_targets.json"
DEFAULT_HISTORY_BACKFILL = ROOT / "data" / "wallet_backfills" / "wallet_history_backfill_report.json"
DEFAULT_EVIDENCE_ENRICHMENT = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_MISSING_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "wallet_missing_market_context_report.json"
DEFAULT_TRUSTED_MARKET_CONTEXT = ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_report.json"
DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_readiness_report.json"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def canonical_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if number != number:
        return ""
    return f"{number:.12g}"


def evidence_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("wallet") or ""),
        str(row.get("transaction_signature") or ""),
        str(row.get("token_mint") or ""),
        str(row.get("observed_action") or ""),
        canonical_number(row.get("token_amount_delta")),
    )


def duplicate_evidence_count(evidence_path: Path | str) -> int:
    seen: set[tuple[str, str, str, str, str]] = set()
    duplicates = 0
    for row in read_jsonl(evidence_path):
        key = evidence_key(row)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
    return duplicates


def evidence_file_row_count(evidence_path: Path | str) -> int:
    return len(read_jsonl(evidence_path))


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_evidence_readiness_report(
    *,
    candidate_targets_path: Path | str = DEFAULT_CANDIDATE_TARGETS,
    history_backfill_path: Path | str = DEFAULT_HISTORY_BACKFILL,
    evidence_enrichment_path: Path | str = DEFAULT_EVIDENCE_ENRICHMENT,
    missing_market_context_path: Path | str = DEFAULT_MISSING_MARKET_CONTEXT,
    trusted_market_context_path: Path | str = DEFAULT_TRUSTED_MARKET_CONTEXT,
    evidence_path: Path | str = DEFAULT_EVIDENCE,
    report_path: Path | str = DEFAULT_REPORT,
) -> dict[str, Any]:
    report_path = Path(report_path)
    candidate_targets_path = Path(candidate_targets_path)
    history_backfill_path = Path(history_backfill_path)
    evidence_enrichment_path = Path(evidence_enrichment_path)
    missing_market_context_path = Path(missing_market_context_path)
    trusted_market_context_path = Path(trusted_market_context_path)
    evidence_path = Path(evidence_path)

    report = build_wallet_evidence_readiness_report(
        candidate_backfill_targets=read_json(candidate_targets_path),
        wallet_history_backfill=read_json(history_backfill_path),
        wallet_evidence_enrichment=read_json(evidence_enrichment_path),
        wallet_missing_market_context=read_json(missing_market_context_path),
        trusted_historical_market_context=read_json(trusted_market_context_path),
        evidence_duplicate_count=duplicate_evidence_count(evidence_path),
        evidence_file_rows=evidence_file_row_count(evidence_path),
    )
    report["input_paths"] = {
        "candidate_backfill_targets": relative_path(candidate_targets_path),
        "wallet_history_backfill": relative_path(history_backfill_path),
        "wallet_evidence_enrichment": relative_path(evidence_enrichment_path),
        "wallet_missing_market_context": relative_path(missing_market_context_path),
        "trusted_historical_market_context": relative_path(trusted_market_context_path),
        "wallet_history_evidence": relative_path(evidence_path),
    }
    report["output_paths"] = {"report": relative_path(report_path)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Stage 3 wallet evidence readiness report.")
    parser.add_argument("--candidate-targets", type=Path, default=DEFAULT_CANDIDATE_TARGETS)
    parser.add_argument("--history-backfill", type=Path, default=DEFAULT_HISTORY_BACKFILL)
    parser.add_argument("--evidence-enrichment", type=Path, default=DEFAULT_EVIDENCE_ENRICHMENT)
    parser.add_argument("--missing-market-context", type=Path, default=DEFAULT_MISSING_MARKET_CONTEXT)
    parser.add_argument("--trusted-market-context", type=Path, default=DEFAULT_TRUSTED_MARKET_CONTEXT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_wallet_evidence_readiness_report(
        candidate_targets_path=args.candidate_targets,
        history_backfill_path=args.history_backfill,
        evidence_enrichment_path=args.evidence_enrichment,
        missing_market_context_path=args.missing_market_context,
        trusted_market_context_path=args.trusted_market_context,
        evidence_path=args.evidence,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
