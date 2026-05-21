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

from wallets.forward_enhanced_observation import build_forward_enhanced_observation  # noqa: E402


DEFAULT_ROLLUP = ROOT / "data" / "reports" / "forward_testing" / "forward_signal_operator_rollup.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_enhanced_observation_watchlist.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_enhanced_observation_watchlist.md"


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
        "# MemeTraderPro Forward Enhanced Observation",
        "",
        "Review-only watchlist for forward-signal wallets that showed repeatability but are not trusted.",
        "",
        "## Summary",
        "",
        f"- Enhanced observation wallets: {summary.get('enhanced_observation_wallets', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        f"- Wallet trust mutations allowed: {summary.get('wallet_trust_mutations_allowed', 0)}",
        f"- Wallet-list mutations allowed: {summary.get('wallet_list_mutations_allowed', 0)}",
        "",
        "No promotion is allowed from this artifact.",
        "",
    ]
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        evidence = wallet.get("evidence_summary") if isinstance(wallet.get("evidence_summary"), dict) else {}
        lines.extend(
            [
                f"## Wallet {wallet.get('wallet')}",
                "",
                f"- Lane: {wallet.get('observation_lane')}",
                f"- Review action: {wallet.get('review_action')}",
                f"- Trust status: {wallet.get('trust_status')}",
                f"- Operator recommendation: {wallet.get('operator_recommendation')}",
                f"- Runner rows: {evidence.get('runner_rows')}",
                f"- Unknown 15m rows: {evidence.get('unknown_15m_rows')}",
                f"- Distinct runner token mints: {evidence.get('runner_distinct_token_mints')}",
                f"- Minimum next forward signals: {wallet.get('minimum_next_forward_signals')}",
                f"- Minimum distinct next token mints: {wallet.get('minimum_distinct_next_token_mints')}",
                "",
                "Required next checks:",
            ]
        )
        for check in wallet.get("required_next_checks") or []:
            lines.append(f"- {check}")
        lines.append("")
    lines.extend(
        [
            "Safety:",
            "- Review-only output.",
            "- Live execution remains locked.",
            "- Wallet trust is not mutated.",
            "- Wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_enhanced_observation(
    *,
    rollup_path: Path | str = DEFAULT_ROLLUP,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    rollup_path = Path(rollup_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_enhanced_observation(rollup=read_json(rollup_path), generated_at=generated_at)
    report["input_paths"] = {"forward_signal_operator_rollup": relative_path(rollup_path)}
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
    parser = argparse.ArgumentParser(description="Build review-only forward enhanced observation watchlist.")
    parser.add_argument("--rollup-path", type=Path, default=DEFAULT_ROLLUP)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_enhanced_observation(
        rollup_path=args.rollup_path,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
