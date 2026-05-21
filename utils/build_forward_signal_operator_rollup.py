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

from wallets.forward_signal_operator_rollup import build_forward_signal_operator_rollup  # noqa: E402


DEFAULT_PACKET = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_packet.json"
DEFAULT_VALIDATOR = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_review_validator.json"
DEFAULT_DECISION_PREP = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_decision_prep.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_operator_rollup.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_operator_rollup.md"


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


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# MemeTraderPro Forward Signal Operator Rollup",
        "",
        "Single-file operator review of the repaired forward-signal wallet.",
        "",
        "## Summary",
        "",
        f"- Wallets: {summary.get('wallets', 0)}",
        f"- Manual review required: {summary.get('manual_review_required', 0)}",
        f"- Repeatability supported: {summary.get('repeatability_supported', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        f"- Trust mutations allowed: {summary.get('trust_mutations_allowed', 0)}",
        "",
    ]
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        lines.extend(
            [
                f"## Wallet {wallet.get('wallet')}",
                "",
                f"- Decision: {wallet.get('decision_type')}",
                f"- Validation: {wallet.get('validation_status')}",
                f"- Runner rows: {wallet.get('runner_rows')}",
                f"- Unknown 15m rows: {wallet.get('unknown_15m_rows')}",
                f"- Distinct runner token mints: {wallet.get('runner_distinct_token_mints')}",
                f"- Runner signal span seconds: {wallet.get('runner_signal_span_seconds')}",
                f"- Dominant runner token share: {wallet.get('dominant_runner_token_share')}",
                "",
                "Top runner token mints:",
            ]
        )
        for mint in wallet.get("top_token_mints") or []:
            if isinstance(mint, dict):
                lines.append(f"- `{mint.get('token_mint')}`: {mint.get('rows')} rows")
        lines.extend(["", "Required human checks:"])
        for check in wallet.get("required_human_checks") or []:
            lines.append(f"- {check}")
        lines.append("")
    lines.extend(
        [
            "Safety:",
            "- Review-only output.",
            "- This rollup does not approve promotion.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_signal_operator_rollup(
    *,
    packet_path: Path | str = DEFAULT_PACKET,
    validator_path: Path | str = DEFAULT_VALIDATOR,
    decision_prep_path: Path | str = DEFAULT_DECISION_PREP,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    packet_path = Path(packet_path)
    validator_path = Path(validator_path)
    decision_prep_path = Path(decision_prep_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_signal_operator_rollup(
        packet=read_json(packet_path),
        validator=read_json(validator_path),
        decision_prep=read_json(decision_prep_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_signal_review_packet": relative_path(packet_path),
        "forward_signal_review_validator": relative_path(validator_path),
        "forward_signal_decision_prep": relative_path(decision_prep_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "markdown": relative_path(markdown_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build single-file forward signal operator rollup.")
    parser.add_argument("--packet-path", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--validator-path", type=Path, default=DEFAULT_VALIDATOR)
    parser.add_argument("--decision-prep-path", type=Path, default=DEFAULT_DECISION_PREP)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_signal_operator_rollup(
        packet_path=args.packet_path,
        validator_path=args.validator_path,
        decision_prep_path=args.decision_prep_path,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
