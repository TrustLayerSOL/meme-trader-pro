#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.execution_safety import ExecutionSafetyGate  # noqa: E402
from obsidian_export.config import ObsidianExportConfig  # noqa: E402
from obsidian_export.exporter import ObsidianExporter  # noqa: E402
from wallets.forward_wallet_trust_review_packet import TOP_WALLET  # noqa: E402
from wallets.forward_wallet_trust_review_packet import build_forward_wallet_trust_review_packet  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_REPAIRED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_SCORECARD = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_scorecard.json"
DEFAULT_RECOMMENDATIONS = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_recommendations.json"
DEFAULT_RESOLVER = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_report.json"
DEFAULT_CANARY_DIR = ROOT / "data" / "reports" / "forward_testing"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "wallet_trust_review"


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


def read_canary_reports(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    reports: list[dict[str, Any]] = []
    for item in sorted(p.glob("forward_free_rpc_canary_*.json")):
        parsed = read_json(item)
        if parsed:
            parsed["_source_file"] = relative_path(item)
            reports.append(parsed)
    latest = read_json(p / "forward_free_rpc_canary_report.json")
    if latest:
        latest["_source_file"] = relative_path(p / "forward_free_rpc_canary_report.json")
        reports.append(latest)
    return reports


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path | str, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


WALLET_FIELDS = [
    "wallet_address",
    "recommendation_bucket",
    "total_forward_records",
    "known_15m_outcomes",
    "runner_15m_count",
    "flat_15m_count",
    "loser_15m_count",
    "blocked_record_count",
    "repaired_record_count",
    "runner_rate_known_only",
    "runner_rate_all_records",
    "flat_rate_known_only",
    "loser_rate_known_only",
    "context_completion_rate",
    "market_snapshot_coverage",
    "average_liquidity_at_entry",
    "median_liquidity_at_entry",
    "average_market_cap_at_entry",
    "median_market_cap_at_entry",
    "average_entry_delay_seconds",
    "timing_quality",
    "repeatability_score",
    "noise_score",
    "review_status",
    "review_reason",
    "next_required_evidence",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]


EVENT_FIELDS = [
    "wallet_address",
    "token_address",
    "token_symbol",
    "action",
    "observed_at",
    "decision_time_snapshot_at",
    "market_context_available",
    "liquidity_at_entry",
    "market_cap_at_entry",
    "price_at_entry",
    "outcome_15m",
    "return_15m_pct",
    "runner_label",
    "flat_label",
    "loser_label",
    "blocked_reason",
    "repaired_context",
    "source_file",
    "evidence_quality",
    "notes",
    "event_id",
    "transaction_signature",
]


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    gap = report.get("context_gap_analysis") if isinstance(report.get("context_gap_analysis"), dict) else {}
    rpc = report.get("rpc_collection_health") if isinstance(report.get("rpc_collection_health"), dict) else {}
    safety = report.get("safety_lock_verification") if isinstance(report.get("safety_lock_verification"), dict) else {}
    lines = [
        "# First Forward Wallet Trust Review Packet",
        "",
        "Review-only packet for deciding which wallets deserve continued trust validation. This file does not promote wallets, mutate trust, mutate lists, or enable execution.",
        "",
        "## Summary",
        "",
        f"- Review wallets: {summary.get('review_wallets', 0)}",
        f"- Event evidence rows: {summary.get('event_evidence_rows', 0)}",
        f"- Context-blocked records: {summary.get('context_blocked_records', 0)}",
        f"- RPC health status: {summary.get('rpc_health_status')}",
        f"- Safety status: {summary.get('safety_status')}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Top Review Wallets",
        "",
        "| Wallet | Records | Known 15m | Runner | Flat | Loser | Blocked | Context | Review Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('total_forward_records')} | {row.get('known_15m_outcomes')} | "
            f"{row.get('runner_15m_count')} | {row.get('flat_15m_count')} | {row.get('loser_15m_count')} | "
            f"{row.get('blocked_record_count')} | {row.get('context_completion_rate')} | {row.get('review_status')} |"
        )
    lines.extend(
        [
            "",
            "## Context Gap",
            "",
            f"- Total blocked records: {gap.get('total_blocked_records', 0)}",
            f"- Blocked wallets: {gap.get('blocked_wallet_count', 0)}",
            f"- Repaired records: {gap.get('repaired_record_count', 0)}",
            f"- Context completion rate: {gap.get('context_completion_rate', 0)}",
            "",
            "## RPC Health",
            "",
            f"- Status: {rpc.get('status')}",
            f"- Internal cycle interval: {rpc.get('configured_internal_cycle_interval')}",
            f"- Expected heartbeat interval: {rpc.get('expected_heartbeat_interval')}",
            f"- Projected RPC/day: {rpc.get('projected_rpc_day')}",
            f"- Max allowed RPC/day: {rpc.get('max_allowed_rpc_day')}",
            "",
            "## Safety",
            "",
            f"- Safety status: {safety.get('safety_status')}",
            f"- Execution mode: {safety.get('execution_mode')}",
            f"- Live trading allowed: {safety.get('live_trading_allowed')}",
            f"- Live trading enabled: {safety.get('live_trading_enabled')}",
            f"- Paper mode enabled: {safety.get('paper_mode_enabled')}",
            f"- Wallet trust mutations: {safety.get('wallet_trust_mutations')}",
            f"- Wallet-list mutations: {safety.get('wallet_list_mutations')}",
            "",
            "## Guardrail",
            "",
            "No wallet is trusted from this packet. The only allowed conclusion is whether a wallet deserves continued validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def page_frontmatter(kind: str, run_id: str) -> dict[str, Any]:
    return {
        "type": kind,
        "generated_by": "meme-trader-pro",
        "run_id": run_id,
        "review_only": True,
        "live_execution_locked": True,
    }


def build_obsidian_pages(report: dict[str, Any]) -> dict[str, tuple[dict[str, Any], str]]:
    run_id = str(report.get("run_id") or "")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    gap = report.get("context_gap_analysis") if isinstance(report.get("context_gap_analysis"), dict) else {}
    buckets = report.get("wallet_behavior_buckets") if isinstance(report.get("wallet_behavior_buckets"), dict) else {}
    rpc = report.get("rpc_collection_health") if isinstance(report.get("rpc_collection_health"), dict) else {}
    safety = report.get("safety_lock_verification") if isinstance(report.get("safety_lock_verification"), dict) else {}
    case = report.get("top_wallet_case_study") if isinstance(report.get("top_wallet_case_study"), dict) else {}

    wallet_lines = [
        "| Wallet | Review Status | Known 15m | Runner | Flat | Blocked | Context |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("wallets") or []:
        if isinstance(row, dict):
            wallet_lines.append(
                f"| `{row.get('wallet_address')}` | {row.get('review_status')} | {row.get('known_15m_outcomes')} | "
                f"{row.get('runner_15m_count')} | {row.get('flat_15m_count')} | {row.get('blocked_record_count')} | "
                f"{row.get('context_completion_rate')} |"
            )

    bucket_lines = [
        "| Bucket | Wallets | Records | Known | Runner | Flat | Blocked | Action |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in buckets.get("buckets") or []:
        if isinstance(row, dict):
            bucket_lines.append(
                f"| {row.get('bucket')} | {row.get('wallet_count')} | {row.get('total_records')} | "
                f"{row.get('known_outcomes')} | {row.get('runner_count')} | {row.get('flat_count')} | "
                f"{row.get('blocked_count')} | {row.get('recommended_operator_action')} |"
            )

    command_center = f"""# Command Center

## What This Page Does

This is the top-level review surface for the First Forward Wallet Trust Review Packet. It summarizes the current paper-safe wallet-intelligence milestone and links to the review pages.

## Current Mode

- Project: MemeTraderPro / Quant Wallet Tracker V2
- Mode: `{safety.get('execution_mode')}`
- Live trading locked: `{not bool(safety.get('live_trading_enabled'))}`
- Current milestone: First Forward Wallet Trust Review Packet
- Next operator action: review top wallets without promotion

## Forward Evidence Totals

- Review wallets: `{summary.get('review_wallets', 0)}`
- Event evidence rows: `{summary.get('event_evidence_rows', 0)}`
- Context-blocked records: `{summary.get('context_blocked_records', 0)}`
- Promotions allowed: `{summary.get('promotions_allowed', 0)}`

## Pages

- [[Forward Wallet Trust Review Packet]]
- [[Top Wallet Case Study]]
- [[Context Gap Analysis]]
- [[Wallet Behavior Buckets]]
- [[Public RPC Collection Health]]
- [[Safety Locks]]
- [[Research Guardrails]]
"""

    review_packet = f"""# Forward Wallet Trust Review Packet

## What This Page Does

This page shows the top review-only behavioral wallets and the evidence quality behind them. It does not approve promotion or trust.

## Top Wallets

{chr(10).join(wallet_lines)}
"""

    case_study = f"""# Top Wallet Case Study

## What This Page Does

This page focuses on the leading review candidate wallet and explains why it remains not trusted.

## Wallet

`{case.get('wallet_address', TOP_WALLET)}`

## Current Conclusion

{', '.join(str(item) for item in case.get('current_conclusion', []))}

## Why Interesting

{case.get('why_interesting')}

## Why Not Trusted Yet

{case.get('why_not_trusted_yet')}

## Evidence

- Runner history: `{case.get('runner_history')}`
- Flat history: `{case.get('flat_history')}`
- Blocked/context issues: `{case.get('blocked_context_issues')}`
- Additional evidence needed: {case.get('additional_evidence_needed')}
"""

    context_gap = f"""# Context Gap Analysis

## What This Page Does

This page explains why blocked rows cannot be used for trust validation yet.

## Summary

- Total blocked records: `{gap.get('total_blocked_records', 0)}`
- Blocked wallet count: `{gap.get('blocked_wallet_count', 0)}`
- Repairable blocked count: `{gap.get('repairable_blocked_count', 0)}`
- Non-repairable blocked count: `{gap.get('non_repairable_blocked_count', 0)}`
- Repaired record count: `{gap.get('repaired_record_count', 0)}`
- Context completion rate: `{gap.get('context_completion_rate', 0)}`
"""

    bucket_page = f"""# Wallet Behavior Buckets

## What This Page Does

This page groups wallets by review posture. Buckets are not promotions.

## Buckets

{chr(10).join(bucket_lines)}
"""

    rpc_page = f"""# Public RPC Collection Health

## What This Page Does

This page checks whether public-RPC collection is healthy and under budget.

## Health

- Status: `{rpc.get('status')}`
- Configured internal cycle interval: `{rpc.get('configured_internal_cycle_interval')}`
- Expected heartbeat interval: `{rpc.get('expected_heartbeat_interval')}`
- Projected RPC/day: `{rpc.get('projected_rpc_day')}`
- Max allowed RPC/day: `{rpc.get('max_allowed_rpc_day')}`
- Provider-blocked files: `{rpc.get('provider_blocked_files')}`
- Wallet checks: `{rpc.get('wallet_checks')}`
- Collected activity rows: `{rpc.get('collected_activity_rows')}`
- Market snapshots captured: `{rpc.get('market_snapshots_captured')}`
"""

    safety_page = f"""# Safety Locks

## What This Page Does

This page verifies that review artifacts remain paper-safe and cannot mutate trust, wallet lists, or execution.

## Status

- Safety status: `{safety.get('safety_status')}`
- Execution mode: `{safety.get('execution_mode')}`
- Live trading allowed: `{safety.get('live_trading_allowed')}`
- Live trading enabled: `{safety.get('live_trading_enabled')}`
- Paper mode enabled: `{safety.get('paper_mode_enabled')}`
- Promotions allowed: `{safety.get('promotions_allowed')}`
- Wallet-list mutations: `{safety.get('wallet_list_mutations')}`
- Wallet-trust mutations: `{safety.get('wallet_trust_mutations')}`
"""

    guardrails = """# Research Guardrails

## What This Page Does

This page states the hard research boundaries for the wallet-intelligence system.

## Guardrails

- No live trading
- No execution
- No auto-promotion
- No wallet trust mutation
- No wallet list mutation
- No edge/profitability claim
- No trusted-wallet claim
- Forward validation is required before any trust discussion
"""

    pages = {
        "Dashboards/Command Center.md": ("wallet_trust_review_command_center", command_center),
        "Dashboards/Forward Wallet Trust Review Packet.md": ("forward_wallet_trust_review_packet", review_packet),
        "Dashboards/Top Wallet Case Study.md": ("top_wallet_case_study", case_study),
        "Dashboards/Context Gap Analysis.md": ("context_gap_analysis", context_gap),
        "Dashboards/Wallet Behavior Buckets.md": ("wallet_behavior_buckets", bucket_page),
        "Dashboards/Public RPC Collection Health.md": ("public_rpc_collection_health", rpc_page),
        "Dashboards/Safety Locks.md": ("safety_locks", safety_page),
        "Dashboards/Research Guardrails.md": ("research_guardrails", guardrails),
    }
    return {path: (page_frontmatter(kind, run_id), body) for path, (kind, body) in pages.items()}


def export_obsidian_pages(report: dict[str, Any], vault_path: Path | None) -> list[str]:
    if vault_path is None:
        return []
    config = ObsidianExportConfig(vault_path=vault_path, data_dir=ROOT / "data")
    exporter = ObsidianExporter(config)
    written: list[str] = []
    for relative_path, (frontmatter, body) in build_obsidian_pages(report).items():
        path = exporter.write_note(relative_path, frontmatter, body)
        written.append(str(path))
    return written


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path,
    obsidian_vault: Path | None = None,
) -> dict[str, Any]:
    run_id = str(report.get("run_id"))
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_json = output_dir / f"forward_wallet_trust_review_packet_{run_id}.json"
    packet_csv = output_dir / f"forward_wallet_trust_review_packet_{run_id}.csv"
    packet_md = output_dir / f"forward_wallet_trust_review_packet_{run_id}.md"
    events_json = output_dir / f"wallet_event_evidence_{run_id}.json"
    events_csv = output_dir / f"wallet_event_evidence_{run_id}.csv"
    gap_json = output_dir / f"context_gap_analysis_{run_id}.json"
    buckets_json = output_dir / f"wallet_behavior_buckets_{run_id}.json"
    rpc_json = output_dir / f"rpc_collection_health_{run_id}.json"
    safety_json = output_dir / f"safety_lock_verification_{run_id}.json"

    write_json(packet_json, report)
    write_csv(packet_csv, report.get("wallets") or [], WALLET_FIELDS)
    packet_md.write_text(render_markdown(report), encoding="utf-8")
    write_json(events_json, report.get("event_evidence") or [])
    write_csv(events_csv, report.get("event_evidence") or [], EVENT_FIELDS)
    write_json(gap_json, report.get("context_gap_analysis") or {})
    write_json(buckets_json, report.get("wallet_behavior_buckets") or {})
    write_json(rpc_json, report.get("rpc_collection_health") or {})
    write_json(safety_json, report.get("safety_lock_verification") or {})

    latest_paths = {
        output_dir / "forward_wallet_trust_review_packet.json": report,
        output_dir / "wallet_event_evidence.json": report.get("event_evidence") or [],
        output_dir / "context_gap_analysis.json": report.get("context_gap_analysis") or {},
        output_dir / "wallet_behavior_buckets.json": report.get("wallet_behavior_buckets") or {},
        output_dir / "rpc_collection_health.json": report.get("rpc_collection_health") or {},
        output_dir / "safety_lock_verification.json": report.get("safety_lock_verification") or {},
    }
    for path, payload in latest_paths.items():
        write_json(path, payload)
    (output_dir / "forward_wallet_trust_review_packet.md").write_text(render_markdown(report), encoding="utf-8")

    obsidian_pages = export_obsidian_pages(report, obsidian_vault)
    output_paths = {
        "review_packet_json": relative_path(packet_json),
        "review_packet_csv": relative_path(packet_csv),
        "review_packet_markdown": relative_path(packet_md),
        "wallet_event_evidence_json": relative_path(events_json),
        "wallet_event_evidence_csv": relative_path(events_csv),
        "context_gap_analysis_json": relative_path(gap_json),
        "wallet_behavior_buckets_json": relative_path(buckets_json),
        "rpc_collection_health_json": relative_path(rpc_json),
        "safety_lock_verification_json": relative_path(safety_json),
        "obsidian_pages": obsidian_pages,
    }
    report["output_paths"] = output_paths
    write_json(packet_json, report)
    write_json(output_dir / "forward_wallet_trust_review_packet.json", report)
    return output_paths


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the first forward wallet trust review packet.")
    parser.add_argument("--bucket", default="review_behavioral_signal")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--expected-heartbeat-interval-seconds", type=int, default=900)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED)
    parser.add_argument("--merged-scorecard", type=Path, default=DEFAULT_SCORECARD)
    parser.add_argument("--recommendations", type=Path, default=DEFAULT_RECOMMENDATIONS)
    parser.add_argument("--resolver-report", type=Path, default=DEFAULT_RESOLVER)
    parser.add_argument("--canary-dir", type=Path, default=DEFAULT_CANARY_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--obsidian-vault", type=Path, default=None)
    parser.add_argument("--no-obsidian", action="store_true")
    return parser.parse_args(argv)


def resolve_obsidian_vault(args: argparse.Namespace) -> Path | None:
    if args.no_obsidian:
        return None
    if args.obsidian_vault:
        return args.obsidian_vault
    raw = os.getenv("OBSIDIAN_VAULT_PATH")
    if raw:
        return Path(raw).expanduser()
    common = Path("/Users/dianeposs/Projects/obsidian-research/quant-database")
    return common if common.exists() else None


def write_forward_wallet_trust_review_packet(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED,
    merged_scorecard_path: Path | str = DEFAULT_SCORECARD,
    recommendations_path: Path | str = DEFAULT_RECOMMENDATIONS,
    resolver_report_path: Path | str = DEFAULT_RESOLVER,
    canary_dir: Path | str = DEFAULT_CANARY_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    obsidian_vault: Path | None = None,
    bucket: str = "review_behavioral_signal",
    limit: int = 3,
    expected_heartbeat_interval_seconds: int = 900,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_forward_wallet_trust_review_packet(
        original_records=read_jsonl(records_path),
        repaired_records=read_jsonl(repaired_records_path),
        merged_scorecard=read_json(merged_scorecard_path),
        recommendations=read_json(recommendations_path),
        resolver_report=read_json(resolver_report_path),
        canary_reports=read_canary_reports(canary_dir),
        safety_report=ExecutionSafetyGate().report(),
        bucket=bucket,
        limit=limit,
        expected_heartbeat_interval_seconds=expected_heartbeat_interval_seconds,
        run_id=run_id,
        generated_at=time.time() if generated_at is None else generated_at,
    )
    report["input_paths"] = {
        "forward_outcome_records": relative_path(records_path),
        "forward_entry_context_resolved_records": relative_path(repaired_records_path),
        "forward_merged_calibration_scorecard": relative_path(merged_scorecard_path),
        "forward_merged_calibration_recommendations": relative_path(recommendations_path),
        "forward_entry_context_resolver_report": relative_path(resolver_report_path),
        "forward_free_rpc_canary_dir": relative_path(canary_dir),
    }
    output_paths = write_outputs(report, output_dir=Path(output_dir), obsidian_vault=obsidian_vault)
    report["output_paths"] = output_paths
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_wallet_trust_review_packet(
        records_path=args.records,
        repaired_records_path=args.repaired_records,
        merged_scorecard_path=args.merged_scorecard,
        recommendations_path=args.recommendations,
        resolver_report_path=args.resolver_report,
        canary_dir=args.canary_dir,
        output_dir=args.output_dir,
        obsidian_vault=resolve_obsidian_vault(args),
        bucket=args.bucket,
        limit=args.limit,
        expected_heartbeat_interval_seconds=args.expected_heartbeat_interval_seconds,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
