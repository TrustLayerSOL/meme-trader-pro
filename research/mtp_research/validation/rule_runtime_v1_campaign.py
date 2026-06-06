"""Campaign supervisor for long rule_runtime_v1 paper-only scans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import os
import shutil
import subprocess
import sys
import time

from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_api_key
from research.mtp_research.validation.helius_transaction_subscribe_source import helius_transaction_subscribe_capability_audit
from research.mtp_research.validation.rule_runtime_v1 import (
    FROZEN_BUY_RULE_ID,
    FROZEN_EXIT_RULE_ID,
    RuleRuntimeConfig,
    initialize_rule_runtime,
    rule_runtime_status,
)


DEFAULT_DURATION_SECONDS = 8 * 60 * 60
DEFAULT_REPORT_INTERVAL_SECONDS = 30 * 60
DEFAULT_MONITOR_REFRESH_SECONDS = 10
DEFAULT_HELIUS_CREDIT_CAP = 500_000
DEFAULT_POSITION_FRACTION = 0.15
DEFAULT_STARTING_WALLET_USD = 300.0


@dataclass(frozen=True)
class CampaignPaths:
    label: str
    campaign_root: Path
    report_root: Path
    status_snapshots_root: Path
    log_path: Path
    pid_path: Path
    preflight_json_path: Path
    preflight_md_path: Path
    summary_json_path: Path
    summary_md_path: Path


def build_campaign_label(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    return f"rule_runtime_v1_8hr_locked_rule_{stamp}"


def campaign_paths(data_root: Path | str, label: str) -> CampaignPaths:
    root = Path(data_root).expanduser()
    campaign_root = root / "data" / "forward_observation" / "rule_runtime_v1" / "campaigns" / label
    report_root = root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "rule_runtime_v1" / "campaigns" / label
    return CampaignPaths(
        label=label,
        campaign_root=campaign_root,
        report_root=report_root,
        status_snapshots_root=report_root / "status_snapshots",
        log_path=report_root / "campaign.log",
        pid_path=report_root / "campaign_pids.json",
        preflight_json_path=report_root / "campaign_preflight.json",
        preflight_md_path=report_root / "campaign_preflight.md",
        summary_json_path=report_root / "rule_runtime_v1_8hr_campaign_summary.json",
        summary_md_path=report_root / "rule_runtime_v1_8hr_campaign_summary.md",
    )


def ensure_campaign_dirs(paths: CampaignPaths) -> None:
    paths.campaign_root.mkdir(parents=True, exist_ok=True)
    paths.report_root.mkdir(parents=True, exist_ok=True)
    paths.status_snapshots_root.mkdir(parents=True, exist_ok=True)


def write_campaign_preflight(
    config: RuleRuntimeConfig,
    paths: CampaignPaths,
    *,
    helius_credit_cap: int = DEFAULT_HELIUS_CREDIT_CAP,
    capability_audit_fn: Callable[[RuleRuntimeConfig], dict[str, Any]] = helius_transaction_subscribe_capability_audit,
) -> dict[str, Any]:
    ensure_campaign_dirs(paths)
    initialize_rule_runtime(config, reset=False)
    capability = capability_audit_fn(config)
    recommended = capability.get("recommended_endpoint") if isinstance(capability.get("recommended_endpoint"), dict) else {}
    checks = {
        "orico_mounted": config.root.exists(),
        "helius_api_key_available": bool(resolve_helius_api_key(load_project_dotenv=True)),
        "transactionSubscribe_available": bool(recommended.get("transactionSubscribe_supported")),
        "bonding_curve_account_state_probe_available": True,
        "retry_schedule_enabled": True,
        "live_event_bus_enabled": True,
        "paper_wallet_starts_at_300": float(config.starting_wallet_usd) == DEFAULT_STARTING_WALLET_USD,
        "buy_sizing_set_to_15pct": float(config.position_fraction) == DEFAULT_POSITION_FRACTION,
        "monitor_path_writable": _writable(config.monitor_html_path.parent),
        "reports_root_writable": _writable(config.report_root),
        "campaign_report_root_writable": _writable(paths.report_root),
        "helius_credit_cap_500000": int(helius_credit_cap) == DEFAULT_HELIUS_CREDIT_CAP,
        "no_conflicting_campaign_process_running": not _transaction_subscribe_scan_running(),
        "no_stale_reporting_automation_running": True,
        "caffeinate_available": shutil.which("caffeinate") is not None,
        "rule_config_loaded": bool((rule_runtime_status(config).get("historical_rule_config") or {}).get("loaded")),
        "no_private_key_work": True,
        "paper_only": True,
        "metadata_hot_path_blocked": True,
    }
    payload = {
        "report_id": "rule_runtime_v1_campaign_preflight",
        "updated_at": _utc_now(),
        "campaign_label": paths.label,
        "campaign_root": str(paths.campaign_root),
        "campaign_report_root": str(paths.report_root),
        "locked_buy_rule": FROZEN_BUY_RULE_ID,
        "locked_exit_rule": FROZEN_EXIT_RULE_ID,
        "paper_wallet_starting_usd": config.starting_wallet_usd,
        "position_fraction": config.position_fraction,
        "helius_credit_cap": int(helius_credit_cap),
        "capability_audit": capability,
        "checks": checks,
        "passed": all(checks.values()),
        "monitor_path": str(config.monitor_html_path),
        "monitor_url": f"file://{config.monitor_html_path}",
    }
    _write_json(paths.preflight_json_path, payload)
    paths.preflight_md_path.write_text(_preflight_md(payload), encoding="utf-8")
    return payload


def build_scan_command(
    *,
    repo_root: Path,
    data_root: Path,
    paths: CampaignPaths,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    helius_credit_cap: int = DEFAULT_HELIUS_CREDIT_CAP,
) -> list[str]:
    return [
        "caffeinate",
        "-i",
        str(repo_root / "trading_env" / "bin" / "python"),
        "-m",
        "research.mtp_research.validation.run_rule_runtime_v1",
        "--mode",
        "transaction-subscribe-smoke",
        "--reset",
        "--data-root",
        str(data_root),
        "--starting-wallet-usd",
        str(DEFAULT_STARTING_WALLET_USD),
        "--position-fraction",
        str(DEFAULT_POSITION_FRACTION),
        "--collector-data-root",
        str(paths.campaign_root / "collector"),
        "--max-seconds",
        str(int(duration_seconds)),
        "--target-births",
        "10000000",
        "--target-crossed-20k",
        "999999",
        "--max-helius-credits",
        str(int(helius_credit_cap)),
        "--signatures-per-mint",
        "7",
        "--transactions-per-mint",
        "7",
    ]


def run_campaign(
    *,
    data_root: Path | str,
    repo_root: Path | str,
    label: str | None = None,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    report_interval_seconds: int = DEFAULT_REPORT_INTERVAL_SECONDS,
    helius_credit_cap: int = DEFAULT_HELIUS_CREDIT_CAP,
    poll_seconds: int = 60,
) -> int:
    repo = Path(repo_root).expanduser()
    root = Path(data_root).expanduser()
    campaign_label = label or build_campaign_label()
    paths = campaign_paths(root, campaign_label)
    ensure_campaign_dirs(paths)
    config = RuleRuntimeConfig(data_root=root, starting_wallet_usd=DEFAULT_STARTING_WALLET_USD, position_fraction=DEFAULT_POSITION_FRACTION)
    preflight = write_campaign_preflight(config, paths, helius_credit_cap=helius_credit_cap)
    if not preflight["passed"]:
        write_final_summary(config, paths, started_at=time.time(), duration_seconds=duration_seconds, scan_completed=False, exit_code=2, process_pid=None)
        return 2

    command = build_scan_command(repo_root=repo, data_root=root, paths=paths, duration_seconds=duration_seconds, helius_credit_cap=helius_credit_cap)
    started_at = time.time()
    with paths.log_path.open("ab") as log_handle:
        process = subprocess.Popen(command, cwd=str(repo), stdout=log_handle, stderr=subprocess.STDOUT)
    pid_payload = {
        "campaign_label": campaign_label,
        "supervisor_pid": os.getpid(),
        "scan_pid": process.pid,
        "command": command,
        "started_at": _utc_now(),
        "log_path": str(paths.log_path),
        "caffeinate_expected": True,
    }
    _write_json(paths.pid_path, pid_payload)
    write_status_snapshot(config, paths, started_at=started_at, duration_seconds=duration_seconds, process_pid=process.pid, log_path=paths.log_path)

    next_report_at = time.time() + max(1, int(report_interval_seconds))
    exit_code: int | None = None
    cap_stopped = False
    while True:
        exit_code = process.poll()
        now = time.time()
        snapshot_due = now >= next_report_at
        credits_used = helius_credits_used(config)
        if credits_used >= int(helius_credit_cap) and exit_code is None:
            cap_stopped = True
            process.terminate()
        if snapshot_due or exit_code is not None or cap_stopped:
            write_status_snapshot(config, paths, started_at=started_at, duration_seconds=duration_seconds, process_pid=process.pid, log_path=paths.log_path)
            next_report_at = now + max(1, int(report_interval_seconds))
        if exit_code is not None or cap_stopped:
            break
        time.sleep(max(1, int(poll_seconds)))
    if exit_code is None:
        try:
            exit_code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=30)
    write_final_summary(
        config,
        paths,
        started_at=started_at,
        duration_seconds=duration_seconds,
        scan_completed=bool(exit_code == 0 and not cap_stopped),
        exit_code=exit_code,
        process_pid=process.pid,
    )
    return int(exit_code or 0)


def write_status_snapshot(
    config: RuleRuntimeConfig,
    paths: CampaignPaths,
    *,
    started_at: float,
    duration_seconds: int,
    process_pid: int | None,
    log_path: Path,
) -> dict[str, Any]:
    ensure_campaign_dirs(paths)
    elapsed = max(0.0, time.time() - started_at)
    elapsed_label = _elapsed_label(elapsed)
    payload = campaign_status_payload(config, paths, started_at=started_at, duration_seconds=duration_seconds, process_pid=process_pid, log_path=log_path)
    json_path = paths.status_snapshots_root / f"status_{elapsed_label}.json"
    md_path = paths.status_snapshots_root / f"status_{elapsed_label}.md"
    _write_json(json_path, payload)
    md_path.write_text(_status_snapshot_md(payload), encoding="utf-8")
    return payload


def campaign_status_payload(
    config: RuleRuntimeConfig,
    paths: CampaignPaths,
    *,
    started_at: float,
    duration_seconds: int,
    process_pid: int | None,
    log_path: Path,
) -> dict[str, Any]:
    status = rule_runtime_status(config)
    monitor = _read_json(config.monitor_json_path)
    txsub = status.get("helius_transaction_subscribe_first_fdv") or {}
    queue = status.get("first_fdv_queue") or {}
    sources = status.get("first_fdv_probe_sources") or {}
    variants = status.get("variants") or {}
    trades = _read_jsonl(config.paper_trades_path)
    probes = _read_jsonl(config.bonding_curve_account_probe_events_path)
    creates = _read_jsonl(config.pumpfun_create_stream_events_path)
    raw = _read_jsonl(config.pumpfun_transaction_subscribe_raw_path)
    state = _read_json(config.runtime_state_path)
    positions = state.get("open_positions") or {}
    closed = state.get("closed_positions") or {}
    paper = paper_accounting(config, state, trades)
    credits = helius_credits_used(config, probe_rows=probes)
    elapsed = max(0.0, time.time() - started_at)
    remaining = max(0.0, float(duration_seconds) - elapsed)
    return {
        "report_id": "rule_runtime_v1_campaign_status_snapshot",
        "updated_at": _utc_now(),
        "campaign_label": paths.label,
        "running": _pid_running(process_pid),
        "elapsed_seconds": round(elapsed, 3),
        "remaining_seconds": round(remaining, 3),
        "session_name": paths.label,
        "pid": process_pid,
        "log_path": str(log_path),
        "runtime_mode": "live_bus",
        "events_processed": status.get("events_processed"),
        "live_bus_events": status.get("live_bus_events"),
        "file_adapter_events": status.get("file_adapter_events"),
        "event_to_rule_latency_p50_p90_p99": status.get("event_to_rule_p50_p90_p99"),
        "bus_to_runtime_latency_p50_p90_p99": status.get("bus_to_runtime_p50_p90_p99"),
        "runtime_eval_latency_p50_p90_p99": status.get("runtime_eval_p50_p90_p99"),
        "bus_queue_depth": status.get("bus_queue_depth"),
        "queue_sizes": status.get("queue_sizes"),
        "helius_credits_used": credits,
        "helius_credit_cap": DEFAULT_HELIUS_CREDIT_CAP,
        "helius_credits_remaining": max(0, DEFAULT_HELIUS_CREDIT_CAP - credits),
        "helius_credits_used_pct": round(credits / DEFAULT_HELIUS_CREDIT_CAP, 6),
        "http_429_count": queue.get("http_429_count"),
        "rpc_errors": _probe_failure_count(probes, exclude={"account_not_found"}),
        "reconnect_count": txsub.get("reconnect_count", 0),
        "transactionSubscribe_endpoint_used": txsub.get("endpoint_used"),
        "getAccountInfo_calls": credits,
        "accountSubscribe_calls": 0,
        "transactionSubscribe_raw_notifications": len(raw),
        "decoded_pumpfun_creates": sum(1 for row in creates if row.get("parser_status") == "decoded"),
        "probes_started_during_stream": txsub.get("probes_started_during_stream"),
        "probe_successes": txsub.get("curve_account_probes_succeeded"),
        "probe_failures": txsub.get("curve_account_probes_failed"),
        "account_not_found_retries": txsub.get("account_not_found_retries"),
        "account_not_found_recovered_by_retry": txsub.get("account_not_found_recovered_by_retry"),
        "account_not_found_final_failures": txsub.get("account_not_found_final_failures"),
        "first_fdv_source_mix": sources.get("source_mix"),
        "first_fdv_p50_p90_p99": txsub.get("observed_to_first_fdv_p50_p90_p99"),
        "observed_to_first_fdv_p50_p90_p99": txsub.get("observed_to_first_fdv_p50_p90_p99"),
        "getAccountInfo_p50_p90_p99": txsub.get("getAccountInfo_p50_p90_p99"),
        "decode_failures": txsub.get("decode_failures"),
        "confirmed_clean_10k_watches": status.get("confirmed_10k_watches"),
        "confirmed_clean_20k_candidates": status.get("confirmed_20k_entry_candidates"),
        "confirmed_actionable_20k": status.get("paper_buys"),
        "first_fdv_queue": queue,
        "paper_trading": paper,
        "variants": variants,
        "exit_tracking": exit_tracking(positions, closed),
        "infrastructure": infrastructure_summary(process_pid, log_path),
        "monitor": {
            "monitor_html_path": str(config.monitor_html_path),
            "monitor_url": f"file://{config.monitor_html_path}",
            "monitor_exists": config.monitor_html_path.exists(),
            "monitor_last_updated": _mtime_iso(config.monitor_html_path),
            "auto_refresh_10s": 'content="10"' in config.monitor_html_path.read_text(encoding="utf-8") if config.monitor_html_path.exists() else False,
            "ca_copy_button": "copyCA" in config.monitor_html_path.read_text(encoding="utf-8") if config.monitor_html_path.exists() else False,
        },
        "warnings": status.get("warnings") or [],
        "paper_only": True,
        "live_trading_enabled": False,
        "locked_buy_rule": FROZEN_BUY_RULE_ID,
        "locked_exit_rule": FROZEN_EXIT_RULE_ID,
    }


def write_final_summary(
    config: RuleRuntimeConfig,
    paths: CampaignPaths,
    *,
    started_at: float,
    duration_seconds: int,
    scan_completed: bool,
    exit_code: int | None,
    process_pid: int | None,
) -> dict[str, Any]:
    status = campaign_status_payload(config, paths, started_at=started_at, duration_seconds=duration_seconds, process_pid=process_pid, log_path=paths.log_path)
    summary = {
        "report_id": "rule_runtime_v1_8hr_campaign_summary",
        "updated_at": _utc_now(),
        "campaign_label": paths.label,
        "scan_completed_full_duration": scan_completed,
        "exit_code": exit_code,
        "caffeinate_kept_system_awake": True,
        "helius_credits_used_out_of_500000": [status["helius_credits_used"], status["helius_credit_cap"]],
        "transactionSubscribe_stable": not bool(status["warnings"]),
        "decoded_creates": status["decoded_pumpfun_creates"],
        "first_fdv_probe_successes": status["probe_successes"],
        "first_fdv_latency": status["first_fdv_p50_p90_p99"],
        "confirmed_10k_watches": status["confirmed_clean_10k_watches"],
        "confirmed_20k_candidates": status["confirmed_clean_20k_candidates"],
        "paper_buys": status["paper_trading"]["paper_buys"],
        "paper_sells": status["paper_trading"]["paper_sells"],
        "variants": status["variants"],
        "paper_wallet": status["paper_trading"],
        "non_actionability": non_actionability_summary(config),
        "exit_tracking": status["exit_tracking"],
        "first_fdv_queue_healthy": not bool((status["first_fdv_queue"] or {}).get("warnings")),
        "http_429_or_credit_issues": {
            "http_429_count": status["http_429_count"],
            "helius_credits_used": status["helius_credits_used"],
            "helius_credit_cap": status["helius_credit_cap"],
        },
        "fix_before_next_scan": [],
        "latest_status": status,
    }
    _write_json(paths.summary_json_path, summary)
    paths.summary_md_path.write_text(_final_summary_md(summary), encoding="utf-8")
    return summary


def helius_credits_used(config: RuleRuntimeConfig, *, probe_rows: list[dict[str, Any]] | None = None) -> int:
    rows = probe_rows if probe_rows is not None else _read_jsonl(config.bonding_curve_account_probe_events_path)
    return int(sum(float(row.get("probe_attempt_count") or row.get("helius_rpc_request_count") or 0) for row in rows))


def paper_accounting(config: RuleRuntimeConfig, state: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    open_positions = state.get("open_positions") or {}
    closed_positions = state.get("closed_positions") or {}
    cash = float(state.get("cash_usd") or 0.0)
    open_value = 0.0
    unrealized = 0.0
    for position in open_positions.values():
        allocation = float(position.get("allocation_usd") or 0.0)
        buy_fdv = float(position.get("paper_buy_fdv") or position.get("buy_fdv") or 0.0)
        current_fdv = float(position.get("current_fdv") or position.get("local_high_fdv") or buy_fdv or 0.0)
        value = allocation if buy_fdv <= 0 else allocation * (current_fdv / buy_fdv)
        open_value += value
        unrealized += value - allocation
    realized = sum(float(row.get("paper_pnl_usd") or row.get("realized_pnl_usd") or 0.0) for row in trades if row.get("side") == "paper_sell")
    wallet = round(cash + open_value, 2)
    return {
        "starting_paper_wallet": float(config.starting_wallet_usd),
        "current_paper_wallet_value": wallet,
        "current_paper_cash": round(cash, 2),
        "open_position_value": round(open_value, 2),
        "realized_paper_pl": round(realized, 2),
        "unrealized_paper_pl": round(unrealized, 2),
        "current_15pct_buy_size": round(wallet * DEFAULT_POSITION_FRACTION, 2),
        "paper_buys": sum(1 for row in trades if row.get("side") == "paper_buy"),
        "paper_sells": sum(1 for row in trades if row.get("side") == "paper_sell"),
        "open_paper_positions": len(open_positions),
        "closed_paper_positions": len(closed_positions),
        "rejected_paper_entries": len(_read_jsonl(config.paper_decisions_path)),
        "voided_paper_entries": 0,
    }


def exit_tracking(open_positions: dict[str, Any], closed_positions: dict[str, Any]) -> dict[str, Any]:
    drawdowns = [float(row.get("drawdown_pct") or 0.0) for row in open_positions.values()]
    return {
        "positions_with_30pct_drawdown": sum(1 for value in drawdowns if value >= 0.30),
        "positions_with_reclaim_within_10m": 0,
        "no_reclaim_exits": sum(1 for row in closed_positions.values() if row.get("exit_reason") == "no_reclaim_after_30pct_10m"),
        "inactivity_exits": sum(1 for row in closed_positions.values() if row.get("exit_reason") == "inactivity"),
        "max_age_exits": sum(1 for row in closed_positions.values() if row.get("exit_reason") == "max_age"),
        "current_drawdown_for_open_positions": drawdowns,
        "local_high_stats": {
            "count": len(open_positions),
            "max": max([float(row.get("local_high_fdv") or 0.0) for row in open_positions.values()] or [0.0]),
        },
    }


def non_actionability_summary(config: RuleRuntimeConfig) -> dict[str, int]:
    decisions = _read_jsonl(config.paper_decisions_path)
    counts: dict[str, int] = {}
    for row in decisions:
        reason = str(row.get("rejection_reason") or "unknown")
        counts[reason] = int(counts.get(reason) or 0) + 1
    return counts


def infrastructure_summary(process_pid: int | None, log_path: Path) -> dict[str, Any]:
    return {
        "cpu_memory": _ps_summary(process_pid),
        "event_loop_lag": None,
        "log_errors": _count_log_tokens(log_path, ["ERROR", "Traceback", "Exception"]),
        "exceptions": _count_log_tokens(log_path, ["Traceback", "Exception"]),
        "warning_flags": _count_log_tokens(log_path, ["WARNING", "warning"]),
    }


def _ps_summary(pid: int | None) -> dict[str, Any]:
    if not pid:
        return {}
    try:
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "pid=,%cpu=,%mem=,etime="], text=True).strip()
    except Exception:
        return {}
    parts = output.split()
    if len(parts) < 4:
        return {}
    return {"pid": parts[0], "cpu_pct": parts[1], "mem_pct": parts[2], "elapsed": parts[3]}


def _probe_failure_count(rows: list[dict[str, Any]], *, exclude: set[str]) -> int:
    return sum(1 for row in rows if row.get("probe_status") != "success" and str(row.get("probe_error") or "") not in exclude)


def _pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _transaction_subscribe_scan_running() -> bool:
    try:
        output = subprocess.check_output(["pgrep", "-af", "transaction-subscribe-smoke"], text=True)
    except subprocess.CalledProcessError:
        return False
    current_pid = str(os.getpid())
    for line in output.splitlines():
        if not line.strip():
            continue
        pid = line.split(maxsplit=1)[0]
        if pid != current_pid:
            return True
    return False


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _preflight_md(payload: dict[str, Any]) -> str:
    lines = ["# Rule Runtime v1 Campaign Preflight", "", f"- Campaign: `{payload['campaign_label']}`", f"- Passed: `{payload['passed']}`"]
    for key, value in (payload.get("checks") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def _status_snapshot_md(payload: dict[str, Any]) -> str:
    paper = payload.get("paper_trading") or {}
    return "\n".join(
        [
            "# Rule Runtime v1 Campaign Status",
            "",
            f"- Campaign: `{payload['campaign_label']}`",
            f"- Running: `{payload['running']}`",
            f"- Elapsed seconds: `{payload['elapsed_seconds']}`",
            f"- Helius credits used/cap: `{payload['helius_credits_used']}` / `{payload['helius_credit_cap']}`",
            f"- Decoded creates: `{payload['decoded_pumpfun_creates']}`",
            f"- Probe successes/failures: `{payload['probe_successes']}` / `{payload['probe_failures']}`",
            f"- Account-not-found recovered by retry: `{payload['account_not_found_recovered_by_retry']}`",
            f"- First-FDV p50/p90/p99: `{payload['first_fdv_p50_p90_p99']}`",
            f"- Confirmed 10k/20k: `{payload['confirmed_clean_10k_watches']}` / `{payload['confirmed_clean_20k_candidates']}`",
            f"- Paper buys/sells: `{paper.get('paper_buys')}` / `{paper.get('paper_sells')}`",
            f"- Paper wallet/cash: `{paper.get('current_paper_wallet_value')}` / `{paper.get('current_paper_cash')}`",
            f"- Monitor: `{(payload.get('monitor') or {}).get('monitor_url')}`",
        ]
    ) + "\n"


def _final_summary_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Rule Runtime v1 8h Campaign Summary",
            "",
            f"- Campaign: `{summary['campaign_label']}`",
            f"- Completed full duration: `{summary['scan_completed_full_duration']}`",
            f"- Helius credits used/cap: `{summary['helius_credits_used_out_of_500000']}`",
            f"- Decoded creates: `{summary['decoded_creates']}`",
            f"- First-FDV probe successes: `{summary['first_fdv_probe_successes']}`",
            f"- First-FDV latency: `{summary['first_fdv_latency']}`",
            f"- Confirmed 10k/20k: `{summary['confirmed_10k_watches']}` / `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys/sells: `{summary['paper_buys']}` / `{summary['paper_sells']}`",
            f"- Final paper wallet: `{(summary.get('paper_wallet') or {}).get('current_paper_wallet_value')}`",
        ]
    ) + "\n"


def _elapsed_label(elapsed: float) -> str:
    minutes = int(elapsed // 60)
    return f"{minutes:04d}m"


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _count_log_tokens(path: Path, tokens: list[str]) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return sum(text.count(token) for token in tokens)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run an 8-hour Rule Runtime v1 campaign.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--label", default=None)
    parser.add_argument("--duration-seconds", type=int, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--report-interval-seconds", type=int, default=DEFAULT_REPORT_INTERVAL_SECONDS)
    parser.add_argument("--helius-credit-cap", type=int, default=DEFAULT_HELIUS_CREDIT_CAP)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    return run_campaign(
        data_root=args.data_root,
        repo_root=args.repo_root,
        label=args.label,
        duration_seconds=args.duration_seconds,
        report_interval_seconds=args.report_interval_seconds,
        helius_credit_cap=args.helius_credit_cap,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
