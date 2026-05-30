#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.forward_signal_review_packet import build_forward_signal_review_packet  # noqa: E402


DEFAULT_RECOMMENDATIONS = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_recommendations.json"
DEFAULT_REPAIRED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_packet.json"
DEFAULT_CSV = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_packet.csv"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_packet.md"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        for row in wallet.get("rows") or []:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "wallet": wallet.get("wallet"),
                    "event_id": row.get("event_id"),
                    "token_mint": row.get("token_mint"),
                    "signal_time": row.get("signal_time"),
                    "observed_action": row.get("observed_action"),
                    "repaired_price": row.get("repaired_price"),
                    "repair_confidence": row.get("repair_confidence"),
                    "later_snapshots_available": row.get("later_snapshots_available"),
                    "outcome_15m": row.get("outcome_15m"),
                    "outcome_15m_confidence": row.get("outcome_15m_confidence"),
                    "transaction_signature": row.get("transaction_signature"),
                }
            )
    return rows


def write_csv(path: Path | str, report: dict[str, Any]) -> None:
    rows = csv_rows(report)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "wallet",
        "event_id",
        "token_mint",
        "signal_time",
        "observed_action",
        "repaired_price",
        "repair_confidence",
        "later_snapshots_available",
        "outcome_15m",
        "outcome_15m_confidence",
        "transaction_signature",
    ]
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# MemeTraderPro Forward Signal Review Packet",
        "",
        "Manual review packet for wallets flagged by repaired forward evidence.",
        "",
        "## Summary",
        "",
        f"- Review wallets: {summary.get('review_wallets', 0)}",
        f"- Review rows: {summary.get('review_rows', 0)}",
        f"- Runner 15m rows: {summary.get('runner_15m_rows', 0)}",
        f"- Flat 15m rows: {summary.get('flat_15m_rows', 0)}",
        f"- Unknown 15m rows: {summary.get('unknown_15m_rows', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
    ]
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        lines.extend(
            [
                f"## Wallet {wallet.get('wallet')}",
                "",
                f"- Recommendation: {wallet.get('recommendation_action')}",
                f"- Records: {wallet.get('records')}",
                f"- Outcomes 15m: {wallet.get('outcomes_15m')}",
                "",
                "| Token | Time | Action | Price | 15m | Tx |",
                "| --- | ---: | --- | ---: | --- | --- |",
            ]
        )
        for row in wallet.get("rows") or []:
            if not isinstance(row, dict):
                continue
            tx = str(row.get("transaction_signature") or "")
            lines.append(
                f"| {row.get('token_mint')} | {row.get('signal_time')} | {row.get('observed_action')} | "
                f"{row.get('repaired_price')} | {row.get('outcome_15m')} | {tx[:12]}... |"
            )
        lines.append("")
    lines.extend(
        [
            "Safety:",
            "- Review-only output.",
            "- This packet does not approve promotions.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_signal_review_packet(
    *,
    recommendations_path: Path | str = DEFAULT_RECOMMENDATIONS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED,
    report_path: Path | str = DEFAULT_REPORT,
    csv_path: Path | str = DEFAULT_CSV,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    recommendations_path = Path(recommendations_path)
    repaired_records_path = Path(repaired_records_path)
    report_path = Path(report_path)
    csv_path = Path(csv_path)
    markdown_path = Path(markdown_path)
    report = build_forward_signal_review_packet(
        recommendations=read_json(recommendations_path),
        repaired_records=read_jsonl(repaired_records_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_merged_calibration_recommendations": relative_path(recommendations_path),
        "forward_entry_context_resolved_records": relative_path(repaired_records_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "csv": relative_path(csv_path),
        "markdown": relative_path(markdown_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build manual review packet for repaired forward-signal wallets.")
    parser.add_argument("--recommendations", type=Path, default=DEFAULT_RECOMMENDATIONS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_signal_review_packet(
        recommendations_path=args.recommendations,
        repaired_records_path=args.repaired_records,
        report_path=args.report_path,
        csv_path=args.csv_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
