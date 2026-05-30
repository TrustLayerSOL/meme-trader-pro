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

from wallets.forward_enhanced_observation_followup import build_forward_enhanced_observation_followup  # noqa: E402


DEFAULT_WATCHLIST = ROOT / "data" / "reports" / "forward_testing" / "forward_enhanced_observation_watchlist.json"
DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_enhanced_observation_followup.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_enhanced_observation_followup.md"


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
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
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


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# MemeTraderPro Forward Enhanced Observation Follow-Up",
        "",
        "Review-only comparison of enhanced-observation wallets against forward records after the watchlist baseline.",
        "",
        "## Summary",
        "",
        f"- Follow-up wallets: {summary.get('followup_wallets', 0)}",
        f"- Wallets meeting review threshold: {summary.get('wallets_meeting_review_threshold', 0)}",
        f"- Wallets collecting more evidence: {summary.get('wallets_collecting_more_evidence', 0)}",
        f"- New forward records: {summary.get('new_forward_records', 0)}",
        f"- New 15m runners: {summary.get('new_runner_15m', 0)}",
        f"- New 15m rugs: {summary.get('new_rug_15m', 0)}",
        f"- New blocked records: {summary.get('new_blocked_records', 0)}",
        "",
        "No promotion is allowed from this artifact.",
        "",
    ]
    for wallet in report.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        lines.extend(
            [
                f"## Wallet {wallet.get('wallet')}",
                "",
                f"- Review status: {wallet.get('review_status')}",
                f"- Trust status: {wallet.get('trust_status')}",
                f"- New forward records: {wallet.get('new_forward_records')}",
                f"- New distinct token mints: {wallet.get('new_distinct_token_mints')}",
                f"- New 15m runners: {wallet.get('new_runner_15m')}",
                f"- New 15m rugs: {wallet.get('new_rug_15m')}",
                f"- New blocked records: {wallet.get('new_blocked_records')}",
                f"- Minimum next forward signals: {wallet.get('minimum_next_forward_signals')}",
                f"- Minimum distinct next token mints: {wallet.get('minimum_distinct_next_token_mints')}",
                "",
            ]
        )
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


def write_forward_enhanced_observation_followup(
    *,
    watchlist_path: Path | str = DEFAULT_WATCHLIST,
    records_path: Path | str = DEFAULT_RECORDS,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    watchlist_path = Path(watchlist_path)
    records_path = Path(records_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_enhanced_observation_followup(
        watchlist=read_json(watchlist_path),
        records=read_jsonl(records_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_enhanced_observation_watchlist": relative_path(watchlist_path),
        "forward_records": relative_path(records_path),
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
    parser = argparse.ArgumentParser(description="Build enhanced-observation follow-up report.")
    parser.add_argument("--watchlist-path", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_enhanced_observation_followup(
        watchlist_path=args.watchlist_path,
        records_path=args.records_path,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
