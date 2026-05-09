import argparse
import asyncio
import time
from pathlib import Path

from core.json_store import atomic_write_json
from core.json_store import read_json
from core.runtime_status import update_component
from core.wallet_behavior import build_wallet_behavior_report
from utils.apply_wallet_review import run_apply as run_wallet_review_apply
from utils.discover_candidate_wallets import build_candidate_report
from utils.sync_paper_watch_wallets import build_report as build_paper_watch_report


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_WALLETS = ROOT / "data" / "candidate_wallets.json"
PAPER_WATCH_WALLETS = ROOT / "data" / "paper_watch_wallets.json"
SCHEDULER_STATUS = ROOT / "data" / "wallet_discovery_status.json"
WALLET_BEHAVIOR = ROOT / "data" / "wallet_behavior.json"
WALLET_PERFORMANCE = ROOT / "data" / "wallet_performance.json"
PAPER_TRADES = ROOT / "data" / "paper_trades.json"


DEFAULT_DISCOVERY_CONFIG = {
    "local_hours": 6,
    "local_limit": 5000,
    "from_paper_winners": False,
    "min_winner_pnl_pct": 25,
    "max_winner_mints": 3,
    "signature_limit": 30,
    "max_transactions": 15,
    "max_buyers_per_mint": 20,
    "rpc_timeout": 12,
    "mint": [],
}


def discovery_args(config=None):
    merged = dict(DEFAULT_DISCOVERY_CONFIG)
    merged.update(config or {})
    return argparse.Namespace(**merged)


def safe_apply_preview_summary(result):
    result = result if isinstance(result, dict) else {}
    audit = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    return {
        "dry_run": bool(result.get("dry_run", True)),
        "summary": result.get("summary") if isinstance(result.get("summary"), dict) else {},
        "changes": audit.get("changes")[:20] if isinstance(audit.get("changes"), list) else [],
        "skipped": audit.get("skipped")[:20] if isinstance(audit.get("skipped"), list) else [],
    }


def run_wallet_discovery_cycle(
    discover=None,
    sync_paper_watch=None,
    build_behavior=None,
    apply_preview=None,
    write_json=None,
    update_status=None,
    now=None,
    config=None,
):
    now = now or time.time
    write_json = write_json or atomic_write_json
    update_status = update_status or update_component
    discover = discover or (lambda: build_candidate_report(discovery_args(config)))
    sync_paper_watch = sync_paper_watch or build_paper_watch_report
    build_behavior = build_behavior or (
        lambda: build_wallet_behavior_report(
            performance=read_json(WALLET_PERFORMANCE, {"wallets": {}, "signals": []}),
            paper_state=read_json(PAPER_TRADES, {"open_trades": [], "closed_trades": [], "failed_trades": []}),
        )
    )
    apply_preview = apply_preview or run_wallet_review_apply

    started_at = now()
    update_status("wallet_discovery", status="cycle_running", live_execution_locked=True)

    candidate_report = discover()
    write_json(CANDIDATE_WALLETS, candidate_report)

    paper_watch_report = sync_paper_watch()
    write_json(PAPER_WATCH_WALLETS, paper_watch_report)

    behavior_report = build_behavior()
    write_json(WALLET_BEHAVIOR, behavior_report)

    apply_result = apply_preview(dry_run=True)
    candidate_rows = candidate_report.get("candidates") if isinstance(candidate_report, dict) else []
    paper_watch_rows = paper_watch_report.get("wallets") if isinstance(paper_watch_report, dict) else []
    summary = {
        "mode": "WALLET_DISCOVERY_SCHEDULER",
        "generated_at": now(),
        "started_at": started_at,
        "live_execution_locked": True,
        "mutates_tracked_wallets": False,
        "apply_dry_run_only": True,
        "candidate_wallets": len(candidate_rows or []),
        "paper_watch_wallets": len(paper_watch_rows or []),
        "candidate_summary": candidate_report.get("review_summary", {}) if isinstance(candidate_report, dict) else {},
        "paper_watch_summary": paper_watch_report.get("summary", {}) if isinstance(paper_watch_report, dict) else {},
        "behavior_summary": {
            "wallet_count": behavior_report.get("wallet_count", 0) if isinstance(behavior_report, dict) else 0,
            "label_counts": behavior_report.get("label_counts", {}) if isinstance(behavior_report, dict) else {},
        },
        "apply_preview": safe_apply_preview_summary(apply_result),
    }
    write_json(SCHEDULER_STATUS, summary)
    update_status(
        "wallet_discovery",
        status="cycle_ok",
        live_execution_locked=True,
        candidate_wallets=summary["candidate_wallets"],
        paper_watch_wallets=summary["paper_watch_wallets"],
        behavior_wallets=summary["behavior_summary"]["wallet_count"],
        approved_changes=summary["apply_preview"]["summary"].get("approved_decisions", 0),
        heartbeat_interval=(config or {}).get("interval_seconds"),
    )
    return summary


async def wallet_discovery_loop(interval_seconds=300, config=None):
    config = dict(config or {})
    config.setdefault("interval_seconds", interval_seconds)
    while True:
        try:
            await asyncio.to_thread(run_wallet_discovery_cycle, config=config)
        except Exception as exc:
            update_component(
                "wallet_discovery",
                status="cycle_error",
                live_execution_locked=True,
                last_error=str(exc)[:240],
                heartbeat_interval=interval_seconds,
            )
        await asyncio.sleep(interval_seconds)
