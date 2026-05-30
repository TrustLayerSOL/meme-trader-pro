#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.run_wallet_history_backfill import evidence_key, read_jsonl, write_jsonl  # noqa: E402
from wallets.wallet_history_parser import parse_wallet_token_deltas  # noqa: E402


DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_RAW_GLOB = str(ROOT / "data" / "wallet_backfills" / "raw_transactions" / "wallet_history_raw_*.jsonl")
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_raw_refresh_report.json"


def merge_quote_fields(existing: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    changed = False
    for key in ("quote_mint", "quote_amount_delta", "execution_price_quote"):
        if parsed.get(key) not in (None, "") and merged.get(key) in (None, ""):
            merged[key] = parsed.get(key)
            changed = True
    existing_context = merged.get("estimated_entry_context") if isinstance(merged.get("estimated_entry_context"), dict) else {}
    parsed_context = parsed.get("estimated_entry_context") if isinstance(parsed.get("estimated_entry_context"), dict) else {}
    context = dict(existing_context)
    for key in ("quote_mint", "quote_amount_delta", "execution_price_quote", "execution_price_source"):
        if parsed_context.get(key) not in (None, "") and context.get(key) in (None, ""):
            context[key] = parsed_context.get(key)
            changed = True
    if changed:
        merged["estimated_entry_context"] = context
    return merged


def parsed_rows_from_raw_files(raw_glob: str) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    for file_name in sorted(glob.glob(raw_glob)):
        for raw in read_jsonl(Path(file_name)):
            wallet = str(raw.get("wallet") or "").strip()
            tx = raw.get("transaction") if isinstance(raw.get("transaction"), dict) else {}
            signature = str(raw.get("signature") or "")
            if not wallet or not tx:
                continue
            parsed_rows.extend(
                parse_wallet_token_deltas(
                    tx,
                    wallet=wallet,
                    signature=signature,
                    outcome_by_mint={},
                    risk_flags=[],
                )
            )
    return parsed_rows


def build_refresh_report(
    *,
    evidence_path: Path = DEFAULT_EVIDENCE,
    raw_glob: str = DEFAULT_RAW_GLOB,
    report_path: Path = DEFAULT_REPORT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    evidence_rows = read_jsonl(evidence_path)
    parsed_rows = parsed_rows_from_raw_files(raw_glob)
    parsed_by_key = {evidence_key(row): row for row in parsed_rows}

    refreshed: list[dict[str, Any]] = []
    rows_updated = 0
    rows_with_quote_price = 0
    for row in evidence_rows:
        parsed = parsed_by_key.get(evidence_key(row))
        updated = merge_quote_fields(row, parsed) if parsed else row
        if updated != row:
            rows_updated += 1
        if updated.get("execution_price_quote") not in (None, ""):
            rows_with_quote_price += 1
        refreshed.append(updated)

    write_jsonl(evidence_path, refreshed)
    report = {
        "generated_at": generated_at,
        "mode": "WALLET_EVIDENCE_RAW_REFRESH_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "evidence_rows_scanned": len(evidence_rows),
            "raw_rows_parsed": len(parsed_rows),
            "matching_rows_with_raw_parse": sum(1 for row in evidence_rows if evidence_key(row) in parsed_by_key),
            "rows_updated_with_quote_execution": rows_updated,
            "rows_with_quote_execution_price": rows_with_quote_price,
        },
        "input_paths": {
            "wallet_history_evidence": str(evidence_path.relative_to(ROOT)),
            "raw_glob": raw_glob.replace(str(ROOT) + "/", ""),
        },
        "output_paths": {"report": str(report_path.relative_to(ROOT))},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh wallet evidence with quote execution context from preserved raw transactions.")
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--raw-glob", default=DEFAULT_RAW_GLOB)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    report = build_refresh_report(
        evidence_path=args.evidence_path,
        raw_glob=args.raw_glob,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
