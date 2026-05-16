import argparse
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from core.data_freshness import DataFreshness
from core.decision_explainer import generate_decision_explanation
from core.decision_explainer import generate_google_decision_explanation
from core.decision_explainer import generate_groq_decision_explanation
from core.env_loader import load_env
from core.json_store import locked_update_json
from core.json_store import read_json
from core.position_cockpit import build_candles, build_position_rows
from core.performance_analyzer import PerformanceAnalyzer
from core.protection_amounts import apply_manual_amount_to_watchlist
from core.protection_amounts import build_manual_amount_patch
from core.redaction import redact_secrets
from core.rpc_provider import build_helius_rpc_providers
from core.rpc_provider import check_helius_provider_health
from core.runtime_status import DEFAULT_STATUS, load_status
from core.settings_manager import load_settings as load_bot_settings
from core.wallet_discovery import apply_review_policy
from core.wallet_discovery import normalize_tracked_wallets
from research.evidence_layer_completion import build_evidence_layer_completion_report
from core.wallet_lifecycle import build_wallet_lifecycle_report
from core.wallet_quant import build_wallet_quant_report
from utils.apply_wallet_review import run_apply as run_wallet_review_apply
from wallets.wallet_candidate_backfill_targets import build_wallet_candidate_backfill_targets
from wallets.wallet_candidate_blocker_reducer import build_wallet_candidate_blocker_reducer
from wallets.wallet_candidate_collection_plan import build_wallet_candidate_collection_plan
from wallets.wallet_candidate_context_recovery_closeout import build_wallet_candidate_context_recovery_closeout
from wallets.wallet_candidate_context_recovery_queue import build_wallet_candidate_context_recovery_queue
from wallets.wallet_candidate_context_recovery_runner import build_wallet_candidate_context_recovery_report
from wallets.wallet_candidate_decision_prep import build_wallet_candidate_decision_prep
from wallets.wallet_candidate_evidence_plan import build_wallet_candidate_evidence_plan
from wallets.wallet_candidate_quality import build_wallet_candidate_quality_report
from wallets.wallet_candidate_quality_review import build_wallet_candidate_quality_review
from wallets.wallet_candidate_review_summary import build_wallet_candidate_review_summary
from wallets.wallet_cycle_report import build_wallet_cycle_report
from wallets.wallet_evidence_enrichment import build_wallet_evidence_enrichment_report
from wallets.wallet_history_backfill import build_wallet_history_backfill_report
from wallets.wallet_missing_market_context import build_wallet_missing_market_context_targets
from wallets.wallet_replay_review import build_wallet_replay_review


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "desktop_gui"
DB_FILE = ROOT / "data" / "memetrader.db"
PAPER_TRADES_FILE = ROOT / "data" / "paper_trades.json"
WATCHLIST_FILE = ROOT / "data" / "manual_watchlist.json"
SOCIAL_STATE_FILE = ROOT / "data" / "social_state.json"
CATALYST_CARDS_FILE = ROOT / "data" / "catalyst_cards.json"
SETTINGS_FILE = ROOT / "data" / "bot_settings.json"
LIVE_STATE_FILE = ROOT / "live_state.json"
TRACKED_WALLETS_FILE = ROOT / "data" / "tracked_wallets.json"
WALLET_PERFORMANCE_FILE = ROOT / "data" / "wallet_performance.json"
WALLET_BEHAVIOR_FILE = ROOT / "data" / "wallet_behavior.json"
CANDIDATE_WALLETS_FILE = ROOT / "data" / "candidate_wallets.json"
PAPER_WATCH_WALLETS_FILE = ROOT / "data" / "paper_watch_wallets.json"
WALLET_REVIEW_DECISIONS_FILE = ROOT / "data" / "wallet_review_decisions.json"
WALLET_REPLAY_SCORECARD_FILE = ROOT / "data" / "wallet_replay_scorecard.json"
WALLET_CYCLE_REPORT_FILE = ROOT / "data" / "wallet_cycle_report.json"
WALLET_CANDIDATE_AUDIT_FILE = ROOT / "data" / "wallet_candidate_audit.json"
WALLET_CANDIDATE_QUALITY_REPORT_FILE = ROOT / "data" / "wallet_candidate_quality_report.json"
WALLET_CANDIDATE_QUALITY_REVIEW_FILE = ROOT / "data" / "wallet_candidate_quality_review.json"
WALLET_CANDIDATE_EVIDENCE_PLAN_FILE = ROOT / "data" / "wallet_candidate_evidence_plan.json"
WALLET_CANDIDATE_BACKFILL_TARGETS_FILE = ROOT / "data" / "wallet_candidate_backfill_targets.json"
WALLET_CANDIDATE_COLLECTION_PLAN_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_plan.json"
WALLET_CANDIDATE_COLLECTION_BATCH_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_batch_report.json"
WALLET_CANDIDATE_BLOCKER_REDUCER_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_blocker_reducer.json"
WALLET_CANDIDATE_CONTEXT_RECOVERY_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_queue.json"
WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_runner.json"
WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_FILE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_closeout.json"
WALLET_HISTORY_BACKFILL_REPORT_FILE = ROOT / "data" / "wallet_backfills" / "wallet_history_backfill_report.json"
WALLET_EVIDENCE_ENRICHMENT_REPORT_FILE = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
WALLET_MISSING_MARKET_CONTEXT_REPORT_FILE = ROOT / "data" / "wallet_backfills" / "wallet_missing_market_context_report.json"
WALLET_EVIDENCE_READINESS_REPORT_FILE = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_readiness_report.json"
WALLET_EVIDENCE_SCORECARD_REPORT_FILE = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_evidence_scorecard_report.json"
EVIDENCE_LAYER_COMPLETION_REPORT_FILE = ROOT / "data" / "reports" / "wallet_backfills" / "evidence_layer_completion_report.json"
BAD_WALLETS_FILE = ROOT / "data" / "bad_wallets.json"
LOG_DIR = ROOT / "logs"
LOG_FILES = {
    "bot": LOG_DIR / "bot.log",
    "dashboard": LOG_DIR / "dashboard.log",
    "desktop_api": LOG_DIR / "desktop_api.log",
    "watchdog": LOG_DIR / "watchdog.log",
}

CRITICAL_COMPONENTS = ("bot", "websocket", "scanner")
FRESH_SECONDS = 90
SERVER_STARTED_AT = time.time()
DESKTOP_API_TOKEN = os.getenv("MTP_DESKTOP_API_TOKEN")
SESSION_FILE = ROOT / "data" / "desktop_api_session.json"
CHART_METRICS = ("market_cap", "price", "liquidity")
PROVIDER_HEALTH_TTL_SECONDS = 30
QUOTE_COOLDOWN_RECOVERY_SECONDS = 300
SOCIAL_SOURCE_FRESH_SECONDS = 3600
SOCIAL_COLLECTOR_FRESH_SECONDS = 1800
PROVIDER_HEALTH_CACHE = {"updated_at": 0, "payload": None}
STATE_CACHE_TTL_SECONDS = 0.75
STATE_CACHE = {"updated_at": 0, "data": None}
STATE_CACHE_LOCK = threading.Lock()
ASSET_METADATA_TTL_SECONDS = 300
ASSET_METADATA_CACHE = {}
DESKTOP_ENV_LOADED = False
CANDIDATE_CONTEXTS = {
    "scanner_skip",
    "scanner_entry_candidate",
    "scanner_runtime_skip",
}
ALLOWED_CORS_ORIGINS = {
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}
ALLOWED_DEV_CORS_PORTS = {5173, 5174, 5175, 5176, 1420}


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def parse_int_query(query, key, default, minimum=None, maximum=None):
    try:
        value = int((query.get(key) or [default])[0] or default)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def bounded_int(value, default, minimum=None, maximum=None):
    try:
        value = int(value or default)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def path_param(value):
    return unquote(str(value or "")).strip()


def first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def allowed_cors_origin(origin):
    if not origin:
        return None
    origin = str(origin).strip()
    if origin in ALLOWED_CORS_ORIGINS:
        return origin
    parsed = urlparse(origin)
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port in ALLOWED_DEV_CORS_PORTS
    ):
        return origin
    return None


def load_desktop_env():
    global DESKTOP_ENV_LOADED
    if DESKTOP_ENV_LOADED:
        return
    load_env()
    DESKTOP_ENV_LOADED = True


def desktop_session_payload(token=None):
    return {
        "token": token or DESKTOP_API_TOKEN,
        "started_at": SERVER_STARTED_AT,
        "process_id": os.getpid(),
    }


def write_desktop_session_file(token=None):
    payload = desktop_session_payload(token)
    if not payload.get("token"):
        return None

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = SESSION_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w") as handle:
        json.dump(payload, handle)
    if os.name != "nt":
        os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, SESSION_FILE)
    if os.name != "nt":
        os.chmod(SESSION_FILE, 0o600)
    return payload


def json_safe(value):
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def age_seconds(timestamp):
    value = safe_float(timestamp, None)
    if value is None:
        return None
    return max(0, time.time() - value)


def runtime_fresh_seconds(item):
    item = item if isinstance(item, dict) else {}
    heartbeat_interval = safe_float(item.get("heartbeat_interval"), 0)
    if heartbeat_interval > 0:
        return max(FRESH_SECONDS, heartbeat_interval * 2)
    return FRESH_SECONDS


def quote_runtime_health(item, item_age, fresh):
    item = item if isinstance(item, dict) else {}
    state = str(item.get("state") or item.get("status") or "").lower()
    last_error = item.get("last_error") or item.get("last_rpc_error")
    if state in ("cooldown_after_429", "http_429"):
        if item_age is not None and item_age > QUOTE_COOLDOWN_RECOVERY_SECONDS:
            return True, state, f"last quote cooldown expired {int(item_age)}s ago; idle is healthy"
        return False, state, runtime_component_detail(item, state, False) or "quote provider cooling down"
    if state.startswith("http_") or state in ("missing_api_key", "quote_exception") or last_error:
        return False, state or "quote_error", runtime_component_detail(item, state, False)
    if state == "quote_ok":
        if fresh:
            return True, "quote_ok", runtime_component_detail(item, state, True)
        if item_age is not None:
            return True, "quote_ok", f"last quote OK {int(item_age)}s ago; idle is healthy"
    return fresh, state or "unknown", runtime_component_detail(item, state, fresh)


def read_state_files():
    now = time.time()
    with STATE_CACHE_LOCK:
        cached = STATE_CACHE.get("data")
        updated_at = safe_float(STATE_CACHE.get("updated_at"), 0)
        if cached is not None and now - updated_at <= STATE_CACHE_TTL_SECONDS:
            return cached

    data = {
        "paper": load_paper_trade_state()[0],
        "watchlist": read_json(WATCHLIST_FILE, []),
        "runtime": load_status(),
        "social": read_json(SOCIAL_STATE_FILE, {"events": []}),
        "catalysts": read_json(CATALYST_CARDS_FILE, {"cards": []}),
        "settings": read_json(SETTINGS_FILE, {}),
        "tracked_wallets": read_json(TRACKED_WALLETS_FILE, []),
        "wallet_performance": read_json(WALLET_PERFORMANCE_FILE, {"wallets": {}, "signals": []}),
        "wallet_behavior": read_json(WALLET_BEHAVIOR_FILE, {"wallets": {}}),
        "candidate_wallets": read_json(CANDIDATE_WALLETS_FILE, {"candidates": []}),
        "paper_watch_wallets": read_json(PAPER_WATCH_WALLETS_FILE, {"wallets": []}),
        "bad_wallets": read_json(BAD_WALLETS_FILE, []),
        "wallet_review_decisions": read_json(WALLET_REVIEW_DECISIONS_FILE, {"decisions": []}),
        "wallet_replay_scorecard": read_json(WALLET_REPLAY_SCORECARD_FILE, {}),
        "wallet_cycle_report": read_json(WALLET_CYCLE_REPORT_FILE, {}),
        "wallet_candidate_audit": read_json(WALLET_CANDIDATE_AUDIT_FILE, {}),
        "wallet_candidate_quality_report": read_json(WALLET_CANDIDATE_QUALITY_REPORT_FILE, {}),
        "wallet_candidate_quality_review": read_json(WALLET_CANDIDATE_QUALITY_REVIEW_FILE, {}),
        "wallet_candidate_evidence_plan": read_json(WALLET_CANDIDATE_EVIDENCE_PLAN_FILE, {}),
        "wallet_candidate_backfill_targets": read_json(WALLET_CANDIDATE_BACKFILL_TARGETS_FILE, {}),
        "wallet_candidate_collection_plan": read_json(WALLET_CANDIDATE_COLLECTION_PLAN_FILE, {}),
        "wallet_candidate_collection_batch": read_json(WALLET_CANDIDATE_COLLECTION_BATCH_FILE, {}),
        "wallet_candidate_blocker_reducer": read_json(WALLET_CANDIDATE_BLOCKER_REDUCER_FILE, {}),
        "wallet_candidate_context_recovery": read_json(WALLET_CANDIDATE_CONTEXT_RECOVERY_FILE, {}),
        "wallet_candidate_context_recovery_runner": read_json(WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_FILE, {}),
        "wallet_candidate_context_recovery_closeout": read_json(WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_FILE, {}),
        "wallet_history_backfill": read_json(WALLET_HISTORY_BACKFILL_REPORT_FILE, {}),
        "wallet_evidence_enrichment": read_json(WALLET_EVIDENCE_ENRICHMENT_REPORT_FILE, {}),
        "wallet_missing_market_context": read_json(WALLET_MISSING_MARKET_CONTEXT_REPORT_FILE, {}),
        "wallet_evidence_readiness": read_json(WALLET_EVIDENCE_READINESS_REPORT_FILE, {}),
        "wallet_evidence_scorecard": read_json(WALLET_EVIDENCE_SCORECARD_REPORT_FILE, {}),
        "evidence_layer_completion": read_json(EVIDENCE_LAYER_COMPLETION_REPORT_FILE, {}),
    }
    with STATE_CACHE_LOCK:
        STATE_CACHE["data"] = data
        STATE_CACHE["updated_at"] = now
    return data


def invalidate_state_cache():
    with STATE_CACHE_LOCK:
        STATE_CACHE["data"] = None
        STATE_CACHE["updated_at"] = 0


def build_health_payload():
    return {
        "status": "ok",
        "server": "MemeTraderProDesktop",
        "started_at": SERVER_STARTED_AT,
        "session_started_at": SERVER_STARTED_AT,
        "process_id": os.getpid(),
        "uptime_seconds": max(0, time.time() - SERVER_STARTED_AT),
        "repo_path": str(ROOT),
        "bind_default": "127.0.0.1",
        "mode": "EXECUTION_LOCKED",
        "read_routes": True,
        "metadata_mutations_enabled": True,
        "metadata_mutations_require_token": bool(DESKTOP_API_TOKEN),
        "execution_mutations_enabled": False,
        "live_execution_locked": True,
    }


def cached_provider_health():
    load_desktop_env()
    cached = PROVIDER_HEALTH_CACHE.get("payload")
    updated_at = safe_float(PROVIDER_HEALTH_CACHE.get("updated_at"), 0)
    if cached and time.time() - updated_at <= PROVIDER_HEALTH_TTL_SECONDS:
        return cached

    payload = check_helius_provider_health(timeout=3)
    PROVIDER_HEALTH_CACHE["payload"] = payload
    PROVIDER_HEALTH_CACHE["updated_at"] = time.time()
    return payload


def build_runtime_payload(state=None):
    state = state or read_state_files()
    runtime = state.get("runtime") or DEFAULT_STATUS.copy()
    return {
        "generated_at": time.time(),
        "runtime": summarize_runtime(runtime),
        "raw": runtime,
    }


def build_freshness_payload():
    state = read_state_files()
    return {
        "generated_at": time.time(),
        "freshness": DataFreshness().report(),
        "social": build_social_freshness_payload(
            social_state=state.get("social"),
            catalyst_state=state.get("catalysts"),
            collector_state=state.get("runtime"),
        ),
    }


def safe_sqlite_counts():
    tables = ("events", "alerts", "trades", "watchlist", "token_snapshots", "swap_ticks", "decision_records")
    counts = {table: 0 for table in tables}
    if not DB_FILE.exists():
        return counts
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        for table in tables:
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except Exception:
                counts[table] = 0
    except Exception:
        return counts
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return counts


def build_readiness_payload(state=None):
    state = state or read_state_files()
    required = [
        ("paper_trades", PAPER_TRADES_FILE),
        ("manual_watchlist", WATCHLIST_FILE),
        ("runtime_status", ROOT / "data" / "runtime_status.json"),
        ("sqlite_store", DB_FILE),
    ]
    rows = []
    for name, path in required:
        exists = path.exists()
        rows.append({
            "check": name,
            "status": "OK" if exists else "WARN",
            "detail": str(path.relative_to(ROOT)) if exists else f"{path.relative_to(ROOT)} missing",
        })
    runtime = summarize_runtime(state.get("runtime") or DEFAULT_STATUS.copy())
    for component in runtime["components"]:
        status = "OK" if component["fresh"] else ("FAIL" if component["name"] in CRITICAL_COMPONENTS else "WARN")
        rows.append({
            "check": f"runtime_{component['name']}",
            "status": status,
            "detail": component.get("detail") or ("fresh" if component["fresh"] else "stale or missing"),
        })
    counts = {
        "OK": len([row for row in rows if row["status"] == "OK"]),
        "WARN": len([row for row in rows if row["status"] == "WARN"]),
        "FAIL": len([row for row in rows if row["status"] == "FAIL"]),
    }
    return {
        "generated_at": time.time(),
        "overall": "FAIL" if counts["FAIL"] else ("WARN" if counts["WARN"] else "OK"),
        "counts": counts,
        "rows": rows,
        "sqlite_counts": safe_sqlite_counts(),
    }


def summarize_runtime(runtime):
    scanner_item = runtime.get("scanner", {}) if isinstance(runtime, dict) else {}
    scanner_age = age_seconds(scanner_item.get("updated_at")) if isinstance(scanner_item, dict) else None
    scanner_fresh = scanner_age is not None and scanner_age <= FRESH_SECONDS
    components = []
    stale = []
    for name in ("bot", "websocket", "scanner", "market", "quotes", "watchdog", "open_position_monitor", "wallet_discovery", "market_radar"):
        item = runtime.get(name, {}) if isinstance(runtime, dict) else {}
        item_age = age_seconds(item.get("updated_at")) if isinstance(item, dict) else None
        state = item.get("state") or item.get("status") or "unknown" if isinstance(item, dict) else "unknown"
        fresh_seconds = runtime_fresh_seconds(item)
        fresh = item_age is not None and item_age <= fresh_seconds
        detail = runtime_component_detail(item, state, fresh)
        if name == "quotes":
            fresh, state, detail = quote_runtime_health(item, item_age, fresh)
        if name == "websocket" and not fresh and scanner_fresh and item.get("subscribed_wallets"):
            fresh = True
            state = "subscribed"
            item_age = scanner_age
            detail = "scanner heartbeat fresh; websocket subscription active"
        if name == "scanner" and scanner_fresh:
            feed_age = age_seconds(item.get("last_swap_tick_at"))
            feed_fresh_seconds = safe_float(item.get("wallet_feed_fresh_seconds"), 300)
            if feed_age is not None and feed_fresh_seconds > 0 and feed_age > feed_fresh_seconds:
                if int(item.get("wallet_events", 0) or 0) > 0:
                    state = "wallet_feed_quiet"
                    detail = f"scanner events fresh; route-backed swap ticks quiet for {int(feed_age)}s"
                else:
                    fresh = False
                    state = "wallet_feed_stale"
                    detail = f"wallet feed stale; last swap tick {int(feed_age)}s old"
        row = {
            "name": name,
            "state": state,
            "age_seconds": item_age,
            "fresh": fresh,
            "detail": detail,
        }
        components.append(row)
        if name in CRITICAL_COMPONENTS and not fresh:
            stale.append(name)
    return {
        "state": "online" if not stale else "stale",
        "stale_components": stale,
        "components": components,
    }


def runtime_component_detail(item, state, fresh):
    item = item if isinstance(item, dict) else {}
    if item.get("detail"):
        return item.get("detail")
    state = str(state or "").lower()
    last_error = item.get("last_error") or item.get("last_rpc_error")
    if last_error and (not fresh or "error" in state or "reconnect" in state or "closed" in state):
        return last_error
    return ""


def trade_count(paper, key):
    rows = paper.get(key, []) if isinstance(paper, dict) else []
    return len(rows) if isinstance(rows, list) else 0


def reason_counts(rows, *keys):
    counts = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        reason = None
        for key in keys:
            if row.get(key):
                reason = str(row.get(key))
                break
        reason = reason or "unrecorded"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def wallet_label_exposure_for_trades(trades, behavior):
    behavior = behavior if isinstance(behavior, dict) else {}
    behavior_wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    counts = {}
    seen = set()
    for trade in trades or []:
        if not isinstance(trade, dict):
            continue
        for wallet in listify(trade.get("wallets")):
            if not wallet:
                continue
            key = (trade_mint(trade), wallet)
            if key in seen:
                continue
            seen.add(key)
            row = behavior_wallets.get(str(wallet)) if isinstance(behavior_wallets.get(str(wallet)), dict) else {}
            for label in row.get("labels") if isinstance(row.get("labels"), list) else []:
                label = str(label)
                counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def paper_trade_lane(trade):
    if not isinstance(trade, dict):
        return "main"
    lane = trade.get("paper_lane")
    if not lane and isinstance(trade.get("signal_metadata"), dict):
        lane = trade["signal_metadata"].get("paper_lane")
    if trade.get("exploration") is True:
        lane = lane or "exploration"
    lane = str(lane or "main").lower()
    if lane in {"exploration", "market_radar"}:
        return lane
    return "main"


def trade_has_decision_id(trade):
    trade = trade if isinstance(trade, dict) else {}
    meta = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    did = trade.get("decision_id") or meta.get("decision_id")
    return bool(str(did or "").strip())


def _pct_cap_fraction(numerator, denominator):
    if not denominator:
        return 0.0
    return min(100.0, round(100.0 * numerator / denominator, 1))


def lane_sample_progress_row(closed_count, minimum_closed, recommended_closed):
    minimum_closed = int(minimum_closed) if minimum_closed else 0
    recommended_closed = int(recommended_closed) if recommended_closed else 0
    closed_count = int(closed_count) if closed_count else 0
    return {
        "closed_trades": closed_count,
        "to_minimum_pct": _pct_cap_fraction(closed_count, minimum_closed),
        "to_recommended_pct": _pct_cap_fraction(closed_count, recommended_closed),
        "meets_minimum": closed_count >= minimum_closed,
        "meets_recommended": closed_count >= recommended_closed,
    }


def paper_decision_lineage_by_lane(paper):
    """Counts open/closed/failed rows with canonical decision_id lineage."""
    paper = paper if isinstance(paper, dict) else {}
    lanes = {}
    for lane in ("all", "main", "market_radar", "exploration"):
        lanes[lane] = {"total": 0, "with_decision_id": 0}
    for bucket in ("open_trades", "closed_trades", "failed_trades"):
        rows = paper.get(bucket) if isinstance(paper.get(bucket), list) else []
        for trade in rows:
            if not isinstance(trade, dict):
                continue
            lane_key = paper_trade_lane(trade)
            if lane_key not in lanes:
                lane_key = "main"
            has_id = trade_has_decision_id(trade)
            for key in ("all", lane_key):
                lanes[key]["total"] += 1
                if has_id:
                    lanes[key]["with_decision_id"] += 1
    enriched = {}
    for key, row in lanes.items():
        total = row["total"]
        with_id = row["with_decision_id"]
        cov = 100.0 if total <= 0 else min(100.0, round(100.0 * with_id / total, 1))
        enriched[key] = {
            "total": total,
            "with_decision_id": with_id,
            "missing_decision_id": max(0, total - with_id),
            "coverage_pct": cov,
        }
    return enriched


def filter_paper_by_lane(paper, lane):
    return filter_paper_by_lanes(paper, {lane})


def filter_paper_by_lanes(paper, lanes):
    paper = paper if isinstance(paper, dict) else {}
    lanes = {str(lane).lower() for lane in (lanes or [])}
    filtered = {"open_trades": [], "closed_trades": [], "failed_trades": []}
    for key in filtered:
        rows = paper.get(key) if isinstance(paper.get(key), list) else []
        filtered[key] = [row for row in rows if paper_trade_lane(row) in lanes]
    return filtered


def build_paper_review_payload(state=None):
    state = state or read_state_files()
    paper = state.get("paper") if isinstance(state.get("paper"), dict) else {}
    behavior = state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {}
    closed = paper.get("closed_trades") if isinstance(paper.get("closed_trades"), list) else []
    failed = paper.get("failed_trades") if isinstance(paper.get("failed_trades"), list) else []
    open_trades = paper.get("open_trades") if isinstance(paper.get("open_trades"), list) else []
    analyzer = PerformanceAnalyzer()
    metrics = analyzer.analyze(paper)
    lane_metrics = {
        "main": analyzer.analyze(filter_paper_by_lane(paper, "main")),
        "co_main": analyzer.analyze(filter_paper_by_lanes(paper, {"main", "market_radar"})),
        "exploration": analyzer.analyze(filter_paper_by_lane(paper, "exploration")),
        "market_radar": analyzer.analyze(filter_paper_by_lane(paper, "market_radar")),
    }
    minimum_closed = 50
    recommended_closed = 100
    wallet_main_meaningful_test_ready = lane_metrics["main"]["closed_trades"] >= minimum_closed
    co_main_meaningful_test_ready = lane_metrics["co_main"]["closed_trades"] >= minimum_closed
    exploration_sample_ready = lane_metrics["exploration"]["closed_trades"] >= minimum_closed
    market_radar_main_meaningful_test_ready = lane_metrics["market_radar"]["closed_trades"] >= minimum_closed
    market_radar_sample_ready = market_radar_main_meaningful_test_ready
    readiness_gaps = []
    co_main_metrics = lane_metrics["co_main"]
    if not co_main_meaningful_test_ready:
        readiness_gaps.append(f"Need at least {minimum_closed} closed co-main paper trades across wallet-main and Market Radar before this is a meaningful test.")
    if co_main_metrics["failed_trades"] and co_main_metrics["closed_trades"] and co_main_metrics["failed_trades"] / max(1, co_main_metrics["closed_trades"]) > 0.25:
        readiness_gaps.append("Failed trade rate is high enough to review quote/routing reliability.")
    if co_main_metrics["profit_factor"] is None:
        readiness_gaps.append("Profit factor is not stable yet because there are not enough losses/wins to compare.")
    if co_main_metrics["win_rate"] < 35 and co_main_metrics["closed_trades"] >= 10:
        readiness_gaps.append("Win rate is below 35%; review entry quality before judging profitability.")

    lineage = paper_decision_lineage_by_lane(paper)
    lineage_all = lineage.get("all") or {}
    if lineage_all.get("total", 0) >= 5 and lineage_all.get("coverage_pct", 100) < 100:
        readiness_gaps.append(
            "Paper lineage: {:.0f}% of paper rows ({}/{}) carry decision_id. "
            "Open the bot once to hydrate JSON lineage or rebuild decisions from SQLite for full Replay joins.".format(
                lineage_all.get("coverage_pct", 0),
                lineage_all.get("with_decision_id", 0),
                lineage_all.get("total", 0),
            )
        )

    sample_progress = {
        "minimum_closed_trades": minimum_closed,
        "recommended_closed_trades": recommended_closed,
        "lanes": {
            "wallet_main": lane_sample_progress_row(
                lane_metrics["main"]["closed_trades"], minimum_closed, recommended_closed,
            ),
            "market_radar": lane_sample_progress_row(
                lane_metrics["market_radar"]["closed_trades"], minimum_closed, recommended_closed,
            ),
            "exploration": lane_sample_progress_row(
                lane_metrics["exploration"]["closed_trades"], minimum_closed, recommended_closed,
            ),
            "co_main": lane_sample_progress_row(
                lane_metrics["co_main"]["closed_trades"], minimum_closed, recommended_closed,
            ),
        },
    }

    all_terminal = closed + failed
    return {
        "generated_at": time.time(),
        "mode": "PAPER_REVIEW_ONLY",
        "live_execution_locked": True,
        "meaningful_test_ready": co_main_meaningful_test_ready and not readiness_gaps,
        "main_meaningful_test_ready": co_main_meaningful_test_ready and not readiness_gaps,
        "co_main_meaningful_test_ready": co_main_meaningful_test_ready and not readiness_gaps,
        "wallet_main_meaningful_test_ready": wallet_main_meaningful_test_ready,
        "market_radar_main_meaningful_test_ready": market_radar_main_meaningful_test_ready,
        "exploration_sample_ready": exploration_sample_ready,
        "market_radar_sample_ready": market_radar_sample_ready,
        "minimum_closed_trades": minimum_closed,
        "recommended_closed_trades": recommended_closed,
        "sample_progress": sample_progress,
        "decision_lineage": lineage,
        "metrics": metrics,
        "lane_metrics": lane_metrics,
        "decision_lane_report": build_decision_lane_report_payload(state=state),
        "open_trades": len(open_trades),
        "readiness_gaps": readiness_gaps,
        "exit_reasons": reason_counts(closed, "exit_reason", "close_reason", "reason"),
        "failure_reasons": reason_counts(failed, "failure_reason", "reason"),
        "entry_reasons": reason_counts(closed, "entry_reason", "reason"),
        "wallet_label_exposure": wallet_label_exposure_for_trades(all_terminal, behavior),
        "next_review_actions": [
            "Let co-main paper mode keep running until wallet-main plus Market Radar have at least 50 closed trades.",
            "Compare wallet-main and Market Radar separately before changing shared thresholds.",
            "Review worst trades by entry reason, wallet label, and exit reason.",
            "Tighten confirmation thresholds only after enough samples show repeated weak patterns.",
        ],
    }


def trade_pnl(row):
    row = row if isinstance(row, dict) else {}
    return safe_float(first_present(row.get("total_pnl"), row.get("pnl"), row.get("realized_pnl"), row.get("unrealized_pnl")), 0)


def trade_pnl_pct(row):
    row = row if isinstance(row, dict) else {}
    value = first_present(row.get("total_pnl_pct"), row.get("pnl_pct"))
    return safe_float(value, None)


def trade_entry_market_cap(row):
    row = row if isinstance(row, dict) else {}
    return safe_float(first_present(row.get("entry_market_cap"), row.get("market_cap_at_entry")), None)


def trade_exit_market_cap(row):
    row = row if isinstance(row, dict) else {}
    return safe_float(first_present(row.get("exit_market_cap"), row.get("market_cap_at_exit"), row.get("current_market_cap"), row.get("market_cap")), None)


def trade_entry_liquidity(row):
    row = row if isinstance(row, dict) else {}
    return safe_float(first_present(row.get("entry_liquidity_usd"), row.get("liquidity_usd"), row.get("current_liquidity_usd")), None)


def signal_meta(row):
    row = row if isinstance(row, dict) else {}
    return row.get("signal_metadata") if isinstance(row.get("signal_metadata"), dict) else {}


def signal_reasons(row):
    meta = signal_meta(row)
    reasons = []
    for key in ("score_reasons", "confirmation_reasons", "risk_warnings"):
        values = meta.get(key)
        if isinstance(values, list):
            reasons.extend(str(value) for value in values)
    for key in ("entry_reason", "reason"):
        if row.get(key):
            reasons.append(str(row.get(key)))
    return reasons


def has_trait(row, trait):
    reasons = " | ".join(signal_reasons(row)).lower()
    meta = signal_meta(row)
    if trait == "elite wallet":
        return "elite live wallet" in reasons or "high average live wallet quality" in reasons
    if trait == "confirmation window":
        return "confirmation:" in reasons and "window" in reasons
    if trait == "strong liquidity":
        return safe_float(trade_entry_liquidity(row), 0) >= 100_000 or "excellent liquidity" in reasons
    if trait == "low risk":
        return str(meta.get("risk_label") or row.get("risk_label") or "").upper() == "LOW_RISK" or "low_risk" in reasons
    if trait == "quote passed":
        buy = meta.get("buy_quote_analysis") if isinstance(meta.get("buy_quote_analysis"), dict) else {}
        sell = meta.get("sell_quote_analysis") if isinstance(meta.get("sell_quote_analysis"), dict) else {}
        return bool(buy.get("pass")) and bool(sell.get("pass")) or "quote_ok" in reasons
    if trait == "score cushion":
        score = safe_float(meta.get("score"), 0)
        threshold = safe_float(meta.get("threshold"), 0)
        return bool(score and threshold and score >= threshold + 10)
    if trait == "partial take-profit":
        sells = row.get("sells") if isinstance(row.get("sells"), list) else []
        return any("take_profit" in str(sell.get("reason") if isinstance(sell, dict) else sell).lower() for sell in sells)
    return False


def summarize_pattern_trade(row):
    row = row if isinstance(row, dict) else {}
    return {
        "mint": trade_mint(row),
        "symbol": row.get("symbol") or row.get("name") or trade_mint(row),
        "pnl": trade_pnl(row),
        "pnl_pct": trade_pnl_pct(row),
        "entry_market_cap": trade_entry_market_cap(row),
        "exit_market_cap": trade_exit_market_cap(row),
        "entry_liquidity": trade_entry_liquidity(row),
        "entry_reason": row.get("entry_reason") or row.get("reason"),
        "exit_reason": row.get("exit_reason") or row.get("close_reason"),
        "wallets": listify(row.get("wallets"))[:8],
    }


def build_winner_pattern_payload(state=None):
    state = state or read_state_files()
    paper = state.get("paper") if isinstance(state.get("paper"), dict) else {}
    closed = [row for row in paper.get("closed_trades", []) if isinstance(row, dict)]
    winners = [row for row in closed if trade_pnl(row) > 0]
    big_winners = [row for row in winners if trade_pnl(row) >= 100 or safe_float(trade_pnl_pct(row), 0) >= 100]
    losers = [row for row in closed if trade_pnl(row) <= 0]
    analysis_set = big_winners or winners
    traits = ["elite wallet", "confirmation window", "strong liquidity", "low risk", "quote passed", "score cushion", "partial take-profit"]
    repeatable_traits = []
    trait_counts = {}
    for trait in traits:
        count = sum(1 for row in analysis_set if has_trait(row, trait))
        trait_counts[trait] = count
        if analysis_set and count / max(1, len(analysis_set)) >= 0.5:
            repeatable_traits.append(trait)

    wallet_totals = {}
    for row in winners:
        for wallet in listify(row.get("wallets")):
            wallet = str(wallet)
            item = wallet_totals.setdefault(wallet, {"wallet": wallet, "wins": 0, "pnl": 0.0, "best_pnl": 0.0})
            pnl = trade_pnl(row)
            item["wins"] += 1
            item["pnl"] += pnl
            item["best_pnl"] = max(item["best_pnl"], pnl)
    wallet_leaders = sorted(wallet_totals.values(), key=lambda item: (item["pnl"], item["wins"]), reverse=True)[:8]

    return {
        "generated_at": time.time(),
        "mode": "WINNER_PATTERN_REVIEW_ONLY",
        "live_execution_locked": True,
        "winner_count": len(winners),
        "big_winner_count": len(big_winners),
        "loser_count": len(losers),
        "sample_warning": "Early read only; tune after at least 50 closed main-strategy trades." if len(closed) < 50 else "",
        "repeatable_traits": repeatable_traits,
        "trait_counts": trait_counts,
        "wallet_leaders": wallet_leaders,
        "top_winners": [summarize_pattern_trade(row) for row in sorted(winners, key=trade_pnl, reverse=True)[:8]],
        "worst_losers": [summarize_pattern_trade(row) for row in sorted(losers, key=trade_pnl)[:8]],
        "recommended_actions": [
            "Prefer winner traits that also appear less often in losers.",
            "Do not loosen live execution from this review; use it for paper-threshold tuning only.",
            "Keep partial take-profit behavior visible because large winners can still finish with a stop exit.",
        ],
    }
def build_overview_payload(state=None):
    state = state or read_state_files()
    paper = state["paper"]
    watchlist = state["watchlist"] if isinstance(state["watchlist"], list) else []
    social = state["social"] if isinstance(state["social"], dict) else {"events": []}
    catalysts = state["catalysts"] if isinstance(state["catalysts"], dict) else {"cards": []}
    runtime = summarize_runtime(state.get("runtime") or DEFAULT_STATUS.copy())
    settings = state["settings"] if isinstance(state["settings"], dict) else {}

    return {
        "generated_at": time.time(),
        "mode": "PAPER_ONLY",
        "live_execution_locked": True,
        "runtime": runtime,
        "counts": {
            "open_trades": trade_count(paper, "open_trades"),
            "closed_trades": trade_count(paper, "closed_trades"),
            "failed_trades": trade_count(paper, "failed_trades"),
            "protected_positions": len(watchlist),
            "social_events": len(social.get("events", [])) if isinstance(social.get("events"), list) else 0,
            "catalyst_cards": len(catalysts.get("cards", [])) if isinstance(catalysts.get("cards"), list) else 0,
        },
        "settings": {
            "strategy_mode": settings.get("strategy_mode") or settings.get("mode") or "unknown",
            "confirmation_mode": settings.get("confirmation_mode"),
            "paper_trading": settings.get("paper_trading", True),
        },
        "wallet_confidence": build_operator_wallet_confidence(state),
    }


def build_operator_wallet_confidence(state=None, recent_limit=80):
    state = state or read_state_files()
    performance = state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {}
    behavior = state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {}
    paper = state.get("paper") if isinstance(state.get("paper"), dict) else {}
    wallet_records = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    signals = performance.get("signals") if isinstance(performance.get("signals"), list) else []
    recent_signals = signals[:recent_limit]
    wallets = set()
    tokens = set()

    for signal in recent_signals:
        if not isinstance(signal, dict):
            continue
        if signal.get("mint"):
            tokens.add(signal.get("mint"))
        wallets.update(str(wallet) for wallet in listify(signal.get("wallets")) if wallet)

    open_trade_wallets = set()
    open_trades = paper.get("open_trades") if isinstance(paper.get("open_trades"), list) else []
    for trade in open_trades:
        if not isinstance(trade, dict):
            continue
        trade_wallets = {str(wallet) for wallet in listify(trade.get("wallets")) if wallet}
        wallets.update(trade_wallets)
        open_trade_wallets.update(trade_wallets)
        mint = trade_mint(trade)
        if mint:
            tokens.add(mint)

    behavior_wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    rows = []
    label_counts = {}
    for wallet in sorted(wallets):
        record = wallet_records.get(wallet) if isinstance(wallet_records.get(wallet), dict) else {}
        behavior_row = behavior_wallets.get(wallet) if isinstance(behavior_wallets.get(wallet), dict) else {}
        labels = behavior_row.get("labels") if isinstance(behavior_row.get("labels"), list) else []
        for label in labels:
            label = str(label)
            label_counts[label] = label_counts.get(label, 0) + 1
        rows.append({
            "wallet": wallet,
            "score": safe_float(record.get("score"), 50),
            "paper_entries": int(safe_float(record.get("paper_entries"), 0) or 0),
            "avg_pnl": safe_float(record.get("avg_pnl"), 0),
            "labels": labels,
            "postmortem": behavior_row.get("postmortem") if isinstance(behavior_row.get("postmortem"), dict) else {},
            "open_trade_driver": wallet in open_trade_wallets,
        })

    proven = [
        row for row in rows
        if "paper-profitable" in row.get("labels", []) or (row["paper_entries"] >= 3 and row["avg_pnl"] > 0)
    ]
    traps = [
        row for row in rows
        if any(label in row.get("labels", []) for label in ("follower-trap", "copy-bait"))
    ]
    rows.sort(key=lambda row: (row["open_trade_driver"], row["score"], row["paper_entries"]), reverse=True)
    return {
        "wallet_count": len(rows),
        "signal_count": len(recent_signals),
        "token_count": len(tokens),
        "proven_wallets": len(proven),
        "trap_wallets": len(traps),
        "open_trade_wallets": len(open_trade_wallets),
        "avg_score": round(sum(row["score"] for row in rows) / len(rows), 2) if rows else 0,
        "top_labels": dict(sorted(label_counts.items(), key=lambda item: item[1], reverse=True)[:8]),
        "live_execution_locked": True,
        "wallets": rows[:8],
    }


def build_positions_payload(state=None):
    state = state or read_state_files()
    positions = build_position_rows(state["paper"], state["watchlist"])
    return {
        "generated_at": time.time(),
        "live_execution_locked": True,
        "positions": [compact_position(row) for row in positions],
    }


def build_position_detail_payload(mint):
    state = read_state_files()
    raw_positions = build_position_rows(state["paper"], state["watchlist"])
    selected_raw = next((position for position in raw_positions if position.get("mint") == mint), None)
    selected = compact_position(selected_raw) if selected_raw else None
    snapshots = fetch_snapshot_rows(mint=mint, limit=50)
    position_source, position_source_detail = position_detail_source(selected_raw)
    mixed_market_fields = bool(selected_raw and snapshots)
    return {
        "generated_at": time.time(),
        "mint": mint,
        "position_source": position_source,
        "position_source_detail": position_source_detail,
        "snapshot_source": "sqlite_token_snapshots",
        "snapshot_source_detail": f"{DB_FILE.relative_to(ROOT)}:token_snapshots",
        "source_contract": {
            "position": position_source or "paper_trades_json_or_manual_watchlist_json",
            "snapshots": "sqlite_token_snapshots",
            "social": "social_state_json",
            "catalysts": "catalyst_cards_json",
            "wallet_stats": "wallet_performance_json_and_wallet_behavior_json",
            "wallet_context": "wallet_performance_json_and_wallet_behavior_json_and_paper_trades_json",
        },
        "mixed_market_fields": mixed_market_fields,
        "mixed_market_fields_note": (
            "position price/market/liquidity can come from JSON position state while latest_snapshot "
            "comes from SQLite token_snapshots"
            if mixed_market_fields else
            "selected-position detail declares separate JSON and SQLite sources; no mixed market fields are present in this response"
        ),
        "position": selected,
        "latest_snapshot": snapshots[-1] if snapshots else None,
        "snapshot_count": len(snapshots),
        "trend": build_snapshot_trend(snapshots),
        "protection": build_protection_summary(selected_raw),
        "signals": build_signal_summary(mint, state.get("social"), state.get("catalysts")),
        "wallet_context": build_wallet_context_for_mint(mint, state),
        "live_execution_locked": True,
    }


def position_detail_source(position):
    source = position.get("source") if isinstance(position, dict) else None
    if source == "paper_trade":
        return "paper_trades_json", str(PAPER_TRADES_FILE.relative_to(ROOT))
    if source == "manual_watchlist":
        return "manual_watchlist_json", str(WATCHLIST_FILE.relative_to(ROOT))
    return None, None


def compact_position(row):
    raw = row.get("raw", {}) if isinstance(row, dict) else {}
    prepared_exit = raw.get("prepared_exit") if isinstance(raw, dict) else {}
    holder_metrics = raw.get("holder_concentration_metrics") if isinstance(raw, dict) else {}
    return {
        "source": row.get("source"),
        "mint": row.get("mint"),
        "label": row.get("label") or (row.get("mint") or "")[:8],
        "status": row.get("status"),
        "price": first_present(row.get("current_price"), raw.get("current_price")),
        "market_cap": first_present(row.get("current_market_cap"), raw.get("market_cap")),
        "liquidity": first_present(row.get("liquidity"), raw.get("current_liquidity")),
        "risk_level": row.get("risk_level") or raw.get("risk_level") or raw.get("alert_level"),
        "alert_level": row.get("alert_level") or raw.get("alert_level"),
        "pnl_pct": first_present(raw.get("total_pnl_pct"), raw.get("pnl_pct")),
        "quote_status": prepared_exit.get("quote_status") if isinstance(prepared_exit, dict) else None,
        "holder_count": first_present(row.get("holder_count"), holder_metrics.get("holder_count")) if isinstance(holder_metrics, dict) else row.get("holder_count"),
        "top_10_holder_pct": holder_metrics.get("top_10_pct") if isinstance(holder_metrics, dict) else None,
        "live_action_allowed": False,
    }


def listify(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def wallets_for_mint_from_paper(mint, paper):
    wallets = set()
    paper = paper if isinstance(paper, dict) else {}
    for source in ("open_trades", "closed_trades", "failed_trades"):
        rows = paper.get(source) if isinstance(paper.get(source), list) else []
        for trade in rows:
            if isinstance(trade, dict) and trade_mint(trade) == mint:
                wallets.update(str(wallet) for wallet in listify(trade.get("wallets")) if wallet)
    return wallets


def wallet_behavior_row(behavior, wallet):
    behavior = behavior if isinstance(behavior, dict) else {}
    wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    return wallets.get(wallet) if isinstance(wallets.get(wallet), dict) else {}


def build_wallet_context_for_mint(mint, state=None, limit=8):
    state = state or read_state_files()
    performance = state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {}
    behavior = state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {}
    tracked = state.get("tracked_wallets") if isinstance(state.get("tracked_wallets"), list) else []
    labels = tracked_wallet_labels(tracked)
    wallet_records = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    signals = performance.get("signals") if isinstance(performance.get("signals"), list) else []
    matched_signals = [signal for signal in signals if isinstance(signal, dict) and signal.get("mint") == mint]
    paper = canonical_trade_state(state)
    wallets = wallets_for_mint_from_paper(mint, paper)

    for signal in matched_signals:
        wallets.update(str(wallet) for wallet in listify(signal.get("wallets")) if wallet)

    rows = []
    for wallet in sorted(wallets):
        row = wallet_row(wallet, wallet_records.get(wallet, {}), labels)
        behavior_row = wallet_behavior_row(behavior, wallet)
        row["labels"] = behavior_row.get("labels") if isinstance(behavior_row.get("labels"), list) else []
        row["rolling"] = behavior_row.get("rolling") if isinstance(behavior_row.get("rolling"), dict) else {}
        row["postmortem"] = behavior_row.get("postmortem") if isinstance(behavior_row.get("postmortem"), dict) else {}
        row["matched_signal_count"] = len([
            signal for signal in matched_signals
            if wallet in listify(signal.get("wallets"))
        ])
        rows.append(row)

    rows.sort(key=lambda row: (
        row.get("matched_signal_count", 0),
        row.get("score", 0),
        row.get("paper_entries", 0),
    ), reverse=True)
    scores = [safe_float(row.get("score"), 0) for row in rows]
    proven = [
        row for row in rows
        if "paper-profitable" in row.get("labels", []) or safe_float(row.get("paper_entries"), 0) >= 3 and safe_float(row.get("avg_pnl"), 0) > 0
    ]
    traps = [
        row for row in rows
        if any(label in row.get("labels", []) for label in ("follower-trap", "copy-bait"))
    ]
    return {
        "wallet_count": len(rows),
        "matched_signals": len(matched_signals),
        "proven_wallets": len(proven),
        "trap_wallets": len(traps),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "live_execution_locked": True,
        "trade_source": paper.get("source"),
        "wallets": rows[:limit],
    }


def build_protection_summary(row):
    row = row or {}
    raw = row.get("raw", {}) if isinstance(row, dict) else {}
    prepared_exit = raw.get("prepared_exit") if isinstance(raw, dict) else {}
    reasons = []
    if isinstance(prepared_exit, dict):
        reasons.extend(listify(prepared_exit.get("reasons")))
    reasons.extend(listify(raw.get("token_mechanics_reasons") if isinstance(raw, dict) else None))
    if isinstance(raw, dict) and raw.get("reason"):
        reasons.append(raw.get("reason"))
    return {
        "state": row.get("status") or raw.get("status") or "UNKNOWN",
        "risk_level": row.get("risk_level") or raw.get("risk_level") or raw.get("alert_level") or "UNKNOWN",
        "alert_level": row.get("alert_level") or raw.get("alert_level"),
        "reason": raw.get("reason") if isinstance(raw, dict) else None,
        "quote_status": prepared_exit.get("quote_status") if isinstance(prepared_exit, dict) else None,
        "quote_reason": prepared_exit.get("quote_reason") if isinstance(prepared_exit, dict) else None,
        "suggested_sell_pct": prepared_exit.get("suggested_sell_pct") if isinstance(prepared_exit, dict) else None,
        "urgency": prepared_exit.get("urgency") if isinstance(prepared_exit, dict) else None,
        "token_amount_reason": prepared_exit.get("token_amount_reason") if isinstance(prepared_exit, dict) else None,
        "token_amount": raw.get("token_amount") if isinstance(raw, dict) else None,
        "token_amount_raw": raw.get("token_amount_raw") if isinstance(raw, dict) else None,
        "token_amount_source": raw.get("token_amount_source") if isinstance(raw, dict) else None,
        "token_amount_updated_at": raw.get("token_amount_updated_at") if isinstance(raw, dict) else None,
        "token_decimals": (raw.get("token_decimals") or raw.get("decimals")) if isinstance(raw, dict) else None,
        "test_amount": bool(raw.get("test_amount") or prepared_exit.get("test_amount")) if isinstance(raw, dict) and isinstance(prepared_exit, dict) else False,
        "amount_safety_note": (raw.get("amount_safety_note") or prepared_exit.get("amount_safety_note")) if isinstance(raw, dict) and isinstance(prepared_exit, dict) else None,
        "wallet_balance_status": raw.get("wallet_balance_status") if isinstance(raw, dict) else None,
        "wallet_balance_accounts": raw.get("wallet_balance_accounts") if isinstance(raw, dict) else None,
        "wallet_balance_reason": raw.get("wallet_balance_reason") if isinstance(raw, dict) else None,
        "token_standard": raw.get("token_standard") if isinstance(raw, dict) else None,
        "token_extensions": listify(raw.get("token_extensions") if isinstance(raw, dict) else None),
        "token_mechanics_risk": raw.get("token_mechanics_risk") if isinstance(raw, dict) else None,
        "price_from_entry_pct": raw.get("price_from_entry_pct") if isinstance(raw, dict) else None,
        "price_from_peak_pct": raw.get("price_from_peak_pct") if isinstance(raw, dict) else None,
        "liquidity_from_entry_pct": raw.get("liquidity_from_entry_pct") if isinstance(raw, dict) else None,
        "liquidity_from_peak_pct": raw.get("liquidity_from_peak_pct") if isinstance(raw, dict) else None,
        "live_action_allowed": False,
        "auto_sell_enabled": False,
        "auto_sell_requested": bool(raw.get("requested_auto_sell")) if isinstance(raw, dict) else False,
        "reasons": [str(reason) for reason in reasons if reason],
    }


def social_rows(social_state):
    if not isinstance(social_state, dict):
        return []
    rows = social_state.get("events")
    if not isinstance(rows, list):
        rows = social_state.get("signals")
    return rows if isinstance(rows, list) else []


def catalyst_rows(catalyst_state):
    if not isinstance(catalyst_state, dict):
        return []
    rows = catalyst_state.get("cards")
    return rows if isinstance(rows, list) else []


def summarize_social_payload(social_state, limit=100):
    rows = social_rows(social_state)
    return {
        "generated_at": time.time(),
        "source": "social_state_json",
        "source_detail": str(SOCIAL_STATE_FILE.relative_to(ROOT)),
        "source_contract": {
            "social": "social_state_json",
            "catalysts": "catalyst_cards_json",
            "decision_social_evidence": "sqlite_decision_records_embedded_evidence",
        },
        "count": len(rows),
        "items": rows[:limit],
        "freshness": build_social_freshness_payload(social_state=social_state),
        "live_execution_locked": True,
    }


def numeric_timestamp(*values):
    for value in values:
        parsed = safe_float(value, None)
        if parsed and parsed > 1000000000:
            return parsed
    return None


def row_timestamp(row):
    if not isinstance(row, dict):
        return None
    return numeric_timestamp(
        row.get("last_success_at"),
        row.get("updated_at"),
        row.get("created_at"),
        row.get("discovered_at"),
        row.get("timestamp"),
        row.get("time"),
    )


def latest_row_timestamp(rows):
    timestamps = [row_timestamp(row) for row in rows if isinstance(row, dict)]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(timestamps) if timestamps else None


def social_freshness_status(last_timestamp, fresh_seconds, empty=False, enabled=True, error=None):
    if not enabled:
        return "DISABLED", None
    if error and last_timestamp is None:
        return "ERROR", None
    if empty or last_timestamp is None:
        return "EMPTY", None
    age = age_seconds(last_timestamp)
    if age is None:
        return "UNKNOWN", age
    if age <= fresh_seconds:
        return "FRESH", age
    if age <= fresh_seconds * 3:
        return "STALE", age
    return "OLD", age


def format_age_seconds(seconds):
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def social_source_row(
    source,
    label,
    status,
    age,
    event_count=0,
    detail="",
    last_success_at=None,
    collector_type="local",
    fresh_seconds=None,
    enabled=True,
    last_error=None,
):
    return {
        "source": source,
        "label": label,
        "status": status,
        "age_seconds": age,
        "age": format_age_seconds(age),
        "fresh_seconds": fresh_seconds,
        "event_count": int(event_count or 0),
        "enabled": enabled,
        "last_success_at": last_success_at,
        "last_error": last_error,
        "collector_type": collector_type,
        "detail": detail,
    }


def normalize_collector_rows(collector_state):
    if not isinstance(collector_state, dict):
        return []
    rows = collector_state.get("collectors")
    if rows is None and isinstance(collector_state.get("social_collectors"), (list, dict)):
        rows = collector_state.get("social_collectors")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if isinstance(rows, dict):
        return [{**value, "collector": key} for key, value in rows.items() if isinstance(value, dict)]
    return []


def build_social_freshness_payload(social_state=None, catalyst_state=None, collector_state=None):
    social_state = social_state if isinstance(social_state, dict) else read_json(SOCIAL_STATE_FILE, {"events": []})
    catalyst_state = catalyst_state if isinstance(catalyst_state, dict) else read_json(CATALYST_CARDS_FILE, {"cards": []})
    collector_state = collector_state if isinstance(collector_state, dict) else load_status()

    rows = []
    social_events = social_rows(social_state)
    social_latest = latest_row_timestamp(social_events)
    social_status, social_age = social_freshness_status(
        social_latest,
        SOCIAL_SOURCE_FRESH_SECONDS,
        empty=not bool(social_events),
    )
    rows.append(social_source_row(
        "manual_social_import",
        "Manual Social Import",
        social_status,
        social_age,
        event_count=len(social_events),
        detail="latest manual import is stale" if social_status in ("STALE", "OLD") else "local social imports",
        last_success_at=social_latest,
        collector_type="manual",
        fresh_seconds=SOCIAL_SOURCE_FRESH_SECONDS,
    ))

    catalyst_cards = catalyst_rows(catalyst_state)
    catalyst_latest = latest_row_timestamp(catalyst_cards) or numeric_timestamp(
        catalyst_state.get("generated_at"),
        catalyst_state.get("last_updated"),
        catalyst_state.get("updated_at"),
    )
    catalyst_status, catalyst_age = social_freshness_status(
        catalyst_latest,
        SOCIAL_SOURCE_FRESH_SECONDS,
        empty=not bool(catalyst_cards),
    )
    rows.append(social_source_row(
        "catalyst_cards",
        "Catalyst Cards",
        catalyst_status,
        catalyst_age,
        event_count=len(catalyst_cards),
        detail="latest catalyst cards are stale" if catalyst_status in ("STALE", "OLD") else "local catalyst cards",
        last_success_at=catalyst_latest,
        collector_type="derived",
        fresh_seconds=SOCIAL_SOURCE_FRESH_SECONDS,
    ))

    collector_rows = normalize_collector_rows(collector_state)
    if not collector_rows:
        rows.append(social_source_row(
            "automated_collectors",
            "Automated Collectors",
            "NOT_CONFIGURED",
            None,
            detail="no automated collector status file yet",
            collector_type="automation",
            enabled=False,
        ))

    for collector in collector_rows:
        name = str(collector.get("collector") or collector.get("name") or collector.get("source") or "collector").strip() or "collector"
        enabled = collector.get("enabled", True) is not False
        last_success_at = numeric_timestamp(
            collector.get("last_success_at"),
            collector.get("last_event_at"),
            collector.get("updated_at"),
        )
        last_error = str(collector.get("last_error") or "").strip()
        fresh_seconds = bounded_int(collector.get("fresh_seconds"), SOCIAL_COLLECTOR_FRESH_SECONDS, 60, 86400)
        status, age = social_freshness_status(
            last_success_at,
            fresh_seconds,
            empty=False,
            enabled=enabled,
            error=last_error,
        )
        detail_parts = []
        if not enabled:
            detail_parts.append("collector disabled")
        elif last_error:
            detail_parts.append(last_error)
        else:
            detail_parts.append("collector heartbeat")
        rows.append(social_source_row(
            name,
            str(collector.get("label") or f"{name.title()} Collector"),
            status,
            age,
            event_count=collector.get("event_count") or collector.get("events_seen") or 0,
            detail="; ".join(detail_parts),
            last_success_at=last_success_at,
            collector_type=str(collector.get("type") or "automation"),
            fresh_seconds=fresh_seconds,
            enabled=enabled,
            last_error=last_error or None,
        ))

    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    if counts.get("ERROR") or counts.get("OLD"):
        overall = "FAIL"
    elif counts.get("STALE") or counts.get("UNKNOWN") or counts.get("EMPTY") or counts.get("NOT_CONFIGURED"):
        overall = "WARN"
    else:
        overall = "OK"

    return {
        "generated_at": time.time(),
        "mode": "SOCIAL_FRESHNESS_READ_ONLY",
        "live_execution_locked": True,
        "overall": overall,
        "counts": counts,
        "rows": rows,
        "detail": "Freshness only. This does not trigger trades or bypass decision gates.",
    }


def normalize_social_keywords(value):
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("\n", ",").split(",")
    keywords = []
    seen = set()
    for item in raw:
        keyword = str(item or "").strip().lower()
        if not keyword or keyword in seen:
            continue
        keywords.append(keyword[:48])
        seen.add(keyword)
        if len(keywords) >= 12:
            break
    return keywords


def normalize_social_mints(payload):
    rows = []
    if payload.get("mint") or payload.get("token_mint"):
        rows.append(payload.get("mint") or payload.get("token_mint"))
    rows.extend(listify(payload.get("mints")))
    mints = []
    seen = set()
    for mint in rows:
        value = str(mint or "").strip()
        if not value or value in seen:
            continue
        if len(value) < 32:
            raise ValueError("Token mint looks too short.")
        mints.append(value)
        seen.add(value)
        if len(mints) >= 8:
            break
    return mints


def import_social_signal_payload(payload):
    text = str(payload.get("text") or payload.get("summary") or "").strip()
    url = str(payload.get("url") or payload.get("tweet_url") or payload.get("x_url") or "").strip()
    if not text and not url:
        raise ValueError("Social text or URL is required.")
    if url and urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Social URL must start with http or https.")

    now = time.time()
    item = {
        "account": str(payload.get("account") or payload.get("handle") or "").strip(),
        "source_platform": str(payload.get("platform") or "x").strip().lower() or "x",
        "text": text[:2000],
        "url": url,
        "mints": normalize_social_mints(payload),
        "keywords": normalize_social_keywords(payload.get("keywords")),
        "weight": payload.get("weight") or payload.get("score"),
        "source": "desktop_social_input",
        "created_at": now,
        "updated_at": now,
    }
    item["account"] = item["account"] or item["source_platform"] or "social"

    def updater(data):
        if not isinstance(data, dict):
            data = {"events": []}
        rows = data.get("events")
        if not isinstance(rows, list):
            rows = data.get("signals") if isinstance(data.get("signals"), list) else []
        dedupe_key = (item["url"], item["text"], tuple(item["mints"]))
        kept = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_key = (str(row.get("url") or ""), str(row.get("text") or ""), tuple(listify(row.get("mints"))))
            if row_key != dedupe_key:
                kept.append(row)
        kept.insert(0, item)
        data["events"] = kept[:500]
        data.pop("signals", None)
        data["updated_at"] = now
        data.setdefault("mode", "SOCIAL_RESEARCH_IMPORTS")
        return data

    updated = locked_update_json(SOCIAL_STATE_FILE, {"events": []}, updater)
    return {
        "generated_at": now,
        "mode": "SOCIAL_RESEARCH_IMPORT_ONLY",
        "live_execution_locked": True,
        "trade_triggered": False,
        "item": item,
        "summary": summarize_social_payload(updated, limit=20),
        "detail": "Social signal saved for local research. No trade was triggered.",
    }


def signal_matches_mint(signal, mint):
    if not isinstance(signal, dict) or not mint:
        return False
    if mint in listify(signal.get("mints")):
        return True
    return mint in str(signal.get("text") or "")


def summarize_catalyst_card(card):
    outcome = card.get("outcome") if isinstance(card.get("outcome"), dict) else {}
    return {
        "mint": card.get("mint"),
        "symbol": card.get("symbol") or card.get("name"),
        "summary": outcome.get("summary") or card.get("summary") or "Catalyst card",
        "sources": listify(card.get("sources")),
        "snapshot_count": card.get("snapshot_count"),
        "social_matched": (card.get("social") or {}).get("matched") if isinstance(card.get("social"), dict) else None,
    }


def summarize_social_signal(signal):
    return {
        "account": signal.get("account") or signal.get("source_platform") or "social",
        "text": signal.get("text") or signal.get("summary") or "",
        "keywords": listify(signal.get("keywords"))[:6],
        "weight": signal.get("weight") or signal.get("score") or signal.get("sentiment"),
        "url": signal.get("url"),
    }


def build_signal_summary(mint, social_state, catalyst_state):
    matched_social = [summarize_social_signal(row) for row in social_rows(social_state) if signal_matches_mint(row, mint)]
    matched_catalysts = [
        summarize_catalyst_card(card)
        for card in catalyst_rows(catalyst_state)
        if isinstance(card, dict) and card.get("mint") == mint
    ]
    return {
        "social_count": len(matched_social),
        "catalyst_count": len(matched_catalysts),
        "social": matched_social[:4],
        "catalysts": matched_catalysts[:4],
    }


def fetch_snapshot_rows(mint=None, limit=300, newest_first=False):
    if not DB_FILE.exists():
        return []
    where = ""
    params = []
    if mint:
        where = "WHERE mint = ?"
        params.append(mint)
    params.append(int(limit))
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT time, mint, source, context, price, liquidity, risk_label, payload_json
            FROM token_snapshots
            {where}
            ORDER BY time DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    parsed = []
    iterable = rows if newest_first else reversed(rows)
    for row in iterable:
        payload = {}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        item = dict(payload) if isinstance(payload, dict) else {}
        item.update({
            "time": row["time"],
            "mint": row["mint"],
            "source": row["source"],
            "context": row["context"],
            "price": row["price"],
            "liquidity": row["liquidity"],
            "risk_label": row["risk_label"],
        })
        parsed.append(item)
    return parsed


def fetch_swap_tick_rows(mint=None, limit=500, newest_first=False):
    if not mint or not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT time, mint, signature, wallet, side, price, market_cap,
                   liquidity, token_amount, sol_amount, source, payload_json
            FROM swap_ticks
            WHERE mint = ?
            ORDER BY time DESC, id DESC
            LIMIT ?
            """,
            (mint, int(limit)),
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    parsed = []
    iterable = rows if newest_first else reversed(rows)
    for row in iterable:
        payload = parse_payload_json(row["payload_json"])
        item = dict(payload) if isinstance(payload, dict) else {}
        item.update({
            "time": row["time"],
            "mint": row["mint"],
            "signature": row["signature"],
            "wallet": row["wallet"],
            "side": row["side"],
            "price": row["price"],
            "market_cap": row["market_cap"],
            "liquidity": row["liquidity"],
            "token_amount": row["token_amount"],
            "sol_amount": row["sol_amount"],
            "source": row["source"],
            "context": "swap_tick",
        })
        parsed.append(item)
    return parsed


def parse_payload_json(value):
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def fetch_trade_rows(limit=5000):
    rows = read_sqlite_rows(
        """
        SELECT mint, status, entry_time, close_time, pnl, pnl_pct, reason, payload_json
        FROM trades
        ORDER BY COALESCE(close_time, entry_time, 0) DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    parsed = []
    for row in rows:
        payload = parse_payload_json(row["payload_json"])
        if not payload:
            payload = {
                "mint": row["mint"],
                "token_mint": row["mint"],
                "status": row["status"],
                "entry_time": row["entry_time"],
                "close_time": row["close_time"],
                "total_pnl": row["pnl"],
                "total_pnl_pct": row["pnl_pct"],
                "reason": row["reason"],
            }
        elif not payload.get("status") and row["status"]:
            payload = dict(payload)
            payload["status"] = row["status"]
        parsed.append({
            "mint": row["mint"],
            "status": row["status"] or payload.get("status"),
            "entry_time": row["entry_time"],
            "close_time": row["close_time"],
            "payload": payload,
        })
    return parsed


def read_sqlite_rows(query, params=()):
    if not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return [dict(row) for row in rows]


def fetch_alert_rows(limit=100):
    rows = read_sqlite_rows(
        """
        SELECT time, mint, signal_type, total_score, edge_score,
               edge_verdict, should_trade, risk_label, payload_json
        FROM alerts
        ORDER BY time DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    parsed = []
    for row in rows:
        payload = parse_payload_json(row.get("payload_json"))
        if not payload:
            payload = {
                "time": row.get("time"),
                "mint": row.get("mint"),
                "type": row.get("signal_type"),
                "total_score": row.get("total_score"),
                "edge_score": row.get("edge_score"),
                "edge_verdict": row.get("edge_verdict"),
                "should_trade": bool(row.get("should_trade")),
                "risk_label": row.get("risk_label"),
            }
        parsed.append({
            "time": row.get("time"),
            "mint": row.get("mint"),
            "payload": payload,
        })
    return parsed


def paper_trade_bucket(status=None, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    status = str(status or "").lower()
    if (
        "fail" in status
        or payload.get("failure_reason")
        or payload.get("failed_reason")
        or payload.get("error")
        or payload.get("buy_failed")
    ):
        return "failed_trades"
    if (
        status in ("closed", "sold", "exited")
        or "closed" in status
        or payload.get("close_time")
        or payload.get("exit_time")
        or payload.get("exit_reason")
        or payload.get("close_reason")
    ):
        return "closed_trades"
    return "open_trades"


def paper_state_from_trade_rows(rows):
    state = {"open_trades": [], "closed_trades": [], "failed_trades": []}
    for row in rows or []:
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            continue
        status = row.get("status") or payload.get("status")
        state[paper_trade_bucket(status, payload)].append(payload)
    return state


def paper_state_counts(state):
    state = state if isinstance(state, dict) else {}
    return {
        key: len(state.get(key) if isinstance(state.get(key), list) else [])
        for key in ("open_trades", "closed_trades", "failed_trades")
    }


def trade_identity(row):
    row = row if isinstance(row, dict) else {}
    return (
        trade_mint(row),
        str(first_present(row.get("entry_time"), row.get("time"), "")),
        str(first_present(row.get("close_time"), row.get("exit_time"), "")),
        str(first_present(row.get("failure_reason"), row.get("exit_reason"), row.get("close_reason"), row.get("reason"), "")),
    )


def paper_state_signature(state):
    state = state if isinstance(state, dict) else {}
    signature = {}
    for key in ("open_trades", "closed_trades", "failed_trades"):
        rows = state.get(key) if isinstance(state.get(key), list) else []
        signature[key] = sorted(trade_identity(row) for row in rows if isinstance(row, dict))
    return signature


def paper_states_match(left, right):
    return paper_state_signature(left) == paper_state_signature(right)


def load_paper_trade_state():
    rows = fetch_trade_rows()
    json_data = read_json(PAPER_TRADES_FILE, {"open_trades": [], "closed_trades": [], "failed_trades": []})
    paper = json_data if isinstance(json_data, dict) else {}
    json_state = {
        "open_trades": paper.get("open_trades", []) if isinstance(paper.get("open_trades"), list) else [],
        "closed_trades": paper.get("closed_trades", []) if isinstance(paper.get("closed_trades"), list) else [],
        "failed_trades": paper.get("failed_trades", []) if isinstance(paper.get("failed_trades"), list) else [],
    }
    if rows:
        sqlite_state = paper_state_from_trade_rows(rows)
        if paper_states_match(sqlite_state, json_state):
            return sqlite_state, {
                "source": "sqlite_trades",
                "source_detail": f"{DB_FILE.relative_to(ROOT)}:trades",
                "fallback_source": "paper_trades_json",
                "fallback_reason": None,
                "mirror_warning": None,
                "sqlite_counts": paper_state_counts(sqlite_state),
                "json_counts": paper_state_counts(json_state),
            }
        return json_state, {
            "source": "paper_trades_json",
            "source_detail": str(PAPER_TRADES_FILE.relative_to(ROOT)),
            "fallback_source": "sqlite_trades",
            "fallback_reason": "sqlite_trades_parity_mismatch",
            "mirror_warning": (
                f"sqlite_trades parity mismatch; using paper_trades_json "
                f"(sqlite={paper_state_counts(sqlite_state)}, json={paper_state_counts(json_state)})"
            ),
            "sqlite_counts": paper_state_counts(sqlite_state),
            "json_counts": paper_state_counts(json_state),
        }
    return json_state, {
        "source": "paper_trades_json",
        "source_detail": str(PAPER_TRADES_FILE.relative_to(ROOT)),
        "fallback_source": "sqlite_trades",
        "fallback_reason": "sqlite_trades_empty",
        "mirror_warning": None,
        "sqlite_counts": {"open_trades": 0, "closed_trades": 0, "failed_trades": 0},
        "json_counts": paper_state_counts(json_state),
    }


def fetch_event_rows(limit=120):
    if not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT time, event_type, wallet, mint, payload_json
            FROM events
            ORDER BY time DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    parsed = []
    for row in rows:
        payload = parse_payload_json(row["payload_json"])
        parsed.append({
            "time": row["time"],
            "event_type": row["event_type"],
            "wallet": row["wallet"],
            "mint": row["mint"],
            "payload": payload,
        })
    return parsed


def decision_from_sqlite_row(row):
    return {
        "decision_id": row["decision_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "age_seconds": age_seconds(row["updated_at"]),
        "mint": row["mint"],
        "signal_type": row["signal_type"],
        "scanner_stage": row["scanner_stage"],
        "final_action": row["final_action"],
        "action_reason": row["action_reason"],
        "paper_lane": row["paper_lane"],
        "should_trade": bool(row["should_trade"]),
        "total_score": row["total_score"],
        "threshold": row["threshold"],
        "edge_score": row["edge_score"],
        "edge_verdict": row["edge_verdict"],
        "risk_label": row["risk_label"],
        "risk_score": row["risk_score"],
        "buy_quote_pass": bool(row["buy_quote_pass"]) if row["buy_quote_pass"] is not None else None,
        "sell_quote_pass": bool(row["sell_quote_pass"]) if row["sell_quote_pass"] is not None else None,
        "position_size_usd": row["position_size_usd"],
        "trade_id": row["trade_id"],
        "trade_status": row["trade_status"],
        "entry_time": row["entry_time"],
        "close_time": row["close_time"],
        "pnl": row["pnl"],
        "pnl_pct": row["pnl_pct"],
        "payload": parse_payload_json(row["payload_json"]),
        "result": parse_payload_json(row["result_json"]) if row["result_json"] else None,
    }


def decision_select_columns():
    return """
        decision_id, created_at, updated_at, mint, signal_type,
        scanner_stage, final_action, action_reason, paper_lane,
        should_trade, total_score, threshold, edge_score,
        edge_verdict, risk_label, risk_score, buy_quote_pass,
        sell_quote_pass, position_size_usd, trade_id,
        trade_status, entry_time, close_time, pnl, pnl_pct,
        payload_json, result_json
    """


def fetch_decision_rows(limit=80, mint=None):
    if not DB_FILE.exists():
        return []
    where = ""
    params = []
    if mint:
        where = "WHERE mint = ?"
        params.append(mint)
    params.append(int(limit))
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT {decision_select_columns()}
            FROM decision_records
            {where}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    decisions = [decision_from_sqlite_row(row) for row in rows]
    enrich_decisions_with_trade_results(decisions)
    return decisions


def fetch_decision_row_by_id(decision_id):
    decision_id = str(decision_id or "").strip()
    if not decision_id or not DB_FILE.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"""
            SELECT {decision_select_columns()}
            FROM decision_records
            WHERE decision_id = ?
            LIMIT 1
            """,
            (decision_id,),
        ).fetchone()
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return decision_from_sqlite_row(row) if row else None


def trade_result_from_row(trade):
    trade = trade if isinstance(trade, dict) else {}
    signal_metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    return {
        "source": "sqlite_trade_link",
        "mint": trade.get("mint") or trade.get("token_mint"),
        "trade_status": trade.get("status"),
        "trade_id": trade.get("trade_id") or signal_metadata.get("trade_id"),
        "entry_time": trade.get("entry_time"),
        "close_time": trade.get("close_time"),
        "pnl": trade.get("total_pnl", trade.get("pnl")),
        "pnl_pct": trade.get("total_pnl_pct", trade.get("pnl_pct")),
        "failure_reason": trade.get("failure_reason"),
        "exit_reason": trade.get("exit_reason") or trade.get("close_reason"),
    }


def enrich_decisions_with_trade_results(decisions):
    decision_ids = {
        str(decision.get("decision_id"))
        for decision in decisions
        if decision.get("decision_id") and not decision.get("result")
    }
    if not decision_ids:
        return decisions
    linked = {}
    for trade in fetch_trade_rows(limit=1000):
        signal_metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
        decision_id = signal_metadata.get("decision_id")
        if decision_id in decision_ids and decision_id not in linked:
            linked[decision_id] = trade_result_from_row(trade)
    for decision in decisions:
        result = linked.get(decision.get("decision_id"))
        if not result:
            continue
        decision["result"] = result
        decision["trade_id"] = decision.get("trade_id") or result.get("trade_id")
        decision["trade_status"] = decision.get("trade_status") or result.get("trade_status")
        decision["entry_time"] = decision.get("entry_time") or result.get("entry_time")
        decision["close_time"] = decision.get("close_time") or result.get("close_time")
        decision["pnl"] = decision.get("pnl") if decision.get("pnl") is not None else result.get("pnl")
        decision["pnl_pct"] = decision.get("pnl_pct") if decision.get("pnl_pct") is not None else result.get("pnl_pct")
    return decisions


def decision_matches_filter(decision, filter_name=None, lane=None):
    if lane and decision.get("paper_lane") != lane:
        return False
    filter_name = str(filter_name or "all")
    if filter_name in ("", "all"):
        return True
    action = str(decision.get("final_action") or "").lower()
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    rule_outcomes = payload.get("rule_outcomes") if isinstance(payload.get("rule_outcomes"), dict) else {}
    risk = rule_outcomes.get("risk") if isinstance(rule_outcomes.get("risk"), dict) else {}
    if filter_name == "bought":
        return "opened" in action or "open_attempt" in action
    if filter_name == "skipped":
        return "skip" in action or "blocked" in action or action == "runtime_skip"
    if filter_name == "exploration":
        return decision.get("paper_lane") == "exploration"
    if filter_name == "quote_failed":
        return decision.get("buy_quote_pass") is False or decision.get("sell_quote_pass") is False
    if filter_name == "hard_risk":
        return bool(risk.get("hard_block") or decision.get("risk_label") in ("DANGER", "EMERGENCY"))
    if filter_name == "social":
        social = inputs.get("social_match") if isinstance(inputs.get("social_match"), dict) else {}
        return bool(social.get("matched"))
    if filter_name == "wallet":
        return bool(inputs.get("wallets"))
    return True


def build_decisions_payload(limit=80, mint=None, filter_name=None, lane=None):
    items = fetch_decision_rows(limit=limit, mint=mint)
    items = [item for item in items if decision_matches_filter(item, filter_name=filter_name, lane=lane)]
    counts = {}
    for item in items:
        key = item.get("final_action") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return {
        "generated_at": time.time(),
        "source": "decision_records",
        "live_execution_locked": True,
        "filter": filter_name or "all",
        "lane": lane or "all",
        "count": len(items),
        "counts": counts,
        "items": items,
    }


MARKET_RADAR_NURSERY_STAGES = ("rejected", "watch", "quote_watch", "paper_bought", "closed", "failed")
MARKET_RADAR_SOFT_WATCH_BLOCKERS = {"score_below_market_radar_threshold"}


def market_radar_payload(decision):
    decision = decision if isinstance(decision, dict) else {}
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    return payload.get("market_radar") if isinstance(payload.get("market_radar"), dict) else {}


def market_radar_score_payload(decision):
    radar = market_radar_payload(decision)
    return radar.get("score") if isinstance(radar.get("score"), dict) else {}


def market_radar_market_info(decision):
    decision = decision if isinstance(decision, dict) else {}
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    return first_non_empty(
        inputs.get("market_info") if isinstance(inputs.get("market_info"), dict) else None,
        payload.get("market_info") if isinstance(payload.get("market_info"), dict) else None,
        {},
    ) or {}


def market_radar_review_stage(decision):
    action = str((decision or {}).get("final_action") or "").lower()
    status = decision_report_trade_status(decision)
    radar_action = decision_market_radar_action(decision)
    score = market_radar_score_payload(decision)
    quote_retryable = bool(radar_action.get("quote_retryable"))
    skip_bucket = str(radar_action.get("skip_bucket") or "")
    blockers = [str(item) for item in score.get("blockers") if item] if isinstance(score.get("blockers"), list) else []
    score_allowed = bool(score.get("allowed"))
    score_value = safe_float(first_non_empty((decision or {}).get("total_score"), score.get("score")), 0)
    threshold = safe_float(first_non_empty((decision or {}).get("threshold"), score.get("threshold")), 70)
    if status in {"failed", "buy_failed"} or "failed" in action:
        return "failed"
    if status in {"closed", "sold", "exited"}:
        return "closed"
    if status == "open" or "opened" in action:
        return "paper_bought"
    if score_allowed and (
        quote_retryable
        or skip_bucket == "quote_or_route"
        or (decision or {}).get("buy_quote_pass") is False
        or (decision or {}).get("sell_quote_pass") is False
    ):
        return "quote_watch"
    if blockers and any(blocker not in MARKET_RADAR_SOFT_WATCH_BLOCKERS for blocker in blockers):
        return "rejected"
    if score_value >= max(0, threshold - 10):
        return "watch"
    return "rejected"


def market_radar_market_number(row, *keys):
    row = row if isinstance(row, dict) else {}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return safe_float(value, None)
    return None


def market_radar_pct_change(start, end):
    start = safe_float(start, None)
    end = safe_float(end, None)
    if start in (None, 0) or end is None:
        return None
    return round(((end - start) / start) * 100, 2)


def market_radar_hold_seconds(entry_time, close_time):
    entry_time = safe_float(entry_time, None)
    close_time = safe_float(close_time, None)
    if entry_time is None or close_time is None or close_time < entry_time:
        return None
    return round(close_time - entry_time, 2)


def market_radar_postmortem(decision):
    decision = decision if isinstance(decision, dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    paper_outcome = result.get("paper_outcome") if isinstance(result.get("paper_outcome"), dict) else {}
    entry_price = safe_float(first_non_empty(paper_outcome.get("entry_price"), result.get("entry_price"), decision.get("entry_price")), None)
    exit_price = safe_float(first_non_empty(paper_outcome.get("exit_price"), result.get("exit_price"), decision.get("exit_price")), None)
    entry_liquidity = safe_float(
        first_non_empty(paper_outcome.get("entry_liquidity_usd"), result.get("entry_liquidity_usd"), decision.get("entry_liquidity_usd")),
        None,
    )
    exit_liquidity = safe_float(
        first_non_empty(paper_outcome.get("exit_liquidity_usd"), result.get("exit_liquidity_usd"), decision.get("exit_liquidity_usd")),
        None,
    )
    entry_market_cap = safe_float(
        first_non_empty(paper_outcome.get("entry_market_cap"), result.get("entry_market_cap"), decision.get("entry_market_cap")),
        None,
    )
    exit_market_cap = safe_float(
        first_non_empty(paper_outcome.get("exit_market_cap"), result.get("exit_market_cap"), decision.get("exit_market_cap")),
        None,
    )
    entry_time = first_non_empty(paper_outcome.get("entry_time"), result.get("entry_time"), decision.get("entry_time"))
    close_time = first_non_empty(paper_outcome.get("close_time"), paper_outcome.get("exit_time"), result.get("close_time"), result.get("exit_time"), decision.get("close_time"), decision.get("exit_time"))
    return {
        "status": decision_report_trade_status(decision) or None,
        "pnl": decision_report_pnl(decision),
        "pnl_pct": decision_report_pnl_pct(decision),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_liquidity_usd": entry_liquidity,
        "exit_liquidity_usd": exit_liquidity,
        "liquidity_change_pct": market_radar_pct_change(entry_liquidity, exit_liquidity),
        "entry_market_cap": entry_market_cap,
        "exit_market_cap": exit_market_cap,
        "market_cap_change_pct": market_radar_pct_change(entry_market_cap, exit_market_cap),
        "position_size_usd": safe_float(first_non_empty(paper_outcome.get("position_size_usd"), result.get("position_size_usd"), decision.get("position_size_usd")), None),
        "entry_reason": first_non_empty(paper_outcome.get("entry_reason"), result.get("entry_reason"), decision.get("entry_reason")),
        "exit_reason": first_non_empty(paper_outcome.get("exit_reason"), result.get("exit_reason"), decision.get("exit_reason")),
        "failure_reason": first_non_empty(result.get("failure_reason"), decision.get("failure_reason"), paper_outcome.get("failure_reason")),
        "hold_seconds": market_radar_hold_seconds(entry_time, close_time),
    }


def market_radar_review_item(decision):
    decision = decision if isinstance(decision, dict) else {}
    radar = market_radar_payload(decision)
    radar_action = radar.get("decision") if isinstance(radar.get("decision"), dict) else {}
    score = radar.get("score") if isinstance(radar.get("score"), dict) else {}
    market_info = market_radar_market_info(decision)
    reason = first_non_empty(
        radar_action.get("open_reason"),
        radar_action.get("skip_reason"),
        decision.get("action_reason"),
        "unrecorded",
    )
    return {
        "decision_id": decision.get("decision_id"),
        "mint": decision.get("mint"),
        "symbol": market_info.get("symbol"),
        "updated_at": decision.get("updated_at") or decision.get("created_at"),
        "stage": market_radar_review_stage(decision),
        "action": decision.get("final_action"),
        "reason": reason,
        "skip_bucket": radar_action.get("skip_bucket"),
        "quote_retryable": bool(radar_action.get("quote_retryable")),
        "score": first_non_empty(decision.get("total_score"), score.get("score")),
        "threshold": first_non_empty(decision.get("threshold"), score.get("threshold")),
        "liquidity_usd": market_radar_market_number(market_info, "liquidity", "liquidity_usd"),
        "market_cap_usd": market_radar_market_number(market_info, "market_cap", "marketCap", "fdv"),
        "volume_h1": market_radar_market_number(market_info, "volume_h1", "volume"),
        "tx_count_m5": market_radar_market_number(market_info, "tx_count", "tx_count_m5"),
        "buy_ratio": score.get("buy_ratio"),
        "sell_ratio": score.get("sell_ratio"),
        "pair_age_seconds": score.get("pair_age_seconds"),
        "blockers": score.get("blockers") if isinstance(score.get("blockers"), list) else [],
        "positives": score.get("reasons") if isinstance(score.get("reasons"), list) else [],
        "sources": radar.get("sources") if isinstance(radar.get("sources"), list) else [],
        "trade_status": decision_report_trade_status(decision) or None,
        "pnl": decision_report_pnl(decision),
        "pnl_pct": decision_report_pnl_pct(decision),
        "buy_quote_pass": decision.get("buy_quote_pass"),
        "sell_quote_pass": decision.get("sell_quote_pass"),
        "postmortem": market_radar_postmortem(decision),
    }


def build_market_radar_review_payload(limit=120):
    search_limit = max(int(limit), min(5000, int(limit) * 5))
    decisions = [
        decision
        for decision in fetch_decision_rows(limit=search_limit)
        if decision_report_lane(decision) == "market_radar" or bool(market_radar_payload(decision))
    ]
    decisions.sort(key=lambda row: safe_float(first_non_empty(row.get("updated_at"), row.get("created_at")), 0), reverse=True)
    items = [market_radar_review_item(decision) for decision in decisions[:int(limit)]]
    summary = {stage: 0 for stage in MARKET_RADAR_NURSERY_STAGES}
    for item in items:
        stage = item.get("stage") if item.get("stage") in summary else "rejected"
        summary[stage] += 1
    summary["total"] = len(items)
    return {
        "generated_at": time.time(),
        "mode": "MARKET_RADAR_REVIEW_ONLY",
        "source": "sqlite_decision_records",
        "live_execution_locked": True,
        "summary": summary,
        "items": items,
        "notes": [
            "Token Nursery is a read-only review of Market Radar decision records.",
            "Quote Watch means the candidate was close enough to inspect routes but quote budget, cooldown, or route checks blocked a paper entry.",
            "Paper Bought, Closed, and Failed are paper-only states and never enable live execution.",
        ],
    }


def openai_decision_explainer_model():
    load_desktop_env()
    return os.getenv("OPENAI_DECISION_EXPLAINER_MODEL") or "gpt-4.1-mini"


def google_decision_explainer_model():
    load_desktop_env()
    return os.getenv("GOOGLE_AI_DECISION_EXPLAINER_MODEL") or os.getenv("GEMINI_DECISION_EXPLAINER_MODEL") or "gemini-2.5-flash"


def groq_decision_explainer_model():
    load_desktop_env()
    return os.getenv("GROQ_DECISION_EXPLAINER_MODEL") or "llama-3.3-70b-versatile"


def decision_explainer_provider_configs():
    load_desktop_env()
    providers = []
    google_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if google_key:
        providers.append({
            "provider": "google_ai",
            "source": "google_ai_decision_explainer",
            "api_key": google_key,
            "model": google_decision_explainer_model(),
            "generate": generate_google_decision_explanation,
        })
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append({
            "provider": "groq",
            "source": "groq_decision_explainer",
            "api_key": groq_key,
            "model": groq_decision_explainer_model(),
            "generate": generate_groq_decision_explanation,
        })
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        providers.append({
            "provider": "openai",
            "source": "openai_decision_explainer",
            "api_key": openai_key,
            "model": openai_decision_explainer_model(),
            "generate": generate_decision_explanation,
        })
    return providers


def is_provider_limit_error(exc):
    text = str(exc or "").lower()
    limit_terms = ("http 429", "rate limit", "rate_limit", "quota", "resource exhausted", "too many requests", "limit exceeded")
    return any(term in text for term in limit_terms)


def build_decision_explanation_payload(decision_id):
    decision_id = str(decision_id or "").strip()
    if not decision_id:
        raise ValueError("decision_id is required.")
    decision = fetch_decision_row_by_id(decision_id)
    if not decision:
        raise LookupError("decision_id not found.")

    providers = decision_explainer_provider_configs()
    provider = providers[0] if providers else {
        "provider": "google_ai",
        "source": "google_ai_decision_explainer",
        "api_key": None,
        "model": google_decision_explainer_model(),
        "generate": None,
    }
    attempted_providers = []
    base = {
        "generated_at": time.time(),
        "source": provider.get("source"),
        "provider": provider.get("provider"),
        "read_only": True,
        "advisory_only": True,
        "live_execution_locked": True,
        "execution_routes_enabled": False,
        "decision_id": decision_id,
        "mint": decision.get("mint"),
        "model": provider.get("model"),
    }
    if not providers:
        return {
            **base,
            "available": False,
            "status": "missing_api_key",
            "advisory": None,
            "attempted_providers": [],
            "detail": "Set GOOGLE_AI_API_KEY in the active local .env to enable Google AI advisory explanations. Optional fallback: GROQ_API_KEY.",
        }

    last_error = None
    primary_provider = provider.get("provider")
    for index, provider in enumerate(providers):
        attempted_providers.append(provider.get("provider"))
        base = {
            **base,
            "source": provider.get("source"),
            "provider": provider.get("provider"),
            "model": provider.get("model"),
        }
        try:
            generated = provider["generate"](
                decision,
                api_key=provider.get("api_key"),
                model=provider.get("model"),
                timeout=20,
            )
            return {
                **base,
                "available": True,
                "status": "ok",
                "advisory": generated.get("text") or "",
                "model": generated.get("model") or provider.get("model"),
                "response_id": generated.get("response_id"),
                "attempted_providers": attempted_providers,
                "fallback_from": primary_provider if index > 0 else None,
            }
        except Exception as exc:
            last_error = exc
            if not is_provider_limit_error(exc):
                break

    return {
        **base,
        "available": False,
        "status": "error",
        "advisory": None,
        "attempted_providers": attempted_providers,
        "detail": redact_secrets(last_error),
    }


def decision_report_lane(decision):
    decision = decision if isinstance(decision, dict) else {}
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    paper_outcome = result.get("paper_outcome") if isinstance(result.get("paper_outcome"), dict) else {}
    lane_values = [
        paper_outcome.get("paper_lane"),
        action.get("paper_lane"),
        decision.get("paper_lane"),
    ]
    for lane in lane_values:
        lane = str(lane or "").strip().lower()
        if lane == "exploration":
            return "exploration"
        if lane == "market_radar":
            return "market_radar"
        if lane in {"protected", "manual", "protected_manual", "manual_protected"}:
            return "protected_manual"
    return "main"


def decision_report_pnl(decision):
    decision = decision if isinstance(decision, dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    return safe_float(first_non_empty(decision.get("pnl"), result.get("pnl")), 0)


def decision_report_pnl_pct(decision):
    decision = decision if isinstance(decision, dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    return safe_float(first_non_empty(decision.get("pnl_pct"), result.get("pnl_pct")), None)


def decision_report_trade_status(decision):
    decision = decision if isinstance(decision, dict) else {}
    result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
    return str(first_non_empty(decision.get("trade_status"), result.get("trade_status"), result.get("status"), "")).lower()


def empty_decision_lane_summary(label, minimum_closed=50):
    return {
        "label": label,
        "candidate_decisions": 0,
        "paper_attempts": 0,
        "paper_opened": 0,
        "skipped": 0,
        "quote_failed": 0,
        "hard_blocked": 0,
        "social_confirmed": 0,
        "wallet_confirmed": 0,
        "open_trades": 0,
        "closed_trades": 0,
        "failed_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0,
        "avg_pnl_pct": None,
        "win_rate": 0,
        "sample_ready": False,
        "minimum_closed_trades": minimum_closed,
        "protected_positions": 0,
        "skip_reasons": {},
        "skip_buckets": {},
        "open_reasons": {},
    }


def increment_summary_counter(summary, field, key):
    if not key:
        return
    bucket = summary.setdefault(field, {})
    key = str(key)
    bucket[key] = bucket.get(key, 0) + 1


def decision_market_radar_action(decision):
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    radar = payload.get("market_radar") if isinstance(payload.get("market_radar"), dict) else {}
    action = radar.get("decision") if isinstance(radar.get("decision"), dict) else {}
    return action


def strip_reason_prefix(reason):
    reason = str(reason or "").strip()
    for prefix in ("market_radar_skip:", "market_radar_open:"):
        if reason.startswith(prefix):
            return reason[len(prefix):].strip()
    return reason


def add_decision_to_lane_summary(summary, decision):
    action = str(decision.get("final_action") or "").lower()
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    rule_outcomes = payload.get("rule_outcomes") if isinstance(payload.get("rule_outcomes"), dict) else {}
    risk = rule_outcomes.get("risk") if isinstance(rule_outcomes.get("risk"), dict) else {}
    social = inputs.get("social_match") if isinstance(inputs.get("social_match"), dict) else {}
    status = decision_report_trade_status(decision)
    radar_action = decision_market_radar_action(decision)

    summary["candidate_decisions"] += 1
    if decision.get("should_trade") or "open_attempt" in action:
        summary["paper_attempts"] += 1
    if "opened" in action:
        summary["paper_opened"] += 1
    if "skip" in action or "blocked" in action or action == "runtime_skip" or decision.get("should_trade") is False:
        summary["skipped"] += 1
        action_reason = str(decision.get("action_reason") or "")
        is_market_radar = decision_report_lane(decision) == "market_radar" or bool(payload.get("market_radar"))
        if radar_action.get("skip_reason"):
            skip_reason = radar_action.get("skip_reason")
        elif is_market_radar and action_reason.startswith("market_radar_skip:"):
            skip_reason = strip_reason_prefix(action_reason)
        elif is_market_radar:
            skip_reason = None
        else:
            skip_reason = strip_reason_prefix(action_reason)
        skip_bucket = radar_action.get("skip_bucket")
        increment_summary_counter(summary, "skip_reasons", skip_reason)
        increment_summary_counter(summary, "skip_buckets", skip_bucket)
    if "opened" in action or "open_attempt" in action:
        open_reason = radar_action.get("open_reason") or strip_reason_prefix(decision.get("action_reason"))
        increment_summary_counter(summary, "open_reasons", open_reason)
    if decision.get("buy_quote_pass") is False or decision.get("sell_quote_pass") is False:
        summary["quote_failed"] += 1
    if risk.get("hard_block") or str(decision.get("risk_label") or "").upper() in {"DANGER", "EMERGENCY", "BLOCKED"}:
        summary["hard_blocked"] += 1
    if social.get("matched"):
        summary["social_confirmed"] += 1
    if inputs.get("wallets"):
        summary["wallet_confirmed"] += 1

    if status in {"closed", "sold", "exited"}:
        pnl = decision_report_pnl(decision)
        pnl_pct = decision_report_pnl_pct(decision)
        summary["closed_trades"] += 1
        summary["total_pnl"] = round(summary["total_pnl"] + pnl, 6)
        if pnl >= 0:
            summary["wins"] += 1
        else:
            summary["losses"] += 1
        if pnl_pct is not None:
            summary.setdefault("_pnl_pct_values", []).append(pnl_pct)
    elif status in {"failed", "buy_failed"}:
        summary["failed_trades"] += 1
    elif status == "open" or ("opened" in action and not status):
        summary["open_trades"] += 1


def finalize_decision_lane_summary(summary):
    closed = summary["closed_trades"]
    pnl_pct_values = summary.pop("_pnl_pct_values", [])
    summary["win_rate"] = round((summary["wins"] / closed) * 100, 2) if closed else 0
    summary["avg_pnl_pct"] = (
        round(sum(pnl_pct_values) / len(pnl_pct_values), 2)
        if pnl_pct_values
        else None
    )
    summary["sample_ready"] = closed >= summary["minimum_closed_trades"]
    return summary


def build_decision_lane_report_payload(limit=5000, state=None):
    state = state if isinstance(state, dict) else read_state_files()
    watchlist = state.get("watchlist") if isinstance(state.get("watchlist"), list) else []
    decisions = fetch_decision_rows(limit=limit)
    lanes = {
        "co_main": empty_decision_lane_summary("Co-Main Strategy"),
        "main": empty_decision_lane_summary("Wallet Main Strategy"),
        "market_radar": empty_decision_lane_summary("Market Radar Co-Main"),
        "exploration": empty_decision_lane_summary("Exploration Lane"),
        "protected_manual": empty_decision_lane_summary("Protected / Manual", minimum_closed=0),
    }
    lanes["protected_manual"]["protected_positions"] = len(watchlist)

    for decision in decisions:
        lane = decision_report_lane(decision)
        add_decision_to_lane_summary(lanes[lane], decision)
        if lane in {"main", "market_radar"}:
            add_decision_to_lane_summary(lanes["co_main"], decision)

    for summary in lanes.values():
        finalize_decision_lane_summary(summary)

    return {
        "generated_at": time.time(),
        "source": "sqlite_decision_records",
        "source_detail": f"{relative_display_path(DB_FILE)}:decision_records",
        "live_execution_locked": True,
        "total_decisions": len(decisions),
        "lanes": lanes,
        "notes": [
            "Co-main combines wallet-main and Market Radar decision records while preserving each lane separately.",
            "Exploration remains separate and experimental.",
            "Protected/manual count comes from the manual watchlist until protected actions write decision records.",
        ],
    }


def decision_social_matched(decision):
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    social = inputs.get("social_match") if isinstance(inputs.get("social_match"), dict) else {}
    catalyst = inputs.get("social_catalyst") if isinstance(inputs.get("social_catalyst"), dict) else {}
    return bool(social.get("matched") or catalyst.get("matched"))


def decision_wallet_confirmed(decision):
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    return bool(inputs.get("wallets") or safe_float(inputs.get("wallet_count"), 0) > 0)


def clone_decision_summary(label, minimum_closed=50):
    summary = empty_decision_lane_summary(label, minimum_closed=minimum_closed)
    summary["expectancy_pnl"] = 0
    summary["attempt_to_open_rate"] = 0
    summary["decision_to_close_rate"] = 0
    return summary


def finalize_decision_analytics_summary(summary):
    finalize_decision_lane_summary(summary)
    attempts = summary.get("paper_attempts", 0)
    candidates = summary.get("candidate_decisions", 0)
    closed = summary.get("closed_trades", 0)
    summary["expectancy_pnl"] = round(summary["total_pnl"] / closed, 6) if closed else 0
    summary["attempt_to_open_rate"] = round((summary["paper_opened"] / attempts) * 100, 2) if attempts else 0
    summary["decision_to_close_rate"] = round((closed / candidates) * 100, 2) if candidates else 0
    return summary


def add_to_summary(summary, decision):
    add_decision_to_lane_summary(summary, decision)


def build_social_expansion_gate(groups):
    social = groups.get("social_catalyst", {})
    non_social = groups.get("non_social", {})
    social_closed = int(social.get("closed_trades", 0) or 0)
    non_social_closed = int(non_social.get("closed_trades", 0) or 0)
    if social_closed < 50:
        return {
            "allowed": False,
            "reason": f"Need at least 50 labeled social outcomes before expanding sources; current={social_closed}",
            "minimum_labeled_social_outcomes": 50,
            "current_labeled_social_outcomes": social_closed,
        }
    if non_social_closed < 50:
        return {
            "allowed": False,
            "reason": f"Need at least 50 non-social comparison outcomes; current={non_social_closed}",
            "minimum_labeled_social_outcomes": 50,
            "current_labeled_social_outcomes": social_closed,
        }
    allowed = (
        safe_float(social.get("win_rate"), 0) > safe_float(non_social.get("win_rate"), 0)
        and safe_float(social.get("expectancy_pnl"), 0) > safe_float(non_social.get("expectancy_pnl"), 0)
    )
    return {
        "allowed": allowed,
        "reason": "Reddit social cohort outperforms non-social cohort" if allowed else "Social cohort has enough sample but has not outperformed non-social decisions",
        "minimum_labeled_social_outcomes": 50,
        "current_labeled_social_outcomes": social_closed,
    }


def build_decision_outcome_analytics_payload(limit=5000):
    decisions = fetch_decision_rows(limit=limit)
    overall = clone_decision_summary("All Decisions")
    lanes = {
        "co_main": clone_decision_summary("Co-Main Strategy"),
        "main": clone_decision_summary("Wallet Main Strategy"),
        "market_radar": clone_decision_summary("Market Radar Co-Main"),
        "exploration": clone_decision_summary("Exploration Lane"),
        "protected_manual": clone_decision_summary("Protected / Manual", minimum_closed=0),
    }
    groups = {
        "social_catalyst": clone_decision_summary("Social Catalyst"),
        "wallet_only": clone_decision_summary("Wallet Only"),
        "non_social": clone_decision_summary("Non-Social"),
        "quote_failed": clone_decision_summary("Quote Failed", minimum_closed=0),
        "hard_risk": clone_decision_summary("Hard Risk", minimum_closed=0),
    }

    for decision in decisions:
        add_to_summary(overall, decision)
        lane = decision_report_lane(decision)
        add_to_summary(lanes[lane], decision)
        if lane in {"main", "market_radar"}:
            add_to_summary(lanes["co_main"], decision)
        social = decision_social_matched(decision)
        wallet = decision_wallet_confirmed(decision)
        if social:
            add_to_summary(groups["social_catalyst"], decision)
        else:
            add_to_summary(groups["non_social"], decision)
        if wallet and not social:
            add_to_summary(groups["wallet_only"], decision)
        if decision.get("buy_quote_pass") is False or decision.get("sell_quote_pass") is False:
            add_to_summary(groups["quote_failed"], decision)
        payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
        rule_outcomes = payload.get("rule_outcomes") if isinstance(payload.get("rule_outcomes"), dict) else {}
        risk = rule_outcomes.get("risk") if isinstance(rule_outcomes.get("risk"), dict) else {}
        if risk.get("hard_block") or str(decision.get("risk_label") or "").upper() in {"DANGER", "EMERGENCY", "BLOCKED"}:
            add_to_summary(groups["hard_risk"], decision)

    finalize_decision_analytics_summary(overall)
    for summary in lanes.values():
        finalize_decision_analytics_summary(summary)
    for summary in groups.values():
        finalize_decision_analytics_summary(summary)

    return {
        "generated_at": time.time(),
        "source": "sqlite_decision_records",
        "source_detail": f"{relative_display_path(DB_FILE)}:decision_records",
        "live_execution_locked": True,
        "limit": limit,
        "total_decisions": len(decisions),
        "overall": overall,
        "lanes": lanes,
        "groups": groups,
        "social_expansion_gate": build_social_expansion_gate(groups),
        "notes": [
            "Analytics are labels over canonical decision records.",
            "Social expansion remains blocked until labeled outcomes prove lift over non-social decisions.",
        ],
    }


def fetch_event_metadata(mints):
    unique_mints = [mint for mint in dict.fromkeys(str(mint or "").strip() for mint in mints or []) if mint]
    if not unique_mints or not DB_FILE.exists():
        return {}
    placeholders = ",".join("?" for _ in unique_mints)
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT time, mint, price, liquidity, payload_json
            FROM token_snapshots
            WHERE mint IN ({placeholders})
            ORDER BY time DESC, id DESC
            """,
            unique_mints,
        ).fetchall()
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    metadata = {}
    for row in rows:
        mint = row["mint"]
        if mint in metadata:
            continue
        payload = parse_payload_json(row["payload_json"])
        market_info = payload.get("market_info") if isinstance(payload.get("market_info"), dict) else {}
        price_value = first_non_empty(row["price"], payload.get("price"), market_info.get("price"))
        metadata[mint] = {
            "name": first_non_empty(payload.get("name"), market_info.get("name")),
            "symbol": first_non_empty(payload.get("symbol"), market_info.get("symbol")),
            "image_url": safe_image_url(first_non_empty(
                payload.get("image_url"),
                payload.get("image"),
                payload.get("logoURI"),
                market_info.get("image_url"),
                market_info.get("image"),
                market_info.get("logoURI"),
                market_info.get("logo_uri"),
            )),
            "price": price_value,
            "market_cap": first_non_empty(payload.get("market_cap"), market_info.get("market_cap"), market_info.get("fdv"), estimate_pump_market_cap(mint, price_value)),
            "liquidity": first_non_empty(row["liquidity"], payload.get("liquidity"), market_info.get("liquidity")),
            "tx_count": first_non_empty(payload.get("tx_count"), market_info.get("tx_count"), nested_get(market_info, "txns", "total")),
            "holder_count": first_non_empty(payload.get("holder_count"), market_info.get("holder_count"), market_info.get("holders")),
        }
    return metadata


def extract_asset_metadata(payload):
    payload = payload if isinstance(payload, dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    content = result.get("content") if isinstance(result.get("content"), dict) else {}
    metadata = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
    links = content.get("links") if isinstance(content.get("links"), dict) else {}
    files = content.get("files") if isinstance(content.get("files"), list) else []
    first_file = files[0] if files and isinstance(files[0], dict) else {}
    return {
        "name": first_non_empty(metadata.get("name"), result.get("name")),
        "symbol": first_non_empty(metadata.get("symbol"), result.get("symbol")),
        "image_url": safe_image_url(first_non_empty(
            links.get("image"),
            metadata.get("image"),
            first_file.get("cdn_uri"),
            first_file.get("uri"),
        )),
    }


def fetch_rpc_asset_metadata(mints, max_lookup=24, timeout=1):
    load_desktop_env()
    now = time.time()
    result = {}
    lookup = []
    for mint in [mint for mint in dict.fromkeys(str(mint or "").strip() for mint in mints or []) if mint]:
        cached = ASSET_METADATA_CACHE.get(mint)
        if cached and now - safe_float(cached.get("updated_at"), 0) <= ASSET_METADATA_TTL_SECONDS:
            result[mint] = cached.get("metadata") or {}
            continue
        if len(lookup) < max_lookup:
            lookup.append(mint)

    providers = build_helius_rpc_providers()
    helius_providers = [provider for provider in providers if "helius" in provider.url]
    if not lookup:
        return result

    lookup = lookup[:max_lookup]
    rpc_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "meme-trader-pro-asset-metadata",
        "method": "getAssetBatch",
        "params": {"ids": lookup},
    }).encode("utf-8")
    batch_rows = None
    for provider in helius_providers:
        request = Request(provider.url, data=rpc_payload, headers={"content-type": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
                rows = data.get("result") if isinstance(data, dict) else None
                if isinstance(rows, list):
                    batch_rows = rows
                    break
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            batch_rows = None

    if isinstance(batch_rows, list):
        for index, mint in enumerate(lookup):
            row = batch_rows[index] if index < len(batch_rows) and isinstance(batch_rows[index], dict) else {}
            metadata = extract_asset_metadata({"result": row})
            ASSET_METADATA_CACHE[mint] = {"updated_at": now, "metadata": metadata}
            if metadata:
                result[mint] = metadata
        return result

    for mint in lookup[:2]:
        metadata = {}
        single_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": "meme-trader-pro-asset-metadata",
            "method": "getAsset",
            "params": {"id": mint},
        }).encode("utf-8")
        for provider in helius_providers:
            request = Request(provider.url, data=single_payload, headers={"content-type": "application/json"})
            try:
                with urlopen(request, timeout=timeout) as response:
                    data = json.loads(response.read().decode("utf-8", errors="replace"))
                    metadata = extract_asset_metadata(data)
                    if metadata.get("name") or metadata.get("symbol") or metadata.get("image_url"):
                        break
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                metadata = {}
        ASSET_METADATA_CACHE[mint] = {"updated_at": now, "metadata": metadata}
        if metadata:
            result[mint] = metadata
    return result


def build_snapshots_payload(mint=None, limit=250):
    snapshots = fetch_snapshot_rows(mint=mint, limit=limit, newest_first=False)
    return {
        "generated_at": time.time(),
        "source": "sqlite_token_snapshots",
        "source_detail": f"{DB_FILE.relative_to(ROOT)}:token_snapshots",
        "source_contract": {
            "snapshots": "sqlite_token_snapshots",
            "trades": "paper_trades_json",
            "decisions": "sqlite_decision_records",
        },
        "mint": mint,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }


def nested_get(row, *keys):
    current = row
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def relative_display_path(path):
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def safe_image_url(value):
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return str(value).strip()


def estimate_pump_market_cap(mint, price):
    if not str(mint or "").endswith("pump"):
        return None
    price = safe_float(price, 0)
    if price <= 0:
        return None
    return round(price * 1_000_000_000, 2)


def compact_candidate_snapshot(row):
    row = row if isinstance(row, dict) else {}
    market_info = row.get("market_info") if isinstance(row.get("market_info"), dict) else {}
    social_match = row.get("social_match") if isinstance(row.get("social_match"), dict) else {}
    holder_metrics = row.get("holder_concentration_metrics") if isinstance(row.get("holder_concentration_metrics"), dict) else {}
    reasons = []
    for value in (
        row.get("skip_reason"),
        row.get("hard_block_reason"),
        row.get("strategy_guard_reason"),
        row.get("buy_quote_reason"),
        row.get("sell_quote_reason"),
        social_match.get("reason"),
    ):
        if value:
            reasons.append(str(value))
    for key in ("score_reasons", "confirmation_reasons", "confirmation_warnings", "edge_risks", "risk_warnings"):
        for value in listify(row.get(key)):
            if value:
                reasons.append(str(value))

    context = row.get("context") or ""
    should_trade = row.get("should_trade")
    if should_trade is True or context == "scanner_entry_candidate":
        status = "TRADE_READY"
    elif row.get("hard_block") or row.get("hard_block_reason"):
        status = "BLOCKED"
    else:
        status = "SKIPPED"

    tx_count = first_non_empty(
        row.get("tx_count"),
        row.get("transaction_count"),
        market_info.get("tx_count"),
        market_info.get("transaction_count"),
        market_info.get("transactions"),
        nested_get(market_info, "transactions", "total"),
        nested_get(market_info, "txns", "total"),
    )
    if isinstance(tx_count, dict):
        tx_count = first_non_empty(tx_count.get("total"), tx_count.get("count"), tx_count.get("m5"))

    price_value = first_non_empty(row.get("price"), market_info.get("price"))
    market_cap = first_non_empty(row.get("market_cap"), market_info.get("market_cap"), market_info.get("fdv"))
    market_cap_estimated = False
    if market_cap in (None, ""):
        estimated_market_cap = estimate_pump_market_cap(row.get("mint") or row.get("token_mint"), price_value)
        if estimated_market_cap is not None:
            market_cap = estimated_market_cap
            market_cap_estimated = True

    return {
        "time": row.get("time") or row.get("timestamp"),
        "age_seconds": age_seconds(row.get("time") or row.get("timestamp")),
        "mint": row.get("mint") or row.get("token_mint"),
        "source": row.get("source"),
        "context": context,
        "status": status,
        "name": first_non_empty(row.get("name"), market_info.get("name")),
        "symbol": first_non_empty(row.get("symbol"), market_info.get("symbol")),
        "image_url": safe_image_url(
            first_non_empty(
                row.get("image_url"),
                row.get("image"),
                row.get("logoURI"),
                market_info.get("image_url"),
                market_info.get("image"),
                market_info.get("logoURI"),
                market_info.get("logo_uri"),
            )
        ),
        "price": price_value,
        "market_cap": market_cap,
        "market_cap_estimated": market_cap_estimated,
        "liquidity": first_non_empty(row.get("liquidity"), market_info.get("liquidity")),
        "volume": first_non_empty(row.get("volume"), market_info.get("volume")),
        "tx_count": tx_count,
        "holder_count": first_non_empty(
            row.get("holder_count"),
            market_info.get("holder_count"),
            market_info.get("holders"),
            holder_metrics.get("holder_count"),
        ),
        "wallet_count": row.get("wallet_count"),
        "weighted_wallet_score": row.get("weighted_wallet_score"),
        "total_score": row.get("total_score"),
        "edge_score": row.get("edge_score"),
        "risk_label": row.get("risk_label"),
        "token_mechanics_risk": row.get("token_mechanics_risk"),
        "should_trade": should_trade,
        "reasons": reasons[:8],
        "url": first_non_empty(row.get("url"), market_info.get("url")),
    }


def build_candidate_feed_payload(limit=80):
    rows = fetch_snapshot_rows(limit=min(max(int(limit) * 5, int(limit)), 1000), newest_first=True)
    items = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        context = row.get("context")
        mint = row.get("mint") or row.get("token_mint")
        if context not in CANDIDATE_CONTEXTS or not mint or mint in seen:
            continue
        seen.add(mint)
        items.append(compact_candidate_snapshot(row))
    return {
        "generated_at": time.time(),
        "source": "token_snapshots",
        "live_execution_locked": True,
        "count": len(items),
        "items": items,
    }


def compact_event_row(row, metadata=None):
    row = row if isinstance(row, dict) else {}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    timestamp = first_non_empty(row.get("time"), payload.get("time"), payload.get("timestamp"))
    event_type = first_non_empty(row.get("event_type"), row.get("type"), payload.get("type"))
    mint = first_non_empty(row.get("mint"), row.get("token_mint"), payload.get("mint"), payload.get("token_mint"))
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "time": timestamp,
        "age_seconds": age_seconds(timestamp),
        "type": str(event_type or "").lower() or "event",
        "wallet": first_non_empty(row.get("wallet"), payload.get("wallet")),
        "mint": mint,
        "name": first_non_empty(row.get("name"), payload.get("name"), metadata.get("name")),
        "symbol": first_non_empty(row.get("symbol"), payload.get("symbol"), metadata.get("symbol")),
        "image_url": safe_image_url(first_non_empty(row.get("image_url"), payload.get("image_url"), metadata.get("image_url"))),
        "amount": first_non_empty(row.get("amount"), payload.get("amount")),
        "price": first_non_empty(row.get("price"), payload.get("price"), metadata.get("price")),
        "market_cap": first_non_empty(row.get("market_cap"), payload.get("market_cap"), metadata.get("market_cap")),
        "liquidity": first_non_empty(row.get("liquidity"), payload.get("liquidity"), metadata.get("liquidity")),
        "tx_count": first_non_empty(row.get("tx_count"), payload.get("tx_count"), metadata.get("tx_count")),
        "holder_count": first_non_empty(row.get("holder_count"), payload.get("holder_count"), metadata.get("holder_count")),
        "wallet_quality_score": first_non_empty(row.get("wallet_quality_score"), payload.get("wallet_quality_score")),
        "wallet_performance_score": first_non_empty(row.get("wallet_performance_score"), payload.get("wallet_performance_score")),
        "combined_wallet_score": first_non_empty(row.get("combined_wallet_score"), payload.get("combined_wallet_score")),
        "source": first_non_empty(row.get("source"), payload.get("source"), "events"),
    }


def build_event_feed_payload(limit=120):
    rows = fetch_event_rows(limit=limit)
    mints = [first_non_empty(row.get("mint"), row.get("token_mint"), (row.get("payload") or {}).get("mint")) for row in rows if isinstance(row, dict)]
    metadata = fetch_event_metadata(mints)
    missing = [mint for mint in mints if mint and not (metadata.get(mint) or {}).get("symbol") and not (metadata.get(mint) or {}).get("image_url")]
    metadata.update(fetch_rpc_asset_metadata(missing))
    items = [compact_event_row(row, metadata.get(first_non_empty(row.get("mint"), row.get("token_mint"), (row.get("payload") or {}).get("mint")))) for row in rows]
    return {
        "generated_at": time.time(),
        "source": "events",
        "live_execution_locked": True,
        "count": len(items),
        "items": items,
    }


def pct_change(first, last):
    first = safe_float(first)
    last = safe_float(last)
    if first <= 0 or last <= 0:
        return None
    return ((last - first) / first) * 100


def first_positive_value(rows, key):
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = safe_float(row.get(key))
        if value > 0:
            return value
    return None


def latest_positive_value(rows, key):
    for row in reversed(rows or []):
        if not isinstance(row, dict):
            continue
        value = safe_float(row.get(key))
        if value > 0:
            return value
    return None


def build_snapshot_trend(snapshots):
    latest = snapshots[-1] if snapshots else {}
    latest_time = safe_float(latest.get("time") or latest.get("timestamp"), None) if isinstance(latest, dict) else None
    latest_age = max(0, time.time() - latest_time) if latest_time else None
    return {
        "price_change_pct": pct_change(first_positive_value(snapshots, "price"), latest_positive_value(snapshots, "price")),
        "liquidity_change_pct": pct_change(first_positive_value(snapshots, "liquidity"), latest_positive_value(snapshots, "liquidity")),
        "latest_source": latest.get("source") if isinstance(latest, dict) else None,
        "latest_context": latest.get("context") if isinstance(latest, dict) else None,
        "latest_age_seconds": latest_age,
    }


def normalize_chart_metric(metric):
    metric = str(metric or "price").strip().lower()
    return metric if metric in CHART_METRICS else "price"


def chart_snapshots_for_metric(snapshots, metric):
    if metric == "price":
        return snapshots
    normalized = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        item = dict(snapshot)
        value = snapshot.get(metric)
        if metric == "market_cap" and value in (None, ""):
            value = estimate_pump_market_cap(snapshot.get("mint") or snapshot.get("token_mint"), snapshot.get("price"))
        item["market_cap"] = value
        normalized.append(item)
    return normalized


def build_chart_quality_payload(snapshots, candles, metric):
    values = []
    source_contexts = {}
    first_time = None
    last_time = None
    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue
        value = safe_float(snapshot.get(metric), None)
        if value is None and metric == "price":
            value = safe_float(snapshot.get("market_cap"), None)
        if value is not None and value > 0:
            values.append(round(value, 12))
        timestamp = safe_float(snapshot.get("time") or snapshot.get("timestamp"), None)
        if timestamp:
            first_time = timestamp if first_time is None else min(first_time, timestamp)
            last_time = timestamp if last_time is None else max(last_time, timestamp)
        source = str(snapshot.get("source") or "unknown")
        context = str(snapshot.get("context") or "unknown")
        key = f"{source}:{context}"
        source_contexts[key] = source_contexts.get(key, 0) + 1
    distinct_value_count = len(set(values))
    warning = ""
    if candles and distinct_value_count <= 1:
        warning = "Chart is based on repeated sampled quote values, not live swap ticks."
    elif candles and sum(1 for candle in candles if candle.get("synthetic")) > len(candles) * 0.8:
        warning = "Most candles are synthetic one-sample quote candles. Swap/tick stream is not active."
    return {
        "sample_kind": "sampled_quote",
        "source_contexts": source_contexts,
        "distinct_value_count": distinct_value_count,
        "first_time": first_time,
        "last_time": last_time,
        "warning": warning,
        "trade_stream_active": False,
    }


def build_swap_tick_quality_payload(ticks, candles):
    sources = {}
    first_time = None
    last_time = None
    for tick in ticks or []:
        if not isinstance(tick, dict):
            continue
        timestamp = safe_float(tick.get("time") or tick.get("timestamp"), None)
        if timestamp:
            first_time = timestamp if first_time is None else min(first_time, timestamp)
            last_time = timestamp if last_time is None else max(last_time, timestamp)
        source = str(tick.get("source") or "unknown")
        sources[source] = sources.get(source, 0) + 1
    return {
        "sample_kind": "swap_tick",
        "source_contexts": {f"{source}:swap_tick": count for source, count in sources.items()},
        "distinct_value_count": len(set(round(safe_float(tick.get("price"), 0), 12) for tick in ticks or [] if safe_float(tick.get("price"), 0) > 0)),
        "first_time": first_time,
        "last_time": last_time,
        "warning": "" if candles else "No valid swap tick candles were available.",
        "trade_stream_active": True,
    }


def build_candles_payload(mint=None, limit=300, allow_all=False, metric="price", interval_seconds=1):
    metric = normalize_chart_metric(metric)
    output_limit = bounded_int(limit, 300, minimum=20, maximum=500)
    if not mint and not allow_all:
        return {
            "generated_at": time.time(),
            "mint": None,
            "metric": metric,
            "snapshot_count": 0,
            "candles": [],
            "latest_snapshot": None,
            "detail": "mint query parameter required for desktop chart requests",
        }
    ticks = fetch_swap_tick_rows(mint=mint, limit=output_limit)
    if ticks:
        snapshots = fetch_snapshot_rows(mint=mint, limit=min(50, output_limit))
        candle_rows = chart_snapshots_for_metric(ticks, metric)
        value_key = "price" if metric == "price" else "market_cap"
        candles = build_candles(
            candle_rows,
            interval_seconds=max(1, int(interval_seconds or 1)),
            value_key=value_key,
            carry_forward_open=False,
            max_candles=output_limit,
        )
        quality = build_swap_tick_quality_payload(ticks, candles)
        return {
            "generated_at": time.time(),
            "mint": mint,
            "metric": metric,
            "interval_seconds": max(1, int(interval_seconds or 1)),
            "snapshot_count": len(snapshots),
            "tick_count": len(ticks),
            "candles": [{key: json_safe(value) for key, value in candle.items()} for candle in candles],
            "latest_snapshot": snapshots[-1] if snapshots else None,
            "latest_tick": ticks[-1] if ticks else None,
            "sample_kind": quality["sample_kind"],
            "quality": quality,
        }

    snapshots = fetch_snapshot_rows(mint=mint, limit=output_limit)
    candle_rows = chart_snapshots_for_metric(snapshots, metric)
    value_key = "price" if metric == "price" else "market_cap"
    candles = build_candles(
        candle_rows,
        interval_seconds=max(1, int(interval_seconds or 1)),
        value_key=value_key,
        carry_forward_open=(metric in {"market_cap", "price"}),
        max_candles=output_limit,
    )
    quality = build_chart_quality_payload(snapshots, candles, metric)
    return {
        "generated_at": time.time(),
        "mint": mint,
        "metric": metric,
        "interval_seconds": max(1, int(interval_seconds or 1)),
        "snapshot_count": len(snapshots),
        "tick_count": 0,
        "candles": [{key: json_safe(value) for key, value in candle.items()} for candle in candles],
        "latest_snapshot": snapshots[-1] if snapshots else None,
        "sample_kind": quality["sample_kind"],
        "quality": quality,
    }


def summarize_list_payload(source_name, data, key=None, limit=100):
    rows = data.get(key, []) if key and isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = []
    return {
        "generated_at": time.time(),
        "source": source_name,
        "count": len(rows),
        "items": rows[:limit],
        "live_execution_locked": True,
    }


def build_alerts_payload(live_state=None, limit=100):
    state = live_state if live_state is not None else read_json(LIVE_STATE_FILE, {"alerts": []})
    live_rows = state.get("alerts", []) if isinstance(state, dict) and isinstance(state.get("alerts"), list) else []
    sqlite_rows = fetch_alert_rows(limit=limit)
    if sqlite_rows:
        rows = [row["payload"] for row in sqlite_rows if isinstance(row.get("payload"), dict)]
        payload = summarize_list_payload("sqlite_alerts", rows, limit=limit)
        payload["source_detail"] = f"{relative_display_path(DB_FILE)}:alerts"
        payload["fallback_source"] = "live_state_alerts"
        payload["fallback_reason"] = None
    else:
        payload = summarize_list_payload("live_state_alerts", state, key="alerts", limit=limit)
        payload["source_detail"] = str(LIVE_STATE_FILE.relative_to(ROOT))
        payload["fallback_source"] = "sqlite_alerts"
        payload["fallback_reason"] = "sqlite_alerts_empty"
    sqlite_alert_count = safe_sqlite_counts().get("alerts", 0)
    payload.update({
        "source_contract": {
            "alerts": payload["source"],
            "alert_mirror": "live_state_alerts" if payload["source"] == "sqlite_alerts" else "sqlite_alerts",
            "decisions": "sqlite_decision_records",
        },
        "sqlite_mirror_source": "sqlite_alerts",
        "sqlite_mirror_detail": f"{relative_display_path(DB_FILE)}:alerts",
        "sqlite_mirror_count": sqlite_alert_count,
        "live_state_count": len(live_rows),
        "mirror_warning": None,
    })
    if sqlite_alert_count != len(live_rows) and payload.get("fallback_reason") != "sqlite_alerts_empty":
        payload["mirror_warning"] = (
            f"live_state_alerts count {len(live_rows)} differs from sqlite_alerts count {sqlite_alert_count}"
        )
    return payload


def tracked_wallet_labels(rows):
    labels = {}
    if not isinstance(rows, list):
        return labels
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = row.get("trackedWalletAddress") or row.get("wallet") or row.get("address")
        if not wallet:
            continue
        labels[wallet] = {
            "name": row.get("name") or row.get("label") or "",
            "emoji": row.get("emoji") or "",
            "groups": row.get("groups") if isinstance(row.get("groups"), list) else [],
        }
    return labels


def wallet_row(wallet, record, labels):
    record = record if isinstance(record, dict) else {}
    label = labels.get(wallet, {})
    entries = int(safe_float(record.get("paper_entries"), 0) or 0)
    wins = int(safe_float(record.get("wins"), 0) or 0)
    win_rate = (wins / entries * 100) if entries else None
    score = safe_float(record.get("score"), 50)
    return {
        "wallet": wallet,
        "name": label.get("name") or wallet[:8],
        "emoji": label.get("emoji") or "",
        "groups": label.get("groups") or [],
        "signals": int(safe_float(record.get("signals"), 0) or 0),
        "paper_entries": entries,
        "wins": wins,
        "losses": int(safe_float(record.get("losses"), 0) or 0),
        "win_rate_pct": win_rate,
        "total_pnl": safe_float(record.get("total_pnl"), 0),
        "avg_pnl": safe_float(record.get("avg_pnl"), 0),
        "best_pnl": safe_float(record.get("best_pnl"), 0),
        "worst_pnl": safe_float(record.get("worst_pnl"), 0),
        "score": score,
        "label": wallet_performance_label(score),
        "last_seen": record.get("last_seen"),
        "last_seen_age_seconds": age_seconds(record.get("last_seen")),
    }


def wallet_performance_label(score):
    score = safe_float(score, 50)
    if score >= 85:
        return "ELITE_PERFORMER"
    if score >= 70:
        return "GOOD_PERFORMER"
    if score >= 50:
        return "NEUTRAL_PERFORMER"
    if score >= 30:
        return "WEAK_PERFORMER"
    return "BAD_PERFORMER"


def summarize_wallet_signal(signal):
    signal = signal if isinstance(signal, dict) else {}
    return {
        "time": signal.get("time"),
        "mint": signal.get("mint"),
        "wallets": listify(signal.get("wallets"))[:12],
        "signal_type": signal.get("signal_type"),
        "score": signal.get("score"),
        "should_trade": signal.get("should_trade"),
        "token_age_seconds": signal.get("token_age_seconds"),
    }


def trade_mint(row):
    row = row if isinstance(row, dict) else {}
    return row.get("mint") or row.get("token_mint") or row.get("tokenMint") or ""


def summarize_wallet_trade(row, source):
    row = row if isinstance(row, dict) else {}
    return {
        "source": source,
        "mint": trade_mint(row),
        "symbol": row.get("symbol") or row.get("name"),
        "status": row.get("status") or source,
        "pnl_pct": first_present(row.get("total_pnl_pct"), row.get("pnl_pct")),
        "pnl": first_present(row.get("total_pnl"), row.get("pnl")),
        "reason": row.get("entry_reason") or row.get("exit_reason") or row.get("close_reason") or row.get("failure_reason") or row.get("reason"),
        "wallets": listify(row.get("wallets"))[:12],
    }


def canonical_trade_state(state=None):
    paper = state.get("paper") if isinstance(state, dict) and isinstance(state.get("paper"), dict) else None
    if paper is not None:
        return {
            "source": "state_paper",
            "open_trades": paper.get("open_trades", []) if isinstance(paper.get("open_trades"), list) else [],
            "closed_trades": paper.get("closed_trades", []) if isinstance(paper.get("closed_trades"), list) else [],
            "failed_trades": paper.get("failed_trades", []) if isinstance(paper.get("failed_trades"), list) else [],
        }
    trade_payload = build_trades_payload()
    return {
        "source": trade_payload.get("source") or "unknown",
        "open_trades": trade_payload.get("open_trades", []) if isinstance(trade_payload.get("open_trades"), list) else [],
        "closed_trades": trade_payload.get("closed_trades", []) if isinstance(trade_payload.get("closed_trades"), list) else [],
        "failed_trades": trade_payload.get("failed_trades", []) if isinstance(trade_payload.get("failed_trades"), list) else [],
    }


def build_wallets_payload(state=None, limit=80):
    state = state or read_state_files()
    performance = state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {}
    tracked = state.get("tracked_wallets") if isinstance(state.get("tracked_wallets"), list) else []
    labels = tracked_wallet_labels(tracked)
    wallet_records = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    rows = [wallet_row(wallet, record, labels) for wallet, record in wallet_records.items()]
    for wallet in labels:
        if wallet not in wallet_records:
            rows.append(wallet_row(wallet, {}, labels))
    rows.sort(key=lambda row: (
        row["score"],
        row["paper_entries"],
        row["signals"],
        -(row["last_seen_age_seconds"] or 10**9),
    ), reverse=True)
    signals = performance.get("signals") if isinstance(performance.get("signals"), list) else []
    return {
        "generated_at": time.time(),
        "source": "wallet_performance_json",
        "source_detail": str(WALLET_PERFORMANCE_FILE.relative_to(ROOT)),
        "source_contract": {
            "performance": "wallet_performance_json",
            "behavior": "wallet_behavior_json",
            "tracked_wallets": "tracked_wallets_json",
            "paper_watch_wallets": "paper_watch_wallets_json",
            "events": "sqlite_events_raw_activity",
        },
        "live_execution_locked": True,
        "tracked_count": len(labels),
        "performance_count": len(wallet_records),
        "wallets": rows[:limit],
        "recent_signals": [summarize_wallet_signal(signal) for signal in signals[:30]],
    }


def build_candidate_wallets_payload(state=None, limit=80):
    state = state or read_state_files()
    data = state.get("candidate_wallets") if isinstance(state.get("candidate_wallets"), dict) else {}
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    reviewed = apply_review_policy(data)
    return {
        "generated_at": data.get("generated_at") or time.time(),
        "source": data.get("source") or "wallet_discovery",
        "mode": data.get("mode") or "WATCH_ONLY_REVIEW",
        "read_only": True,
        "live_execution_locked": True,
        "summary": data.get("summary") if isinstance(data.get("summary"), dict) else {
            "candidate_wallets": len(candidates),
            "untracked_wallets": len([row for row in candidates if isinstance(row, dict) and not row.get("already_tracked")]),
            "tracked_wallets": len([row for row in candidates if isinstance(row, dict) and row.get("already_tracked")]),
        },
        "source_counts": data.get("source_counts") if isinstance(data.get("source_counts"), dict) else {},
        "review_policy": reviewed.get("review_policy"),
        "review_summary": reviewed.get("review_summary"),
        "count": min(len(candidates), int(limit)),
        "candidates": reviewed.get("candidates", candidates)[:limit],
    }


def build_wallet_lifecycle_payload(state=None, limit=80):
    state = state or read_state_files()
    tracked = normalize_tracked_wallets(state.get("tracked_wallets"))
    paper_watch = state.get("paper_watch_wallets")
    paper_watch_rows = paper_watch.get("wallets", []) if isinstance(paper_watch, dict) else []
    report = build_wallet_lifecycle_report(
        tracked_wallets=tracked,
        paper_watch_wallets=paper_watch_rows,
        candidate_report=state.get("candidate_wallets") if isinstance(state.get("candidate_wallets"), dict) else {"candidates": []},
        performance=state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {"wallets": {}},
        behavior=state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {"wallets": {}},
    )
    rows = report.get("wallets", [])
    return {
        "generated_at": report.get("generated_at") or time.time(),
        "mode": report.get("mode") or "REVIEW_ONLY",
        "read_only": True,
        "live_execution_locked": True,
        "summary": report.get("summary") or {},
        "count": min(len(rows), int(limit)),
        "wallets": rows[:limit],
    }


def build_wallet_quant_payload(state=None, limit=80):
    state = state or read_state_files()
    report = build_wallet_quant_report(
        tracked_wallets=state.get("tracked_wallets", []),
        paper_watch_wallets=state.get("paper_watch_wallets", {"wallets": []}),
        performance=state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {"wallets": {}},
        behavior=state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {"wallets": {}},
    )
    rows = report.get("wallets", [])
    return {
        **report,
        "read_only": True,
        "count": min(len(rows), int(limit)),
        "wallets": rows[:limit],
    }


def build_wallet_replay_review_payload(state=None, limit=80):
    state = state or read_state_files()
    return build_wallet_replay_review(
        state.get("wallet_replay_scorecard") if isinstance(state.get("wallet_replay_scorecard"), dict) else {},
        limit=limit,
    )


def build_wallet_cycle_payload(state=None):
    state = state or read_state_files()
    existing = state.get("wallet_cycle_report")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CYCLE_REPORT_REVIEW_ONLY":
        return {
            **existing,
            "read_only": True,
            "source": "wallet_cycle_report_json",
            "source_detail": str(WALLET_CYCLE_REPORT_FILE.relative_to(ROOT)),
        }
    return {
        **build_wallet_cycle_report(
            tracked_wallets=state.get("tracked_wallets", []),
            paper_watch_wallets=state.get("paper_watch_wallets", {"wallets": []}),
            bad_wallets=read_json(ROOT / "data" / "bad_wallets.json", []),
            candidate_audit=read_json(ROOT / "data" / "wallet_candidate_audit.json", {}),
            wallet_replay_scorecard=state.get("wallet_replay_scorecard") if isinstance(state.get("wallet_replay_scorecard"), dict) else {},
            review_decisions=state.get("wallet_review_decisions", {"decisions": []}),
            wallet_list_update_audit=read_json(ROOT / "data" / "wallet_list_update_audit.json", {"updates": []}),
        ),
        "read_only": True,
        "source": "wallet_cycle_report_computed",
    }


def build_wallet_candidate_audit_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_audit")
    audit = existing if isinstance(existing, dict) else {}
    candidates = audit.get("candidates") if isinstance(audit.get("candidates"), list) else []
    resolved = audit.get("resolved_candidates") if isinstance(audit.get("resolved_candidates"), list) else []
    limited = candidates[: int(limit)]
    stage4_rows = [
        row for row in candidates
        if isinstance(row, dict) and isinstance(row.get("evidence"), dict) and row["evidence"].get("source") == "wallet_stage4_review"
    ]
    return {
        "generated_at": audit.get("generated_at") or time.time(),
        "mode": audit.get("mode") or "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY",
        "read_only": True,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "source": "wallet_candidate_audit_json",
        "source_detail": str(WALLET_CANDIDATE_AUDIT_FILE.relative_to(ROOT)),
        "summary": audit.get("counts") if isinstance(audit.get("counts"), dict) else {},
        "stage4_summary": {
            "stage4_sourced_candidates": len(stage4_rows),
            "stage4_demotion_reviews": len([row for row in stage4_rows if row.get("recommendation_action") == "DEMOTION_REVIEW"]),
            "stage4_risk_reviews": len([row for row in stage4_rows if row.get("recommendation_action") == "RISK_REVIEW_REQUIRED"]),
            "stage4_promotion_reviews": len([row for row in stage4_rows if row.get("recommendation_action") == "PROMOTION_REVIEW"]),
        },
        "count": min(len(candidates), int(limit)),
        "resolved_count": len(resolved),
        "candidates": limited,
        "resolved_candidates": resolved[: int(limit)],
        "operator_note": "Read-only review queue. Wallet-list changes still require an explicit approved decision plus the separate wallet-review apply guard.",
    }


def build_wallet_candidate_decision_prep_payload(state=None, limit=80, selected_wallets=None):
    state = state or read_state_files()
    report = build_wallet_candidate_decision_prep(
        state.get("wallet_candidate_audit", {}),
        selected_wallets=selected_wallets,
        limit=limit,
    )
    return report


def build_wallet_candidate_review_summary_payload(state=None, limit=25):
    state = state or read_state_files()
    decision_prep = build_wallet_candidate_decision_prep(state.get("wallet_candidate_audit", {}), limit=limit)
    return build_wallet_candidate_review_summary(
        state.get("wallet_candidate_audit", {}),
        decision_prep=decision_prep,
        limit=limit,
    )


def build_wallet_candidate_collection_plan_payload(state=None, limit=100):
    state = state or read_state_files()
    return build_wallet_candidate_collection_plan(
        state.get("wallet_candidate_audit", {}),
        limit=limit,
    )


def build_wallet_candidate_collection_batch_payload(state=None, limit=50):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_collection_batch")
    report = existing if isinstance(existing, dict) else {}
    steps = report.get("steps") if isinstance(report.get("steps"), list) else []
    return {
        "generated_at": report.get("generated_at") or time.time(),
        "mode": report.get("mode") or "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY",
        "read_only": True,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "source": "wallet_candidate_collection_batch_report",
        "source_detail": str(WALLET_CANDIDATE_COLLECTION_BATCH_FILE.relative_to(ROOT)),
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "count": min(len(steps), int(limit)),
        "steps": steps[: int(limit)],
        "operator_note": report.get("operator_note") or "Read-only batch report. No wallet-list apply or trading commands are allowed here.",
    }


def build_wallet_candidate_blockers_payload(state=None, limit=50):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_blocker_reducer")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY":
        rows = existing.get("top_blocked_wallets") if isinstance(existing.get("top_blocked_wallets"), list) else []
        return {
            **existing,
            "read_only": True,
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_apply_allowed": False,
            "wallet_list_mutated": False,
            "source": "wallet_candidate_blocker_reducer_json",
            "source_detail": str(WALLET_CANDIDATE_BLOCKER_REDUCER_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "top_blocked_wallets": rows[: int(limit)],
        }
    plan = state.get("wallet_candidate_collection_plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("targets"), list):
        plan = build_wallet_candidate_collection_plan(
            state.get("wallet_candidate_audit", {}),
            limit=max(500, int(limit)),
        )
    report = build_wallet_candidate_blocker_reducer(
        candidate_audit=state.get("wallet_candidate_audit", {}),
        collection_plan=plan,
        collection_batch=state.get("wallet_candidate_collection_batch", {}),
        limit=limit,
    )
    rows = report.get("top_blocked_wallets") if isinstance(report.get("top_blocked_wallets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_blocker_reducer_computed",
        "source_detail": str(WALLET_CANDIDATE_BLOCKER_REDUCER_FILE.relative_to(ROOT)),
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_context_recovery_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_context_recovery")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY":
        rows = existing.get("targets") if isinstance(existing.get("targets"), list) else []
        return {
            **existing,
            "read_only": True,
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_apply_allowed": False,
            "wallet_list_mutated": False,
            "source": "wallet_candidate_context_recovery_queue_json",
            "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "targets": rows[: int(limit)],
        }
    plan = state.get("wallet_candidate_collection_plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("targets"), list):
        plan = build_wallet_candidate_collection_plan(
            state.get("wallet_candidate_audit", {}),
            limit=max(500, int(limit)),
        )
    report = build_wallet_candidate_context_recovery_queue(
        collection_plan=plan,
        blocker_reducer=state.get("wallet_candidate_blocker_reducer", {}),
        limit=limit,
    )
    rows = report.get("targets") if isinstance(report.get("targets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_context_recovery_queue_computed",
        "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_FILE.relative_to(ROOT)),
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_context_recovery_runner_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_context_recovery_runner")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY":
        rows = existing.get("wallets") if isinstance(existing.get("wallets"), list) else []
        return {
            **existing,
            "read_only": True,
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_apply_allowed": False,
            "wallet_list_mutated": False,
            "source": "wallet_candidate_context_recovery_runner_json",
            "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "wallets": rows[: int(limit)],
        }
    report = build_wallet_candidate_context_recovery_report(
        recovery_queue=state.get("wallet_candidate_context_recovery", {}),
        enriched_evidence=state.get("wallet_evidence_enriched_rows", []),
        missing_market_context=state.get("wallet_missing_market_context", {}),
        replay_events=state.get("historical_replay_events", []),
        historical_backfill_records=state.get("historical_backfill_records", []),
        limit=limit,
    )
    rows = report.get("wallets") if isinstance(report.get("wallets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_context_recovery_runner_computed",
        "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_FILE.relative_to(ROOT)),
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_context_recovery_closeout_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_context_recovery_closeout")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY":
        rows = existing.get("wallets") if isinstance(existing.get("wallets"), list) else []
        return {
            **existing,
            "read_only": True,
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_apply_allowed": False,
            "wallet_list_mutated": False,
            "source": "wallet_candidate_context_recovery_closeout_json",
            "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "wallets": rows[: int(limit)],
        }
    runner = state.get("wallet_candidate_context_recovery_runner")
    if not isinstance(runner, dict):
        runner = {}
    report = build_wallet_candidate_context_recovery_closeout(
        recovery_runner=runner,
        limit=limit,
    )
    rows = report.get("wallets") if isinstance(report.get("wallets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_context_recovery_closeout_computed",
        "source_detail": str(WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_FILE.relative_to(ROOT)),
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_quality_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_quality_report")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY":
        rows = existing.get("ranked_candidates") if isinstance(existing.get("ranked_candidates"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_candidate_quality_report_json",
            "source_detail": str(WALLET_CANDIDATE_QUALITY_REPORT_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "ranked_candidates": rows[:limit],
        }
    report = build_wallet_candidate_quality_report(
        candidate_wallets=state.get("candidate_wallets") if isinstance(state.get("candidate_wallets"), dict) else {"candidates": []},
        paper_watch_wallets=state.get("paper_watch_wallets") if isinstance(state.get("paper_watch_wallets"), dict) else {"wallets": []},
        bad_wallets=state.get("bad_wallets", []),
        wallet_behavior=state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {"wallets": {}},
        limit=limit,
    )
    rows = report.get("ranked_candidates") if isinstance(report.get("ranked_candidates"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_quality_report_computed",
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_quality_review_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_quality_review")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY":
        rows = existing.get("shortlist") if isinstance(existing.get("shortlist"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_candidate_quality_review_json",
            "source_detail": str(WALLET_CANDIDATE_QUALITY_REVIEW_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "shortlist": rows[:limit],
        }
    report = build_wallet_candidate_quality_review(
        candidate_quality_report=state.get("wallet_candidate_quality_report") if isinstance(state.get("wallet_candidate_quality_report"), dict) else {},
        wallet_replay_scorecard=state.get("wallet_replay_scorecard") if isinstance(state.get("wallet_replay_scorecard"), dict) else {},
        wallet_outcome_ledger=read_json(ROOT / "data" / "wallet_outcome_ledger.json", {}),
        limit=limit,
    )
    rows = report.get("shortlist") if isinstance(report.get("shortlist"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_quality_review_computed",
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_evidence_plan_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_evidence_plan")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_EVIDENCE_PLAN_REVIEW_ONLY":
        rows = existing.get("coverage_queue") if isinstance(existing.get("coverage_queue"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_candidate_evidence_plan_json",
            "source_detail": str(WALLET_CANDIDATE_EVIDENCE_PLAN_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "coverage_queue": rows[:limit],
        }
    report = build_wallet_candidate_evidence_plan(
        candidate_quality_review=state.get("wallet_candidate_quality_review") if isinstance(state.get("wallet_candidate_quality_review"), dict) else {},
        limit=limit,
    )
    rows = report.get("coverage_queue") if isinstance(report.get("coverage_queue"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_evidence_plan_computed",
        "count": min(len(rows), int(limit)),
    }


def build_wallet_candidate_backfill_targets_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_candidate_backfill_targets")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_CANDIDATE_BACKFILL_TARGETS_REVIEW_ONLY":
        rows = existing.get("targets") if isinstance(existing.get("targets"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_candidate_backfill_targets_json",
            "source_detail": str(WALLET_CANDIDATE_BACKFILL_TARGETS_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "targets": rows[:limit],
        }
    report = build_wallet_candidate_backfill_targets(
        candidate_evidence_plan=state.get("wallet_candidate_evidence_plan") if isinstance(state.get("wallet_candidate_evidence_plan"), dict) else {},
        replay_events=[],
        limit=limit,
    )
    rows = report.get("targets") if isinstance(report.get("targets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_candidate_backfill_targets_computed",
        "count": min(len(rows), int(limit)),
    }


def build_wallet_history_backfill_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_history_backfill")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_HISTORY_BACKFILL_REVIEW_ONLY":
        rows = existing.get("wallets") if isinstance(existing.get("wallets"), list) else []
        evidence = existing.get("evidence_records") if isinstance(existing.get("evidence_records"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_history_backfill_json",
            "source_detail": str(WALLET_HISTORY_BACKFILL_REPORT_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "wallets": rows[:limit],
            "evidence_records": evidence[:limit],
        }
    report = build_wallet_history_backfill_report(
        backfill_targets=state.get("wallet_candidate_backfill_targets") if isinstance(state.get("wallet_candidate_backfill_targets"), dict) else {},
        execute=False,
        max_wallets=limit,
    )
    rows = report.get("wallets") if isinstance(report.get("wallets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_history_backfill_dry_run_computed",
        "count": min(len(rows), int(limit)),
    }


def build_wallet_evidence_enrichment_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_evidence_enrichment")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_EVIDENCE_ENRICHMENT_REVIEW_ONLY":
        rows = existing.get("evidence_records") if isinstance(existing.get("evidence_records"), list) else []
        return {
            **existing,
            "read_only": True,
            "source": "wallet_evidence_enrichment_json",
            "source_detail": str(WALLET_EVIDENCE_ENRICHMENT_REPORT_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "evidence_records": rows[:limit],
        }
    report = build_wallet_evidence_enrichment_report(
        evidence_records=[],
        market_snapshots=[],
        replay_events=[],
    )
    return {
        **report,
        "read_only": True,
        "source": "wallet_evidence_enrichment_empty_computed",
        "count": 0,
    }


def build_wallet_missing_market_context_payload(state=None, limit=80):
    state = state or read_state_files()
    existing = state.get("wallet_missing_market_context")
    if isinstance(existing, dict) and existing.get("mode") == "WALLET_MISSING_MARKET_CONTEXT_REVIEW_ONLY":
        rows = existing.get("targets") if isinstance(existing.get("targets"), list) else []
        return {
            **existing,
            "read_only": True,
            "live_execution_locked": True,
            "source": "wallet_missing_market_context_report_json",
            "source_detail": str(WALLET_MISSING_MARKET_CONTEXT_REPORT_FILE.relative_to(ROOT)),
            "count": min(len(rows), int(limit)),
            "targets": rows[:limit],
        }
    report = build_wallet_missing_market_context_targets(
        wallet_evidence_enrichment=state.get("wallet_evidence_enrichment") if isinstance(state.get("wallet_evidence_enrichment"), dict) else {},
        limit=limit,
    )
    rows = report.get("targets") if isinstance(report.get("targets"), list) else []
    return {
        **report,
        "read_only": True,
        "source": "wallet_missing_market_context_computed",
        "count": min(len(rows), int(limit)),
    }


def build_evidence_layer_completion_payload(state=None):
    state = state or read_state_files()
    existing = state.get("evidence_layer_completion")
    if isinstance(existing, dict) and existing.get("mode") == "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY":
        return {
            **existing,
            "read_only": True,
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_apply_allowed": False,
            "wallet_list_mutated": False,
            "source": "evidence_layer_completion_json",
            "source_detail": str(EVIDENCE_LAYER_COMPLETION_REPORT_FILE.relative_to(ROOT)),
        }
    report = build_evidence_layer_completion_report(
        wallet_evidence_readiness=state.get("wallet_evidence_readiness") if isinstance(state.get("wallet_evidence_readiness"), dict) else {},
        wallet_evidence_scorecard=state.get("wallet_evidence_scorecard") if isinstance(state.get("wallet_evidence_scorecard"), dict) else {},
        recovery_closeout=state.get("wallet_candidate_context_recovery_closeout") if isinstance(state.get("wallet_candidate_context_recovery_closeout"), dict) else {},
    )
    return {
        **report,
        "read_only": True,
        "source": "evidence_layer_completion_computed",
        "source_detail": str(EVIDENCE_LAYER_COMPLETION_REPORT_FILE.relative_to(ROOT)),
    }


def build_wallet_detail_payload(wallet, state=None, limit=40):
    state = state or read_state_files()
    wallet = str(wallet or "").strip()
    performance = state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {}
    tracked = state.get("tracked_wallets") if isinstance(state.get("tracked_wallets"), list) else []
    labels = tracked_wallet_labels(tracked)
    wallet_records = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    record = wallet_records.get(wallet, {})
    row = wallet_row(wallet, record, labels)
    signals = [
        summarize_wallet_signal(signal)
        for signal in performance.get("signals", [])
        if isinstance(signal, dict) and wallet in listify(signal.get("wallets"))
    ]
    paper = canonical_trade_state(state)
    behavior = state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {}
    behavior_wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    behavior_row = behavior_wallets.get(wallet) if isinstance(behavior_wallets.get(wallet), dict) else {}
    trade_rows = []
    for source in ("open_trades", "closed_trades", "failed_trades"):
        for trade in paper.get(source, []) if isinstance(paper.get(source), list) else []:
            if isinstance(trade, dict) and wallet in listify(trade.get("wallets")):
                trade_rows.append(summarize_wallet_trade(trade, source))
    return {
        "generated_at": time.time(),
        "source": "wallet_detail_composed",
        "source_contract": {
            "performance": "wallet_performance_json",
            "behavior": "wallet_behavior_json",
            "tracked_wallets": "tracked_wallets_json",
            "paper_trades": "sqlite_trades_or_json_fallback",
        },
        "read_only": True,
        "live_execution_locked": True,
        "wallet": row,
        "recent_signals": signals[:limit],
        "paper_trades": trade_rows[:limit],
        "trade_source": paper.get("source"),
        "behavior": {
            "labels": behavior_row.get("labels") if isinstance(behavior_row.get("labels"), list) else [],
            "rolling": behavior_row.get("rolling") if isinstance(behavior_row.get("rolling"), dict) else {},
        },
        "postmortem": behavior_row.get("postmortem") if isinstance(behavior_row.get("postmortem"), dict) else {},
    }


def pick_settings(settings):
    settings = settings if isinstance(settings, dict) else {}
    keys = (
        "mode",
        "sniper_score_threshold",
        "confirmation_score_threshold",
        "safe_score_threshold",
        "jupiter_prescore_threshold",
        "weighted_wallet_trigger",
        "weighted_wallet_strong_bonus",
        "cluster_threshold",
        "cluster_window",
        "confirmation_min_launch_age_seconds",
        "confirmation_max_launch_age_seconds",
        "confirmation_min_liquidity_usd",
        "confirmation_require_momentum",
        "confirmation_min_wallets",
        "confirmation_min_repeated_buys",
        "paper_base_position_usd",
        "paper_medium_position_usd",
        "paper_strong_position_usd",
        "paper_exploration_enabled",
        "paper_exploration_score_threshold",
        "paper_exploration_min_edge_score",
        "paper_exploration_size_usd",
        "paper_exploration_auto_pause_enabled",
        "paper_exploration_auto_pause_min_closed",
        "paper_exploration_auto_pause_max_avg_pnl_pct",
        "paper_exploration_auto_pause_max_win_rate_pct",
        "market_radar_enabled",
        "market_radar_interval_seconds",
        "market_radar_max_candidates_per_cycle",
        "market_radar_scan_candidates_per_cycle",
        "market_radar_max_entries_per_cycle",
        "market_radar_max_quotes_per_cycle",
        "market_radar_quote_cooldown_seconds",
        "market_radar_mint_cooldown_seconds",
        "market_radar_position_size_usd",
        "market_radar_min_score",
        "market_radar_min_liquidity_usd",
        "market_radar_min_market_cap_usd",
        "market_radar_max_market_cap_usd",
        "market_radar_min_m5_tx_count",
        "market_radar_min_h1_volume_usd",
        "market_radar_min_buy_ratio",
        "wallet_main_quality_gate_enabled",
        "wallet_main_min_liquidity_usd",
        "wallet_main_min_market_cap_usd",
        "wallet_main_solo_min_score",
        "wallet_main_solo_min_wallet_quality",
        "wallet_main_two_wallet_min_avg_quality",
        "wallet_main_two_wallet_min_max_quality",
        "wallet_main_max_rapid_flips",
        "strategy_guard_enabled",
    )
    return {key: settings.get(key) for key in keys if key in settings}


def build_operator_config_payload(state=None):
    state = state or read_state_files()
    settings = load_bot_settings()
    runtime = summarize_runtime(state.get("runtime") or DEFAULT_STATUS.copy())
    return {
        "generated_at": time.time(),
        "read_only": True,
        "live_execution_locked": True,
        "selected_token_refresh_ms": 1000,
        "overview_refresh_ms": 7000,
        "strategy": pick_settings(settings),
        "mode_blocks": {
            "sniper": settings.get("sniper") if isinstance(settings.get("sniper"), dict) else {},
            "confirmation": settings.get("confirmation") if isinstance(settings.get("confirmation"), dict) else {},
            "safe": settings.get("safe") if isinstance(settings.get("safe"), dict) else {},
        },
        "runtime": runtime,
        "providers": cached_provider_health(),
        "safety": {
            "paper_first": True,
            "auto_sell_enabled": False,
            "metadata_mutations_enabled": True,
            "execution_mutations_enabled": False,
            "execution_routes_enabled": False,
        },
    }


def tail_file(path, max_lines=80, max_chars=12000):
    path = Path(path)
    if not path.exists() or not path.is_file():
        return []
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_chars))
            chunk = handle.read(max_chars).decode("utf-8", errors="replace")
    except Exception as exc:
        return [f"Unable to read {path.name}: {exc}"]
    lines = chunk.splitlines()
    return [redact_secrets(line)[-500:] for line in lines[-max_lines:]]


def build_logs_payload(limit=60):
    logs = {}
    for name, path in LOG_FILES.items():
        logs[name] = {
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "lines": tail_file(path, max_lines=limit),
        }
    return {
        "generated_at": time.time(),
        "read_only": True,
        "live_execution_locked": True,
        "logs": logs,
    }


def build_trades_payload():
    sqlite_trades = fetch_trade_rows(limit=500)
    if sqlite_trades:
        grouped = group_trade_rows(sqlite_trades)
        return {
            "generated_at": time.time(),
            "source": "sqlite_trades",
            "live_execution_locked": True,
            **grouped,
        }
    data, source = load_paper_trade_state()
    return {
        "generated_at": time.time(),
        "source": source["source"],
        "source_detail": source["source_detail"],
        "fallback_source": source["fallback_source"],
        "fallback_reason": source["fallback_reason"],
        "mirror_warning": source.get("mirror_warning"),
        "sqlite_counts": source.get("sqlite_counts"),
        "json_counts": source.get("json_counts"),
        "source_contract": {
            "trades": source["source"],
            "decisions": "sqlite_decision_records",
            "snapshots": "sqlite_token_snapshots",
        },
        "live_execution_locked": True,
        "open_trades": data.get("open_trades", []) if isinstance(data, dict) else [],
        "closed_trades": data.get("closed_trades", []) if isinstance(data, dict) else [],
        "failed_trades": data.get("failed_trades", []) if isinstance(data, dict) else [],
    }


def fetch_trade_rows(limit=500):
    if not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT mint, status, entry_time, close_time, pnl, pnl_pct, reason, payload_json
            FROM trades
            ORDER BY COALESCE(close_time, entry_time, 0) DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    trades = []
    for row in rows:
        payload = parse_payload_json(row["payload_json"])
        if not isinstance(payload, dict):
            payload = {}
        trade = {
            **payload,
            "mint": payload.get("mint") or payload.get("token_mint") or row["mint"],
            "token_mint": payload.get("token_mint") or payload.get("mint") or row["mint"],
            "status": payload.get("status") or row["status"],
            "entry_time": payload.get("entry_time") or row["entry_time"],
            "close_time": payload.get("close_time") or row["close_time"],
            "total_pnl": payload.get("total_pnl", payload.get("pnl", row["pnl"])),
            "total_pnl_pct": payload.get("total_pnl_pct", payload.get("pnl_pct", row["pnl_pct"])),
            "reason": payload.get("reason") or payload.get("entry_reason") or row["reason"],
        }
        trades.append(trade)
    return trades


def group_trade_rows(rows):
    grouped = {"open_trades": [], "closed_trades": [], "failed_trades": []}
    for trade in rows:
        status = str(trade.get("status") or "").lower()
        if status == "closed":
            grouped["closed_trades"].append(trade)
        elif status in ("failed", "error", "rejected"):
            grouped["failed_trades"].append(trade)
        else:
            grouped["open_trades"].append(trade)
    return grouped


def json_response(payload, status=HTTPStatus.OK):
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    return status, "application/json; charset=utf-8", body


def text_response(message, status=HTTPStatus.NOT_FOUND):
    return status, "text/plain; charset=utf-8", message.encode("utf-8")


def safe_route_request(method, raw_path, body=None, headers=None):
    try:
        return route_request(method, raw_path, body, headers)
    except Exception:
        return json_response({
            "error": "Internal desktop API error",
            "live_execution_locked": True,
        }, HTTPStatus.INTERNAL_SERVER_ERROR)


def static_response(path):
    if path in ("", "/"):
        file_path = STATIC_ROOT / "index.html"
    else:
        clean = path.lstrip("/")
        file_path = (STATIC_ROOT / clean).resolve()
        try:
            file_path.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            return text_response("Forbidden", HTTPStatus.FORBIDDEN)
    if not file_path.exists() or not file_path.is_file():
        return text_response("Not found", HTTPStatus.NOT_FOUND)
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    body = file_path.read_bytes()
    if file_path == STATIC_ROOT / "index.html" and DESKTOP_API_TOKEN:
        token_script = (
            "\n<script>"
            f"window.__MTP_API_TOKEN = {json.dumps(DESKTOP_API_TOKEN)};"
            "</script>\n"
        ).encode("utf-8")
        body = body.replace(b"</head>", token_script + b"</head>")
    return HTTPStatus.OK, content_type, body


def json_error(message, status=HTTPStatus.BAD_REQUEST):
    return json_response({
        "error": str(message),
        "live_execution_locked": True,
    }, status)


def parse_json_body(body):
    if body in (None, b"", ""):
        return {}
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def update_protected_amount_metadata(payload):
    mint = str(payload.get("mint") or payload.get("token_mint") or "").strip()
    wallet = str(payload.get("wallet") or "").strip()
    result = {"item": None}

    def updater(rows):
        updated_rows = apply_manual_amount_to_watchlist(
            rows,
            mint=mint,
            wallet=wallet,
            token_amount=payload.get("amount"),
            token_decimals=payload.get("decimals"),
            token_amount_raw=payload.get("raw"),
            test_amount=bool(payload.get("test")),
        )
        for item in updated_rows:
            if isinstance(item, dict) and item.get("token_mint") == mint and (item.get("wallet") or "") == wallet:
                result["item"] = item
                break
        return updated_rows

    locked_update_json(WATCHLIST_FILE, [], updater)
    return {
        "generated_at": time.time(),
        "mode": "PROTECTED_METADATA_ONLY",
        "live_execution_locked": True,
        "auto_sell_enabled": False,
        "execution_routes_enabled": False,
        "item": result["item"] or {},
        "detail": "Protected-position amount metadata updated. No live trade or sell route was executed.",
    }


def add_protected_token_payload(payload):
    mint = str(payload.get("mint") or payload.get("token_mint") or "").strip()
    wallet = str(payload.get("wallet") or "").strip()
    if not mint:
        raise ValueError("Token mint is required.")
    if len(mint) < 32:
        raise ValueError("Token mint looks too short.")
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    requested_auto_sell = bool(payload.get("requested_auto_sell"))
    alert_only = payload.get("alert_only")
    if alert_only is None:
        alert_only = True
    item = {
        "token_mint": mint,
        "mint": mint,
        "wallet": wallet,
        "status": "WATCHING",
        "alert_level": "watching",
        "risk_level": "UNKNOWN",
        "reason": "Added from desktop Protection tab",
        "auto_sell": False,
        "requested_auto_sell": requested_auto_sell,
        "alert_only": bool(alert_only),
        "external_position": bool(payload.get("external_position")),
        "exit_priority": str(payload.get("exit_priority") or ""),
        "live_action_allowed": False,
        "created_at": now,
        "last_update": now,
        "source": "desktop_protection_form",
    }
    if payload.get("amount") not in (None, "") or payload.get("raw") not in (None, ""):
        item.update(build_manual_amount_patch(
            token_amount=payload.get("amount"),
            token_decimals=payload.get("decimals"),
            token_amount_raw=payload.get("raw"),
            test_amount=bool(payload.get("test")),
        ))
    result = {"item": item, "action": "added"}

    def updater(rows):
        rows = rows if isinstance(rows, list) else []
        next_rows = []
        updated = False
        for existing in rows:
            if not isinstance(existing, dict):
                continue
            if existing.get("token_mint") == mint and (existing.get("wallet") or "") == wallet:
                merged = dict(existing)
                merged.update(item)
                merged["created_at"] = existing.get("created_at") or item["created_at"]
                next_rows.append(merged)
                result["item"] = merged
                result["action"] = "updated"
                updated = True
            else:
                next_rows.append(existing)
        if not updated:
            next_rows.append(item)
        return next_rows

    locked_update_json(WATCHLIST_FILE, [], updater)
    return {
        "generated_at": time.time(),
        "mode": "PROTECTED_WATCH_ONLY",
        "live_execution_locked": True,
        "auto_sell_enabled": False,
        "execution_routes_enabled": False,
        "action": result["action"],
        "item": result["item"],
        "detail": "Protected token added for watchdog review. No live trade or auto-sell was enabled.",
    }


def summarize_wallet_review_decisions(data):
    decisions = data.get("decisions") if isinstance(data, dict) and isinstance(data.get("decisions"), list) else []
    approved = [row for row in decisions if isinstance(row, dict) and row.get("approved")]
    return {
        "decisions": len(decisions),
        "approved_decisions": len(approved),
        "approve_promotion": len([row for row in approved if row.get("decision") == "approve_promotion"]),
        "approve_demotion": len([row for row in approved if row.get("decision") == "approve_demotion"]),
    }


def update_wallet_review_decision(payload):
    wallet = str(payload.get("wallet") or payload.get("address") or "").strip()
    decision = str(payload.get("decision") or "").strip().lower()
    if not wallet:
        raise ValueError("wallet is required.")
    if decision not in {"approve_promotion", "approve_demotion", "hold", "reject"}:
        raise ValueError("decision must be approve_promotion, approve_demotion, hold, or reject.")

    approved = bool(payload.get("approved")) if "approved" in payload else decision in {"approve_promotion", "approve_demotion"}
    now = time.time()
    next_decision = {
        "wallet": wallet,
        "decision": decision,
        "approved": approved,
        "note": str(payload.get("note") or "").strip(),
        "approved_by": str(payload.get("approved_by") or "operator").strip(),
        "approved_at": payload.get("approved_at") or now,
        "updated_at": now,
    }

    def updater(data):
        if not isinstance(data, dict):
            data = {"decisions": []}
        rows = data.get("decisions") if isinstance(data.get("decisions"), list) else []
        kept = [
            row for row in rows
            if not (isinstance(row, dict) and row.get("wallet") == wallet)
        ]
        kept.insert(0, next_decision)
        data["decisions"] = kept[:500]
        data["updated_at"] = now
        data.setdefault("mode", "WALLET_REVIEW_DECISIONS")
        return data

    updated = locked_update_json(WALLET_REVIEW_DECISIONS_FILE, {"decisions": []}, updater)
    return {
        "generated_at": now,
        "mode": "WALLET_REVIEW_DECISION_ONLY",
        "live_execution_locked": True,
        "tracked_wallets_mutated": False,
        "decision": next_decision,
        "summary": summarize_wallet_review_decisions(updated),
    }


def summarize_wallet_apply_result(result):
    result = result if isinstance(result, dict) else {}
    audit = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    return {
        "generated_at": time.time(),
        "mode": "WALLET_REVIEW_APPLY",
        "live_execution_locked": True,
        "execution_routes_enabled": False,
        "dry_run": bool(result.get("dry_run")),
        "stamp": result.get("stamp"),
        "backup_dir": result.get("backup_dir"),
        "summary": result.get("summary") if isinstance(result.get("summary"), dict) else {},
        "changes": audit.get("changes") if isinstance(audit.get("changes"), list) else [],
        "skipped": audit.get("skipped") if isinstance(audit.get("skipped"), list) else [],
        "detail": "Wallet-list apply only updates local tracking metadata. It does not execute trades.",
    }


def build_wallet_review_apply_payload(dry_run=True):
    return summarize_wallet_apply_result(run_wallet_review_apply(dry_run=dry_run))


def apply_wallet_review_payload(payload):
    confirm = str(payload.get("confirm") or "").strip()
    if confirm != "APPLY_WALLET_REVIEW":
        raise ValueError("Exact confirmation APPLY_WALLET_REVIEW is required before applying wallet review changes.")
    return summarize_wallet_apply_result(run_wallet_review_apply(dry_run=False))


def metadata_token_valid(headers):
    if not DESKTOP_API_TOKEN:
        return True
    headers = headers or {}
    supplied = headers.get("X-MemeTraderPro-Token") or headers.get("x-memetraderpro-token")
    return secrets.compare_digest(str(supplied or ""), str(DESKTOP_API_TOKEN))


def route_request(method, raw_path, body=None, headers=None):
    if method == "OPTIONS":
        return HTTPStatus.NO_CONTENT, "text/plain; charset=utf-8", b""

    parsed = urlparse(raw_path)
    path = parsed.path
    query = parse_qs(parsed.query)
    if method == "POST":
        if not metadata_token_valid(headers):
            return json_error("Desktop metadata mutation requires a valid session token.", HTTPStatus.UNAUTHORIZED)
        if path == "/api/watchlist/protected-amount":
            try:
                payload = parse_json_body(body)
                response = update_protected_amount_metadata(payload)
                invalidate_state_cache()
                return json_response(response)
            except (ValueError, json.JSONDecodeError) as exc:
                return json_error(exc, HTTPStatus.BAD_REQUEST)
        if path == "/api/watchlist/protected-token":
            try:
                payload = parse_json_body(body)
                response = add_protected_token_payload(payload)
                invalidate_state_cache()
                return json_response(response)
            except (ValueError, json.JSONDecodeError) as exc:
                return json_error(exc, HTTPStatus.BAD_REQUEST)
        if path == "/api/wallet-review-decision":
            try:
                payload = parse_json_body(body)
                response = update_wallet_review_decision(payload)
                invalidate_state_cache()
                return json_response(response)
            except (ValueError, json.JSONDecodeError) as exc:
                return json_error(exc, HTTPStatus.BAD_REQUEST)
        if path == "/api/wallet-review-apply":
            try:
                payload = parse_json_body(body)
                response = apply_wallet_review_payload(payload)
                invalidate_state_cache()
                return json_response(response)
            except (ValueError, json.JSONDecodeError) as exc:
                return json_error(exc, HTTPStatus.BAD_REQUEST)
        if path == "/api/social/import":
            try:
                payload = parse_json_body(body)
                response = import_social_signal_payload(payload)
                invalidate_state_cache()
                return json_response(response)
            except (ValueError, json.JSONDecodeError) as exc:
                return json_error(exc, HTTPStatus.BAD_REQUEST)
        return text_response("Mutation routes are not available in paper-only desktop view.", HTTPStatus.METHOD_NOT_ALLOWED)
    if method not in ("GET", "HEAD"):
        return text_response("Mutation routes are not available in paper-only desktop view.", HTTPStatus.METHOD_NOT_ALLOWED)

    if path == "/api/health":
        return json_response(build_health_payload())
    if path == "/api/runtime":
        return json_response(build_runtime_payload())
    if path == "/api/freshness":
        return json_response(build_freshness_payload())
    if path == "/api/social/freshness":
        return json_response(build_social_freshness_payload(
            read_json(SOCIAL_STATE_FILE, {"events": []}),
            read_json(CATALYST_CARDS_FILE, {"cards": []}),
            load_status(),
        ))
    if path == "/api/readiness":
        return json_response(build_readiness_payload())
    if path == "/api/overview":
        return json_response(build_overview_payload())
    if path == "/api/positions":
        return json_response(build_positions_payload())
    if path.startswith("/api/positions/"):
        mint = path_param(path.removeprefix("/api/positions/"))
        return json_response(build_position_detail_payload(mint))
    if path == "/api/candidate-wallets":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_candidate_wallets_payload(limit=limit))
    if path == "/api/wallet-lifecycle":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_wallet_lifecycle_payload(limit=limit))
    if path == "/api/wallet-quant":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_quant_payload(limit=limit))
    if path == "/api/wallet-replay-review":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_replay_review_payload(limit=limit))
    if path == "/api/wallet-cycle":
        return json_response(build_wallet_cycle_payload())
    if path == "/api/wallet-candidate-audit":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_candidate_audit_payload(limit=limit))
    if path == "/api/wallet-candidate-decision-prep":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        selected_wallets = []
        for value in query.get("wallet", []):
            if value.strip():
                selected_wallets.append(value.strip())
        for value in query.get("wallets", []):
            selected_wallets.extend(wallet.strip() for wallet in value.split(",") if wallet.strip())
        return json_response(build_wallet_candidate_decision_prep_payload(
            limit=limit,
            selected_wallets=selected_wallets or None,
        ))
    if path == "/api/wallet-candidate-review-summary":
        limit = parse_int_query(query, "limit", 25, 1, 250)
        return json_response(build_wallet_candidate_review_summary_payload(limit=limit))
    if path == "/api/wallet-candidate-collection-plan":
        limit = parse_int_query(query, "limit", 100, 1, 500)
        return json_response(build_wallet_candidate_collection_plan_payload(limit=limit))
    if path == "/api/wallet-candidate-collection-batch":
        limit = parse_int_query(query, "limit", 50, 1, 250)
        return json_response(build_wallet_candidate_collection_batch_payload(limit=limit))
    if path == "/api/wallet-candidate-blockers":
        limit = parse_int_query(query, "limit", 50, 1, 250)
        return json_response(build_wallet_candidate_blockers_payload(limit=limit))
    if path == "/api/wallet-candidate-context-recovery":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_wallet_candidate_context_recovery_payload(limit=limit))
    if path == "/api/wallet-candidate-context-recovery-runner":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_wallet_candidate_context_recovery_runner_payload(limit=limit))
    if path == "/api/wallet-candidate-context-recovery-closeout":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_wallet_candidate_context_recovery_closeout_payload(limit=limit))
    if path == "/api/wallet-candidate-quality":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_candidate_quality_payload(limit=limit))
    if path == "/api/wallet-candidate-quality-review":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_candidate_quality_review_payload(limit=limit))
    if path == "/api/wallet-candidate-evidence-plan":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_candidate_evidence_plan_payload(limit=limit))
    if path == "/api/wallet-candidate-backfill-targets":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_candidate_backfill_targets_payload(limit=limit))
    if path == "/api/wallet-history-backfill":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_history_backfill_payload(limit=limit))
    if path == "/api/wallet-evidence-enrichment":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_evidence_enrichment_payload(limit=limit))
    if path == "/api/wallet-missing-market-context":
        limit = parse_int_query(query, "limit", 80, 1, 500)
        return json_response(build_wallet_missing_market_context_payload(limit=limit))
    if path == "/api/evidence-layer-completion":
        return json_response(build_evidence_layer_completion_payload())
    if path == "/api/wallet-review-apply":
        return json_response(build_wallet_review_apply_payload(dry_run=True))
    if path == "/api/candidates":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_candidate_feed_payload(limit=limit))
    if path.startswith("/api/decisions/") and path.endswith("/explanation"):
        decision_id = path_param(path.removeprefix("/api/decisions/").removesuffix("/explanation").strip("/"))
        try:
            return json_response(build_decision_explanation_payload(decision_id))
        except ValueError as exc:
            return json_error(exc, HTTPStatus.BAD_REQUEST)
        except LookupError as exc:
            return json_error(exc, HTTPStatus.NOT_FOUND)
    if path == "/api/decisions":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        mint = path_param((query.get("mint") or [""])[0]) or None
        filter_name = path_param((query.get("filter") or ["all"])[0]) or "all"
        lane = path_param((query.get("lane") or [""])[0]) or None
        return json_response(build_decisions_payload(limit=limit, mint=mint, filter_name=filter_name, lane=lane))
    if path == "/api/decision-analytics":
        limit = parse_int_query(query, "limit", 5000, 1, 10000)
        return json_response(build_decision_outcome_analytics_payload(limit=limit))
    if path == "/api/market-radar-review":
        limit = parse_int_query(query, "limit", 120, 1, 500)
        return json_response(build_market_radar_review_payload(limit=limit))
    if path == "/api/events":
        limit = parse_int_query(query, "limit", 120, 1, 500)
        return json_response(build_event_feed_payload(limit=limit))
    if path == "/api/candles":
        mint = path_param((query.get("mint") or [""])[0]) or None
        limit = parse_int_query(query, "limit", 300, 1, 500)
        allow_all = (query.get("all") or ["0"])[0] == "1"
        metric = (query.get("metric") or ["price"])[0]
        interval = parse_int_query(query, "interval", 1, 1, 60)
        return json_response(build_candles_payload(
            mint=mint,
            limit=limit,
            allow_all=allow_all,
            metric=metric,
            interval_seconds=interval,
        ))
    if path.startswith("/api/tokens/") and path.endswith("/candles"):
        mint = path_param(path.removeprefix("/api/tokens/").removesuffix("/candles").strip("/"))
        limit = parse_int_query(query, "limit", 300, 1, 1000)
        metric = (query.get("metric") or ["price"])[0]
        interval = parse_int_query(query, "interval", 1, 1, 60)
        return json_response(build_candles_payload(
            mint=mint,
            limit=limit,
            metric=metric,
            interval_seconds=interval,
        ))
    if path.startswith("/api/tokens/") and path.endswith("/snapshots"):
        mint = path_param(path.removeprefix("/api/tokens/").removesuffix("/snapshots").strip("/"))
        limit = parse_int_query(query, "limit", 250, 1, 1000)
        return json_response(build_snapshots_payload(mint=mint, limit=limit))
    if path == "/api/trades":
        return json_response(build_trades_payload())
    if path == "/api/paper-review":
        return json_response(build_paper_review_payload())
    if path == "/api/winner-patterns":
        return json_response(build_winner_pattern_payload())
    if path == "/api/watchlist":
        return json_response(summarize_list_payload("manual_watchlist", read_json(WATCHLIST_FILE, [])))
    if path == "/api/wallets":
        limit = parse_int_query(query, "limit", 80, 1, 250)
        return json_response(build_wallets_payload(limit=limit))
    if path.startswith("/api/wallets/"):
        wallet = path_param(path.removeprefix("/api/wallets/"))
        limit = parse_int_query(query, "limit", 40, 1, 100)
        return json_response(build_wallet_detail_payload(wallet, limit=limit))
    if path == "/api/alerts":
        limit = parse_int_query(query, "limit", 100, 1, 250)
        return json_response(build_alerts_payload(limit=limit))
    if path == "/api/catalyst-cards":
        return json_response(summarize_list_payload("catalyst_cards", read_json(CATALYST_CARDS_FILE, {"cards": []}), key="cards"))
    if path == "/api/social":
        return json_response(summarize_social_payload(read_json(SOCIAL_STATE_FILE, {"events": []})))
    if path == "/api/settings":
        settings = read_json(SETTINGS_FILE, {})
        return json_response({
            "generated_at": time.time(),
            "settings": settings if isinstance(settings, dict) else {},
            "read_only": True,
        })
    if path == "/api/operator-config":
        return json_response(build_operator_config_payload())
    if path == "/api/logs":
        limit = parse_int_query(query, "limit", 60, 1, 200)
        return json_response(build_logs_payload(limit=limit))
    if path.startswith("/api/"):
        return text_response("Not found", HTTPStatus.NOT_FOUND)
    return static_response(path)


class DesktopRequestHandler(BaseHTTPRequestHandler):
    server_version = "MemeTraderProDesktop/0.1"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_route("GET")

    def do_HEAD(self):
        self.send_route("HEAD")

    def do_OPTIONS(self):
        self.send_route("OPTIONS")

    def do_POST(self):
        self.send_route("POST")

    def do_PUT(self):
        self.send_route("PUT")

    def do_DELETE(self):
        self.send_route("DELETE")

    def send_route(self, method):
        request_body = None
        if method in ("POST", "PUT", "PATCH"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            request_body = self.rfile.read(length) if length > 0 else b""
        status, content_type, body = safe_route_request(method, self.path, request_body, self.headers)
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        origin = allowed_cors_origin(self.headers.get("Origin"))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-MemeTraderPro-Token")
        self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def run_server(host="127.0.0.1", port=8765, open_browser=False):
    server = ThreadingHTTPServer((host, port), DesktopRequestHandler)
    url = f"http://{host}:{port}/"
    print(f"MemeTraderPro desktop GUI: {url}")
    if open_browser:
        browser_url = f"{url}?api_token={DESKTOP_API_TOKEN}" if DESKTOP_API_TOKEN else url
        webbrowser.open(browser_url)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Run the MemeTraderPro desktop GUI server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--api-token", default=os.getenv("MTP_DESKTOP_API_TOKEN", ""))
    parser.add_argument("--open", action="store_true", help="Open the local GUI in the default browser.")
    args = parser.parse_args()
    global DESKTOP_API_TOKEN
    DESKTOP_API_TOKEN = args.api_token or DESKTOP_API_TOKEN
    write_desktop_session_file(DESKTOP_API_TOKEN)
    run_server(args.host, args.port, args.open)


if __name__ == "__main__":
    main()
