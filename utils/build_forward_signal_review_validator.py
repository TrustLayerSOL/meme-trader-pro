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

from wallets.forward_signal_review_validator import build_forward_signal_review_validator  # noqa: E402


DEFAULT_PACKET = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_packet.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_validator.json"
DEFAULT_CSV = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_validator.csv"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_validator.md"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
        rows.append(
            {
                "wallet": wallet.get("wallet"),
                "validation_status": wallet.get("validation_status"),
                "runner_rows": wallet.get("runner_rows"),
                "total_review_rows": wallet.get("total_review_rows"),
                "runner_distinct_token_mints": wallet.get("runner_distinct_token_mints"),
                "runner_signal_span_seconds": wallet.get("runner_signal_span_seconds"),
                "dominant_runner_token_share": wallet.get("dominant_runner_token_share"),
                "unknown_15m_rows": wallet.get("unknown_15m_rows"),
                "wallet_trust_mutation_allowed": wallet.get("wallet_trust_mutation_allowed"),
                "wallet_list_mutation_allowed": wallet.get("wallet_list_mutation_allowed"),
            }
        )
    return rows


def write_csv(path: Path | str, report: dict[str, Any]) -> None:
    rows = csv_rows(report)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "wallet",
        "validation_status",
        "runner_rows",
        "total_review_rows",
        "runner_distinct_token_mints",
        "runner_signal_span_seconds",
        "dominant_runner_token_share",
        "unknown_15m_rows",
        "wallet_trust_mutation_allowed",
        "wallet_list_mutation_allowed",
    ]
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# MemeTraderPro Forward Signal Review Validator",
        "",
        "Review-only validation of whether repaired forward-signal evidence is repeatable or concentrated.",
        "",
        "## Summary",
        "",
        f"- Validated wallets: {summary.get('validated_wallets', 0)}",
        f"- Repeatability-supported wallets: {summary.get('repeatability_supported_wallets', 0)}",
        f"- Concentrated anomaly wallets: {summary.get('concentrated_anomaly_wallets', 0)}",
        f"- Limited-repeatability wallets: {summary.get('limited_repeatability_wallets', 0)}",
        f"- Trust mutations allowed: {summary.get('trust_mutations_allowed', 0)}",
        "",
        "| Wallet | Status | Runner Rows | Distinct Runner Mints | Span Seconds | Dominant Share |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        lines.append(
            f"| {wallet.get('wallet')} | {wallet.get('validation_status')} | {wallet.get('runner_rows')} | "
            f"{wallet.get('runner_distinct_token_mints')} | {wallet.get('runner_signal_span_seconds')} | "
            f"{wallet.get('dominant_runner_token_share')} |"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- This validator does not approve promotions.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_signal_review_validator(
    *,
    packet_path: Path | str = DEFAULT_PACKET,
    report_path: Path | str = DEFAULT_REPORT,
    csv_path: Path | str = DEFAULT_CSV,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    packet_path = Path(packet_path)
    report_path = Path(report_path)
    csv_path = Path(csv_path)
    markdown_path = Path(markdown_path)
    report = build_forward_signal_review_validator(packet=read_json(packet_path), generated_at=generated_at)
    report["input_paths"] = {"forward_signal_review_packet": relative_path(packet_path)}
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
    parser = argparse.ArgumentParser(description="Validate repaired forward-signal manual review packet.")
    parser.add_argument("--packet-path", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_signal_review_validator(
        packet_path=args.packet_path,
        report_path=args.report_path,
        csv_path=args.csv_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
