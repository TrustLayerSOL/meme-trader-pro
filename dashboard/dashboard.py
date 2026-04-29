import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from core.data_freshness import DataFreshness
from core.execution_safety import ExecutionSafetyGate
from core.operator_brief import OperatorBrief
from core.performance_analyzer import PerformanceAnalyzer
from core.process_guard import ProcessGuard
from core.replay_analyzer import ReplayAnalyzer
from core.settings_manager import load_settings, save_settings
from core.storage import EventStore
from core.system_health import SystemHealth
from core.token_console import TokenConsole
from core.trade_postmortem import TradePostmortem
from core.wallet_copy_engine import WalletCopyEngine
from core.wallet_labeler import WalletLabeler

LIVE_STATE_FILE = "live_state.json"
PAPER_TRADES_FILE = "data/paper_trades.json"
WALLET_PERFORMANCE_FILE = "data/wallet_performance.json"
WATCHLIST_FILE = "data/manual_watchlist.json"
RUNTIME_STATUS_FILE = "data/runtime_status.json"
CANDIDATE_LEDGER_FILE = "data/candidate_ledger.json"
LOG_DIR = Path("logs")
BOT_LOG_FILE = LOG_DIR / "bot.log"
DASHBOARD_LOG_FILE = LOG_DIR / "dashboard.log"
WATCHDOG_LOG_FILE = LOG_DIR / "watchdog.log"

st.set_page_config(
    page_title="MemeTraderPro Dashboard",
    page_icon="🚀",
    layout="wide"
)


def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_candidate_ledger():
    data = load_json(CANDIDATE_LEDGER_FILE, {})
    return data if isinstance(data, dict) else {}


def save_candidate_ledger(data):
    save_json(CANDIDATE_LEDGER_FILE, data)


def update_candidate_ledger(mint, status, note="", alert=None):
    if not mint:
        return

    ledger = load_candidate_ledger()
    item = ledger.setdefault(mint, {})
    item.update({
        "status": status,
        "note": note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    if alert:
        item.update({
            "last_edge_score": alert.get("edge_score"),
            "last_edge_verdict": alert.get("edge_verdict"),
            "last_score": alert.get("total_score"),
            "last_risk": alert.get("risk_label"),
        })

    save_candidate_ledger(ledger)


def pick(d, keys, default="N/A"):
    for k in keys:
        if isinstance(d, dict) and k in d and d.get(k) not in [None, ""]:
            return d.get(k)
    return default


def num_or_none(v):
    try:
        if v in [None, "", "N/A"]:
            return None
        return float(v)
    except Exception:
        return None


def fmt_money(v):
    try:
        if v in [None, "", "N/A"]:
            return "N/A"
        return f"${float(v):,.2f}"
    except Exception:
        return v if v not in [None, ""] else "N/A"


def fmt_price(v):
    try:
        value = float(v)
        if value == 0:
            return "$0.00"
        if abs(value) < 0.01:
            return f"${value:,.10f}".rstrip("0").rstrip(".")
        return f"${value:,.6f}".rstrip("0").rstrip(".")
    except Exception:
        return v if v not in [None, ""] else "N/A"


def fmt_pct(v):
    try:
        return f"{float(v):.2f}%"
    except Exception:
        return v if v not in [None, ""] else "N/A"


def fmt_time(v):
    if v in [None, "", "N/A"]:
        return "N/A"

    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(v)

    try:
        numeric = float(v)
        if numeric > 1000000000:
            return datetime.fromtimestamp(numeric, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass

    return str(v)


def fmt_duration(seconds):
    value = num_or_none(seconds)
    if value is None:
        return "N/A"

    if value < 60:
        return f"{value:.0f}s"
    if value < 3600:
        return f"{value / 60:.1f}m"
    if value < 86400:
        return f"{value / 3600:.1f}h"
    return f"{value / 86400:.1f}d"


def age_from_iso(value):
    if value in [None, "", "N/A"]:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None


def table_value(value):
    if value in [None, ""]:
        return "N/A"
    return str(value)


def read_tail(path, lines=160):
    path = Path(path)
    if not path.exists():
        return "No log file yet."

    try:
        with open(path, "r", errors="replace") as f:
            return "".join(f.readlines()[-lines:]) or "Log file is empty."
    except Exception as exc:
        return f"Unable to read log: {exc}"


def derive_trade_display(trade):
    entry_price = num_or_none(pick(trade, ["entry_price"], None))
    current_price = num_or_none(pick(trade, ["current_price"], None))
    close_price = num_or_none(pick(trade, ["close_price", "exit_price"], None))
    size_usd = num_or_none(pick(trade, ["size_usd", "entry_value"], None))
    remaining_tokens = num_or_none(pick(trade, ["remaining_token_amount"], None))

    current_value = pick(trade, ["current_value", "value_now", "estimated_value"], None)
    if num_or_none(current_value) is None and current_price is not None and remaining_tokens is not None:
        current_value = current_price * remaining_tokens

    exit_value = pick(trade, ["exit_value", "sell_value", "final_value"], None)
    if num_or_none(exit_value) is None:
        sells = trade.get("sells", [])
        if isinstance(sells, list) and sells:
            exit_value = sum(num_or_none(sell.get("net_proceeds")) or 0 for sell in sells)

    return {
        "entry_price": entry_price,
        "current_price": current_price,
        "close_price": close_price,
        "entry_value": pick(trade, ["entry_value", "position_value", "position_size", "amount_sol", "sol_amount", "buy_amount"], size_usd),
        "current_value": current_value,
        "exit_value": exit_value,
    }


def score_bucket(score):
    value = num_or_none(score) or 0
    if value < 30:
        return "0-29"
    if value < 50:
        return "30-49"
    if value < 60:
        return "50-59"
    if value < 70:
        return "60-69"
    if value < 80:
        return "70-79"
    return "80+"


def render_pipeline_health(alerts, signals):
    st.header("Signal Pipeline")

    evaluated = len(alerts)
    trade_ready = len([a for a in alerts if a.get("should_trade")])
    edge_tradeable = len([
        a for a in alerts
        if a.get("edge_verdict") in ["TRADEABLE_EDGE", "STRONG_EDGE"]
        or a.get("edge_paper_trade_worthy")
    ])
    edge_quote_worthy = len([
        a for a in alerts
        if a.get("edge_quote_worthy")
        or a.get("edge_verdict") in ["QUOTE_WORTHY", "TRADEABLE_EDGE", "STRONG_EDGE"]
    ])
    quote_checked = len([
        a for a in alerts
        if a.get("buy_quote_reason") not in [None, "", "quote_not_checked_low_prescore"]
        or a.get("sell_quote_reason") not in [None, "", "sell_quote_not_checked_low_prescore"]
    ])

    scores = [num_or_none(a.get("total_score")) or 0 for a in alerts]
    edge_scores = [num_or_none(a.get("edge_score")) or 0 for a in alerts if a.get("edge_score") is not None]
    highest_score = max(scores) if scores else 0
    avg_score = sum(scores) / len(scores) if scores else 0
    highest_edge = max(edge_scores) if edge_scores else 0
    avg_edge = sum(edge_scores) / len(edge_scores) if edge_scores else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Wallet Signals", len(signals))
    c2.metric("Evaluated Alerts", evaluated)
    c3.metric("Quote Checked", quote_checked)
    c4.metric("Edge Quote Worthy", edge_quote_worthy)
    c5.metric("Trade Ready", trade_ready + edge_tradeable)
    c6.metric("Score / Edge", f"{highest_score:.1f}/{highest_edge:.1f}")

    st.caption(f"Average generic score: {avg_score:.1f} | Average edge score: {avg_edge:.1f}")

    buckets = Counter(score_bucket(a.get("total_score")) for a in alerts)
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    b1.metric("0-29", buckets.get("0-29", 0))
    b2.metric("30-49", buckets.get("30-49", 0))
    b3.metric("50-59", buckets.get("50-59", 0))
    b4.metric("60-69", buckets.get("60-69", 0))
    b5.metric("70-79", buckets.get("70-79", 0))
    b6.metric("80+", buckets.get("80+", 0))

    reason_counter = Counter()
    buy_quote_counter = Counter()
    sell_quote_counter = Counter()
    edge_counter = Counter()
    edge_positive_counter = Counter()
    edge_risk_counter = Counter()

    for alert in alerts:
        for reason in alert.get("score_reasons", []):
            reason_counter[str(reason)] += 1

        buy_quote_counter[str(alert.get("buy_quote_reason", "none"))] += 1
        sell_quote_counter[str(alert.get("sell_quote_reason", "none"))] += 1
        edge_counter[str(alert.get("edge_verdict", "legacy_no_edge"))] += 1

        for positive in alert.get("edge_positives", []):
            edge_positive_counter[str(positive)] += 1

        for risk in alert.get("edge_risks", []):
            edge_risk_counter[str(risk)] += 1

    c6, c7, c8 = st.columns(3)

    with c6:
        st.subheader("Top Skip Reasons")
        if not reason_counter:
            st.info("No skip reasons yet")
        else:
            st.dataframe(
                [{"reason": reason, "count": count} for reason, count in reason_counter.most_common(12)],
                hide_index=True,
                width="stretch",
            )

    with c7:
        st.subheader("Buy Quote Blocks")
        st.dataframe(
            [{"reason": reason, "count": count} for reason, count in buy_quote_counter.most_common(8)],
            hide_index=True,
            width="stretch",
        )

    with c8:
        st.subheader("Sell Quote Blocks")
        st.dataframe(
            [{"reason": reason, "count": count} for reason, count in sell_quote_counter.most_common(8)],
            hide_index=True,
            width="stretch",
        )

    e1, e2, e3 = st.columns(3)

    with e1:
        st.subheader("Edge Verdicts")
        st.dataframe(
            [{"verdict": verdict, "count": count} for verdict, count in edge_counter.most_common(8)],
            hide_index=True,
            width="stretch",
        )

    with e2:
        st.subheader("Edge Positives")
        st.dataframe(
            [{"positive": positive, "count": count} for positive, count in edge_positive_counter.most_common(8)],
            hide_index=True,
            width="stretch",
        )

    with e3:
        st.subheader("Edge Risks")
        st.dataframe(
            [{"risk": risk, "count": count} for risk, count in edge_risk_counter.most_common(8)],
            hide_index=True,
            width="stretch",
        )

    top_alerts = sorted(
        alerts,
        key=lambda a: max(
            num_or_none(a.get("total_score")) or 0,
            num_or_none(a.get("edge_score")) or 0,
        ),
        reverse=True,
    )[:15]

    st.subheader("Closest Candidates")
    if not top_alerts:
        st.info("No evaluated alerts yet")
    else:
        rows = []
        for alert in top_alerts:
            rows.append({
                "score": alert.get("total_score"),
                "edge": alert.get("edge_score"),
                "edge_verdict": alert.get("edge_verdict"),
                "threshold": alert.get("score_threshold"),
                "trade": alert.get("should_trade"),
                "guard": alert.get("strategy_guard_action"),
                "type": alert.get("type"),
                "wallets": alert.get("wallet_count"),
                "weighted": alert.get("weighted_wallet_score"),
                "risk": alert.get("risk_label"),
                "buy_quote": alert.get("buy_quote_reason"),
                "sell_quote": alert.get("sell_quote_reason"),
                "mint": alert.get("mint"),
            })

        st.dataframe(rows, hide_index=True, width="stretch")


def render_operator_brief(state, paper_state, wallet_perf, watchlist, runtime_status, candidate_ledger):
    st.header("Operator Brief")

    brief = OperatorBrief().build(
        state=state,
        paper_state=paper_state,
        wallet_perf=wallet_perf,
        watchlist=watchlist,
        runtime_status=runtime_status,
        candidate_ledger=candidate_ledger,
    )

    cols = st.columns(4)
    for col, item in zip(cols, brief["highlights"]):
        col.metric(item["label"], item["value"], item["detail"])

    rows = brief["tasks"]
    if rows:
        st.subheader("Next Best Actions")
        st.dataframe(rows, hide_index=True, width="stretch")


def render_wallet_intelligence(wallet_perf):
    st.header("Wallet Intelligence")

    wallets = wallet_perf.get("wallets", {}) if isinstance(wallet_perf, dict) else {}
    labeler = WalletLabeler()

    rows = []
    for wallet, record in wallets.items():
        if not isinstance(record, dict):
            continue
        labels = labeler.label(record)

        rows.append({
            "wallet": wallet,
            "label": labeler.primary_label(record),
            "labels": ", ".join(labels),
            "score": num_or_none(record.get("score")) or 0,
            "signals": int(record.get("signals", 0) or 0),
            "entries": int(record.get("paper_entries", 0) or 0),
            "wins": int(record.get("wins", 0) or 0),
            "losses": int(record.get("losses", 0) or 0),
            "avg_pnl": num_or_none(record.get("avg_pnl")) or 0,
            "total_pnl": num_or_none(record.get("total_pnl")) or 0,
            "last_seen": fmt_time(record.get("last_seen")),
        })

    if not rows:
        st.info("No wallet performance data yet")
        return

    active = [r for r in rows if r["signals"] > 0]
    proven = [r for r in rows if r["entries"] > 0]
    trusted = [r for r in rows if r["label"] in ["paper-profitable", "consistent winner"]]
    danger = [r for r in rows if r["label"] in ["fade/caution", "consistent loser", "large-drawdown source"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked Active Wallets", len(active))
    c2.metric("Proven By Paper Trades", len(proven))
    c3.metric("Trusted Candidates", len(trusted))
    c4.metric("Fade / Caution Wallets", len(danger))

    left, right = st.columns(2)

    with left:
        st.subheader("Top Wallets")
        top = sorted(rows, key=lambda r: (r["score"], r["entries"], r["signals"]), reverse=True)[:15]
        st.dataframe(top, hide_index=True, width="stretch")

    with right:
        st.subheader("Caution Wallets")
        bottom = sorted(danger or proven, key=lambda r: (r["score"], -r["entries"]))[:15]
        st.dataframe(bottom, hide_index=True, width="stretch")


def render_paper_copy_engine(wallet_perf):
    st.header("Paper Copy Engine")

    engine = WalletCopyEngine()
    wallet_rows = engine.wallet_rows(wallet_perf, limit=50)
    signal_rows = engine.signal_rows(wallet_perf, limit=40)

    if not wallet_rows:
        st.info("No wallet records available for copy/fade recommendations yet.")
        return

    counts = Counter(row["recommendation"] for row in wallet_rows)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Copy Candidates", counts.get("COPY", 0))
    c2.metric("Paper-Copy Candidates", counts.get("PAPER_COPY", 0))
    c3.metric("Observe Wallets", counts.get("OBSERVE", 0))
    c4.metric("Fade Wallets", counts.get("FADE", 0))

    st.caption("Local recommendation layer for which wallets deserve copy simulation, observation, or fade treatment.")

    display_wallets = []
    for row in wallet_rows:
        display_wallets.append({
            "action": row.get("recommendation"),
            "label": row.get("label"),
            "confidence": row.get("confidence"),
            "size": row.get("size_multiplier"),
            "score": row.get("score"),
            "signals": row.get("signals"),
            "entries": row.get("entries"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "avg_pnl": fmt_money(row.get("avg_pnl")),
            "total_pnl": fmt_money(row.get("total_pnl")),
            "last_seen": fmt_time(row.get("last_seen")),
            "wallet": row.get("wallet"),
        })
    st.dataframe(display_wallets, hide_index=True, width="stretch")

    st.subheader("Latest Wallet Signals")
    display_signals = []
    for row in signal_rows:
        display_signals.append({
            "time": fmt_time(row.get("time")),
            "action": row.get("recommended_action"),
            "copy_wallets": row.get("copy_wallets"),
            "fade_wallets": row.get("fade_wallets"),
            "confidence": row.get("copy_confidence"),
            "wallets": row.get("wallets"),
            "score": row.get("score"),
            "scanner_trade": row.get("should_trade"),
            "top_wallet": row.get("top_wallet"),
            "mint": row.get("mint"),
        })
    st.dataframe(display_signals, hide_index=True, width="stretch")


def small_trade_row(trade):
    return {
        "pnl": fmt_money(trade.get("total_pnl", trade.get("pnl"))),
        "pnl_pct": fmt_pct(trade.get("total_pnl_pct", trade.get("pnl_pct"))),
        "reason": trade.get("entry_reason") or trade.get("reason"),
        "mint": trade.get("token_mint") or trade.get("mint"),
    }


def render_performance_intelligence(paper_state):
    st.header("Performance Intelligence")

    perf = PerformanceAnalyzer().analyze(paper_state)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Realized PnL", fmt_money(perf["realized_pnl"]))
    c2.metric("Unrealized PnL", fmt_money(perf["unrealized_pnl"]))
    c3.metric("Total PnL", fmt_money(perf["total_pnl"]))
    c4.metric("Win Rate", fmt_pct(perf["win_rate"]))
    c5.metric("Expectancy", fmt_money(perf["expectancy"]))
    c6.metric("Max Drawdown", fmt_money(perf["max_drawdown"]))

    c7, c8, c9, c10 = st.columns(4)
    c7.metric("Avg Win", fmt_money(perf["avg_win"]))
    c8.metric("Avg Loss", fmt_money(perf["avg_loss"]))
    c9.metric("Profit Factor", perf["profit_factor"] if perf["profit_factor"] is not None else "N/A")
    c10.metric("Failed Trades", perf["failed_trades"])

    if perf["closed_trades"] == 0:
        st.info("No closed trades yet")
        return

    left, right = st.columns(2)

    with left:
        st.subheader("Signal Families")
        st.dataframe(perf["signal_rows"], hide_index=True, width="stretch")

    with right:
        st.subheader("Trade Mix")
        st.dataframe(
            [{"reason": reason, "count": count} for reason, count in perf["reason_counts"]],
            hide_index=True,
            width="stretch",
        )

    best_col, worst_col = st.columns(2)

    with best_col:
        st.subheader("Best Trades")
        st.dataframe([small_trade_row(t) for t in perf["best_trades"]], hide_index=True, width="stretch")

    with worst_col:
        st.subheader("Worst Trades")
        st.dataframe([small_trade_row(t) for t in perf["worst_trades"]], hide_index=True, width="stretch")


def render_trade_postmortem(paper_state):
    st.header("Trade Postmortem")

    report = TradePostmortem().analyze(paper_state)
    rows = report["rows"]
    if not rows:
        st.info("No trades available for postmortem yet.")
        return

    st.subheader("What Worked")
    for lesson in report["winner_lessons"]:
        st.success(lesson)

    st.subheader("What Failed")
    for lesson in report["loser_lessons"]:
        st.warning(lesson)

    st.subheader("Recommended Changes")
    for item in report["recommendations"]:
        st.write(f"- {item}")

    st.subheader("Trade Diagnostics")
    st.dataframe(rows, hide_index=True, width="stretch")


def render_replay_lab(alerts, paper_state):
    st.header("Replay Lab")

    replay = ReplayAnalyzer().replay(alerts, paper_state)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Alerts Replayed", replay["total_alerts"])
    c2.metric("Paper Trade", replay["actions"].get("PAPER_TRADE", 0))
    c3.metric("Quote Check", replay["actions"].get("QUOTE_CHECK", 0))
    c4.metric("Watchlist", replay["actions"].get("WATCHLIST", 0))
    c5.metric("Guard Blocked", replay["actions"].get("GUARD_BLOCKED", 0))

    left, right = st.columns(2)

    with left:
        st.subheader("Replay Actions")
        st.dataframe(
            [{"action": action, "count": count} for action, count in replay["actions"].most_common()],
            hide_index=True,
            width="stretch",
        )

    with right:
        st.subheader("Current Edge Verdicts")
        st.dataframe(
            [{"verdict": verdict, "count": count} for verdict, count in replay["verdicts"].most_common()],
            hide_index=True,
            width="stretch",
        )

    st.subheader("Threshold Calibration")
    st.dataframe(replay["calibration"], hide_index=True, width="stretch")

    st.subheader("Top Replayed Candidates")
    rows = []
    for row in replay["ranked"][:25]:
        rows.append({
            "action": row["action"],
            "edge": row["edge_score"],
            "verdict": row["edge_verdict"],
            "guard": row["strategy_guard_action"],
            "type": row["type"],
            "risk": row["risk_label"],
            "wallets": row["wallet_count"],
            "weighted": row["weighted_wallet_score"],
            "liquidity": fmt_money(row.get("liquidity")),
            "age": fmt_duration(row.get("true_launch_age_seconds")),
            "positives": ", ".join(row.get("positives", [])[:3]),
            "risks": ", ".join(row.get("risks", [])[:3]),
            "mint": row["mint"],
        })
    st.dataframe(rows, hide_index=True, width="stretch")


def classify_candidate(alert):
    edge_score = num_or_none(alert.get("edge_score")) or 0
    score = num_or_none(alert.get("total_score")) or 0
    risk = str(alert.get("risk_label", "UNKNOWN"))
    verdict = alert.get("edge_verdict") or "LEGACY"

    if alert.get("should_trade"):
        return "TRADE READY"

    if alert.get("edge_quote_worthy"):
        return "QUOTE CHECK"

    if edge_score >= 35 or score >= 35:
        return "WATCH"

    if risk in ["HIGH_RISK", "BLOCKED"]:
        return "AVOID"

    if verdict == "IGNORE":
        return "IGNORE"

    return "REVIEW"


def candidate_row(alert):
    market = alert.get("market_info") or {}
    return {
        "time": fmt_time(alert.get("timestamp") or alert.get("time")),
        "action": classify_candidate(alert),
        "edge": alert.get("edge_score"),
        "verdict": alert.get("edge_verdict"),
        "score": alert.get("total_score"),
        "quote": alert.get("edge_quote_worthy"),
        "trade": alert.get("should_trade"),
        "guard": alert.get("strategy_guard_action"),
        "risk": alert.get("risk_label"),
        "wallets": alert.get("wallet_count"),
        "liquidity": fmt_money(market.get("liquidity")),
        "positives": ", ".join(alert.get("edge_positives", [])[:3]),
        "risks": ", ".join(alert.get("edge_risks", [])[:3]),
        "mint": alert.get("mint"),
    }


def candidate_sort_value(alert):
    return (
        alert.get("should_trade") is True,
        alert.get("edge_quote_worthy") is True,
        num_or_none(alert.get("edge_score")) or 0,
        num_or_none(alert.get("total_score")) or 0,
        num_or_none((alert.get("market_info") or {}).get("liquidity")) or 0,
    )


def render_candidate_card(alert, index, watched_mints, candidate_ledger):
    mint = alert.get("mint")
    market = alert.get("market_info") or {}
    positives = alert.get("edge_positives", [])
    risks = alert.get("edge_risks", [])
    reasons = alert.get("score_reasons", [])
    action = classify_candidate(alert)
    ledger_item = candidate_ledger.get(mint, {})
    ledger_status = ledger_item.get("status")

    status_prefix = f"{ledger_status} | " if ledger_status else ""
    title = f"{status_prefix}{action} | edge {alert.get('edge_score', 'N/A')} | score {alert.get('total_score', 'N/A')}"

    with st.expander(title):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Edge Verdict", alert.get("edge_verdict", "N/A"))
        c2.metric("Risk", alert.get("risk_label", "N/A"))
        c3.metric("Wallets", alert.get("wallet_count", "N/A"))
        c4.metric("Weighted", alert.get("weighted_wallet_score", "N/A"))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Liquidity", fmt_money(market.get("liquidity")))
        c6.metric("Volume 24h", fmt_money(market.get("volume")))
        c7.metric("True Age", fmt_duration(alert.get("true_launch_age_seconds")))
        c8.metric("Position", fmt_money(alert.get("position_size_usd")))

        st.write(f"**Mint:** `{mint}`")
        if ledger_status:
            st.write(f"**Ledger:** {ledger_status} | {ledger_item.get('updated_at')}")
        st.write(f"**Buy Quote:** {alert.get('buy_quote_reason')} | {alert.get('buy_quote_price_impact_pct')}")
        st.write(f"**Sell Quote:** {alert.get('sell_quote_reason')} | {alert.get('sell_quote_price_impact_pct')}")
        if alert.get("strategy_guard_action"):
            st.write(f"**Strategy Guard:** {alert.get('strategy_guard_action')} | {alert.get('strategy_guard_reason')}")

        if positives:
            st.success("Edge positives: " + ", ".join(positives))
        else:
            st.info("Edge positives: none")

        if risks:
            st.warning("Edge risks: " + ", ".join(risks))

        if reasons:
            st.write("**Score Reasons:**")
            st.write(", ".join(str(reason) for reason in reasons[:10]))

        buttons = st.columns(3)
        with buttons[0]:
            if mint in watched_mints:
                st.info("Already protected")
            elif st.button("Add To Protection", key=f"protect_candidate_{index}_{mint}"):
                add_manual_watch(mint, "", auto_sell=False, alert_only=True)
                update_candidate_ledger(mint, "PROTECTED", "Added from candidate workbench", alert)
                st.success("Added to manual protection")
                st.rerun()

        with buttons[1]:
            if st.button("Mark Ignore", key=f"ignore_candidate_{index}_{mint}"):
                update_candidate_ledger(mint, "IGNORED", "Ignored from candidate workbench", alert)
                st.success("Marked ignored")
                st.rerun()

        with buttons[2]:
            if market.get("url"):
                st.link_button("Open Market", market.get("url"), key=f"candidate_market_{index}")

        if st.button("Show Raw", key=f"raw_candidate_{index}_{mint}"):
            st.session_state[f"show_raw_candidate_{index}_{mint}"] = True

        if st.session_state.get(f"show_raw_candidate_{index}_{mint}"):
            st.json(alert)


def render_candidate_ledger(candidate_ledger):
    if not candidate_ledger:
        return

    st.subheader("Candidate Ledger")
    rows = []
    for mint, item in candidate_ledger.items():
        if not isinstance(item, dict):
            continue
        rows.append({
            "status": item.get("status"),
            "edge": item.get("last_edge_score"),
            "verdict": item.get("last_edge_verdict"),
            "score": item.get("last_score"),
            "risk": item.get("last_risk"),
            "updated": item.get("updated_at"),
            "note": item.get("note"),
            "mint": mint,
        })

    rows = sorted(rows, key=lambda row: row.get("updated") or "", reverse=True)
    st.dataframe(rows, hide_index=True, width="stretch")


def render_command_center(state, alerts, watchlist, candidate_ledger):
    st.header("Command Center")

    last_updated = state.get("last_updated")
    seconds_since_update = None
    if num_or_none(last_updated) is not None:
        seconds_since_update = max(0, datetime.now(timezone.utc).timestamp() - float(last_updated))

    recent_events = state.get("events", [])[-20:]
    recent_buys = len([e for e in recent_events if e.get("type") == "buy"])
    recent_sells = len([e for e in recent_events if e.get("type") == "sell"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last Bot State Update", f"{seconds_since_update:.0f}s ago" if seconds_since_update is not None else "N/A")
    c2.metric("Recent Events", len(recent_events))
    c3.metric("Recent Buys", recent_buys)
    c4.metric("Recent Sells", recent_sells)

    if seconds_since_update is None:
        st.warning("No live-state timestamp found yet.")
    elif seconds_since_update > 180:
        st.warning("Live state is stale. The bot may be stopped or waiting for wallet events.")
    else:
        st.success("Live state is updating.")

    top = sorted(
        alerts,
        key=candidate_sort_value,
        reverse=True,
    )[:25]

    st.subheader("Opportunity Inbox")
    if not top:
        st.info("No candidates yet")
    else:
        rows = [candidate_row(alert) for alert in top]
        st.dataframe(rows, hide_index=True, width="stretch")

        watched_mints = {
            item.get("token_mint")
            for item in watchlist
            if isinstance(item, dict) and item.get("token_mint")
        }

        st.subheader("Candidate Workbench")
        for idx, alert in enumerate(top[:8]):
            render_candidate_card(alert, idx, watched_mints, candidate_ledger)

    render_candidate_ledger(candidate_ledger)

    with st.expander("Runtime Logs"):
        log_choice = st.radio(
            "Log",
            ["Bot", "Dashboard", "Watchdog"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if log_choice == "Bot":
            log_path = BOT_LOG_FILE
        elif log_choice == "Dashboard":
            log_path = DASHBOARD_LOG_FILE
        else:
            log_path = WATCHDOG_LOG_FILE
        st.code(read_tail(log_path), language="text")


def render_token_console(state, paper_state, watchlist, candidate_ledger):
    st.header("Token Console")

    console = TokenConsole()
    records = console.build(state, paper_state, watchlist, candidate_ledger)
    rows = console.rows(state, paper_state, watchlist, candidate_ledger)

    if not rows:
        st.info("No token-level records yet. Alerts, trades, protected tokens, and ledger entries will appear here.")
        return

    action_counts = Counter(row.get("recommended_action") or "REVIEW" for row in rows)
    open_positions = len([row for row in rows if row.get("has_open_trade")])
    protected = len([row for row in rows if row.get("protected")])
    quote_ready = len([row for row in rows if row.get("quote_worthy")])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracked Tokens", len(rows))
    c2.metric("Open Positions", open_positions)
    c3.metric("Protected Tokens", protected)
    c4.metric("Quote-Ready", quote_ready)

    st.caption(
        "Unified token view across scanner alerts, paper trades, manual protection, and candidate ledger decisions."
    )

    all_actions = sorted(set(row.get("recommended_action") or "REVIEW" for row in rows))
    all_risks = sorted(set(row.get("risk_label") or "UNKNOWN" for row in rows))

    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    with f1:
        query = st.text_input("Search token", placeholder="Mint, symbol, name, action, risk").strip().lower()
    with f2:
        selected_actions = st.multiselect(
            "Actions",
            all_actions,
            default=[
                action
                for action in all_actions
                if action in ["MONITOR_POSITION", "REVIEW_EXIT", "PROTECTION_ALERT", "CONSIDER_PAPER_TRADE", "QUOTE_CHECK"]
            ],
        )
    with f3:
        selected_risks = st.multiselect("Risks", all_risks, default=all_risks)
    with f4:
        min_edge = st.number_input("Min edge", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

    toggles = st.columns(4)
    open_only = toggles[0].checkbox("Open only", value=False)
    protected_only = toggles[1].checkbox("Protected only", value=False)
    quote_only = toggles[2].checkbox("Quote-ready only", value=False)
    hide_avoid = toggles[3].checkbox("Hide avoid", value=False)

    filtered_rows = filter_token_rows(
        rows=rows,
        query=query,
        selected_actions=selected_actions,
        selected_risks=selected_risks,
        min_edge=min_edge,
        open_only=open_only,
        protected_only=protected_only,
        quote_only=quote_only,
        hide_avoid=hide_avoid,
    )

    st.write(f"Showing {len(filtered_rows)} of {len(rows)} tokens")

    table_rows = []
    for row in filtered_rows:
        table_rows.append({
            "action": row.get("recommended_action"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "edge": row.get("edge_score"),
            "verdict": row.get("edge_verdict"),
            "risk": row.get("risk_label"),
            "token": row.get("token_standard"),
            "mechanics": row.get("token_mechanics_risk"),
            "liquidity": row.get("liquidity"),
            "volume": row.get("volume"),
            "price": row.get("price"),
            "open": row.get("open_trades"),
            "closed": row.get("closed_trades"),
            "pnl": row.get("total_pnl"),
            "protected": row.get("protected"),
            "ledger": row.get("ledger_status"),
            "mint": row.get("mint"),
        })

    st.dataframe(table_rows, hide_index=True, width="stretch")

    action_cols = st.columns(min(4, max(1, len(action_counts))))
    for idx, (action, count) in enumerate(action_counts.most_common(4)):
        action_cols[idx].metric(action, count)

    options = [row.get("mint") for row in filtered_rows if row.get("mint")]
    if not options:
        st.info("No tokens match the current filters.")
        return

    selected = st.selectbox(
        "Inspect token",
        options,
        format_func=lambda mint: token_option_label(records.get(mint, {})),
    )

    record = records.get(selected, {})
    if not record:
        return

    render_token_detail(selected, record)


def filter_token_rows(
    rows,
    query="",
    selected_actions=None,
    selected_risks=None,
    min_edge=0,
    open_only=False,
    protected_only=False,
    quote_only=False,
    hide_avoid=False,
):
    selected_actions = set(selected_actions or [])
    selected_risks = set(selected_risks or [])
    filtered = []

    for row in rows:
        action = row.get("recommended_action") or "REVIEW"
        risk = row.get("risk_label") or "UNKNOWN"
        edge = num_or_none(row.get("edge_score")) or 0

        if selected_actions and action not in selected_actions:
            continue
        if selected_risks and risk not in selected_risks:
            continue
        if edge < float(min_edge or 0):
            continue
        if open_only and not row.get("has_open_trade"):
            continue
        if protected_only and not row.get("protected"):
            continue
        if quote_only and not row.get("quote_worthy"):
            continue
        if hide_avoid and action == "AVOID":
            continue

        haystack = " ".join(
            str(row.get(key) or "")
            for key in ["mint", "symbol", "name", "recommended_action", "risk_label", "edge_verdict", "ledger_status"]
        ).lower()
        if query and query not in haystack:
            continue

        filtered.append(row)

    return filtered


def token_option_label(record):
    market = record.get("market") or {}
    symbol = market.get("symbol") or "UNKNOWN"
    action = record.get("recommended_action") or "REVIEW"
    mint = record.get("mint") or ""
    return f"{symbol} | {action} | {mint[:8]}...{mint[-4:]}" if len(mint) > 14 else f"{symbol} | {action} | {mint}"


def render_token_detail(mint, record):
    market = record.get("market") or {}
    signal = record.get("signal") or {}
    risk = record.get("risk") or {}
    edge = record.get("edge") or {}
    stats = record.get("trade_stats") or {}
    protection = record.get("protection") or {}
    ledger = record.get("ledger") or {}
    latest_alert = record.get("latest_alert") or {}

    st.subheader(token_option_label(record))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommended Action", record.get("recommended_action", "REVIEW"))
    c2.metric("Edge", edge.get("score", "N/A"))
    c3.metric("Risk", risk.get("label", "UNKNOWN"))
    c4.metric("PnL", fmt_money(stats.get("total_pnl")))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Liquidity", fmt_money(market.get("liquidity")))
    c6.metric("Volume", fmt_money(market.get("volume")))
    c7.metric("Price", fmt_price(market.get("price")))
    c8.metric("Last Seen", fmt_time((record.get("sort") or {}).get("latest_time")))

    st.write(f"**Mint:** `{mint}`")
    if market.get("url"):
        st.link_button("Open Market", market.get("url"), key=f"token_console_market_{mint}")

    if edge.get("positives"):
        st.success("Edge positives: " + ", ".join(str(item) for item in edge.get("positives")[:5]))
    if edge.get("risks"):
        st.warning("Edge risks: " + ", ".join(str(item) for item in edge.get("risks")[:5]))
    if risk.get("warnings"):
        st.warning("Risk warnings: " + ", ".join(str(item) for item in risk.get("warnings")[:5]))
    if risk.get("token_mechanics_reasons"):
        st.warning("Token mechanics: " + ", ".join(str(item) for item in risk.get("token_mechanics_reasons")[:5]))

    d1, d2, d3 = st.columns(3)
    d1.write(f"**Signal:** {signal.get('type')} | wallets {signal.get('wallet_count')} | weighted {signal.get('weighted_wallet_score')}")
    d2.write(f"**Protection:** {protection.get('status')} | {protection.get('risk_level')}")
    d3.write(f"**Ledger:** {ledger.get('status') or 'N/A'} | {ledger.get('note') or ''}")

    d4, d5, d6 = st.columns(3)
    d4.write(f"**Token Standard:** {risk.get('token_standard') or 'N/A'}")
    d5.write(f"**Mechanics Risk:** {risk.get('token_mechanics_risk') or 'N/A'}")
    d6.write(f"**Extensions:** {', '.join(risk.get('token_extensions') or []) or 'N/A'}")

    buttons = st.columns(3)
    with buttons[0]:
        if protection.get("protected"):
            st.info("Already protected")
        elif st.button("Add To Protection", key=f"token_console_protect_{mint}"):
            add_manual_watch(mint, "", auto_sell=False, alert_only=True)
            update_candidate_ledger(mint, "PROTECTED", "Added from token console", latest_alert)
            st.success("Added to protection")
            st.rerun()

    with buttons[1]:
        if st.button("Mark Ignore", key=f"token_console_ignore_{mint}"):
            update_candidate_ledger(mint, "IGNORED", "Ignored from token console", latest_alert)
            st.success("Marked ignored")
            st.rerun()

    with buttons[2]:
        if st.button("Needs Review", key=f"token_console_review_{mint}"):
            update_candidate_ledger(mint, "REVIEW", "Flagged for manual review from token console", latest_alert)
            st.success("Flagged for review")
            st.rerun()

    tabs = st.tabs(["Alerts", "Trades", "Protection", "Raw"])

    with tabs[0]:
        alert_rows = []
        for alert in sorted(record.get("alerts", []), key=lambda item: item.get("timestamp") or item.get("time") or 0, reverse=True):
            alert_rows.append({
                "time": fmt_time(alert.get("timestamp") or alert.get("time")),
                "type": alert.get("type") or alert.get("signal_type"),
                "action": classify_candidate(alert),
                "edge": alert.get("edge_score"),
                "verdict": alert.get("edge_verdict"),
                "score": alert.get("total_score"),
                "risk": alert.get("risk_label"),
                "wallets": alert.get("wallet_count"),
                "weighted": alert.get("weighted_wallet_score"),
            })
        st.dataframe(alert_rows, hide_index=True, width="stretch")

    with tabs[1]:
        trade_rows = []
        for trade in sorted(record.get("trades", []), key=lambda item: item.get("entry_time") or 0, reverse=True):
            trade_rows.append({
                "status": trade.get("status"),
                "entry": fmt_time(trade.get("entry_time")),
                "close": fmt_time(trade.get("close_time")),
                "entry_value": fmt_money(trade.get("entry_value")),
                "current_value": fmt_money(trade.get("current_value")),
                "pnl": fmt_money(trade.get("total_pnl", trade.get("pnl"))),
                "pnl_pct": fmt_pct(trade.get("total_pnl_pct", trade.get("pnl_pct"))),
                "reason": trade.get("entry_reason") or trade.get("reason"),
            })
        st.dataframe(trade_rows, hide_index=True, width="stretch")

    with tabs[2]:
        st.json({
            "protection": protection,
            "ledger": ledger,
            "market": market,
            "signal": signal,
            "risk": risk,
            "edge": edge,
        })

    with tabs[3]:
        st.json(record)


def component_age(component):
    updated_at = num_or_none(component.get("updated_at"))
    if updated_at is None:
        return None
    return max(0, datetime.now(timezone.utc).timestamp() - updated_at)


def render_runtime_health(runtime_status):
    st.header("Runtime Health")

    bot = runtime_status.get("bot", {})
    websocket = runtime_status.get("websocket", {})
    scanner = runtime_status.get("scanner", {})
    market = runtime_status.get("market", {})
    quotes = runtime_status.get("quotes", {})
    watchdog = runtime_status.get("watchdog", {})

    components = [
        ("Bot", bot),
        ("WebSocket", websocket),
        ("Scanner", scanner),
        ("Market", market),
        ("Quotes", quotes),
        ("Watchdog", watchdog),
    ]

    cols = st.columns(6)
    for col, (name, component) in zip(cols, components):
        age = component_age(component)
        status = component.get("status", "unknown")
        if age is None:
            value = "N/A"
        elif age < 90:
            value = f"{age:.0f}s"
        else:
            value = f"{age / 60:.1f}m"
        col.metric(name, value, status)

    freshness = DataFreshness().report()
    source_counts = freshness["counts"]
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Source Freshness", freshness["overall"])
    f2.metric("Fresh/OK Sources", source_counts.get("FRESH", 0) + source_counts.get("OK", 0))
    f3.metric(
        "Stale Sources",
        source_counts.get("STALE", 0) + source_counts.get("OLD", 0) + source_counts.get("UNKNOWN", 0),
    )
    f4.metric("Broken/Missing", source_counts.get("BROKEN", 0) + source_counts.get("MISSING", 0))

    stale_sources = [
        row for row in freshness["rows"]
        if row.get("status") in ["STALE", "OLD", "UNKNOWN", "BROKEN", "MISSING"]
    ]
    if stale_sources:
        st.warning("Some data sources are stale, old, missing, or broken.")
        st.dataframe(stale_sources, hide_index=True, width="stretch")
    else:
        st.success("All tracked data sources are fresh enough for their role.")

    process_rows = ProcessGuard().status_rows()
    st.subheader("Local Processes")
    st.dataframe(process_rows, hide_index=True, width="stretch")

    left, middle, right = st.columns(3)

    with left:
        st.subheader("Connection")
        st.dataframe(
            [
                {"metric": "status", "value": table_value(websocket.get("status"))},
                {"metric": "tracked_wallets", "value": table_value(websocket.get("tracked_wallets"))},
                {"metric": "subscribed_wallets", "value": table_value(websocket.get("subscribed_wallets"))},
                {"metric": "messages_received", "value": table_value(websocket.get("messages_received", 0))},
                {"metric": "reconnects", "value": table_value(websocket.get("reconnects", 0))},
                {"metric": "last_error", "value": table_value(websocket.get("last_error"))},
            ],
            hide_index=True,
            width="stretch",
        )

    with middle:
        st.subheader("Scanner")
        st.dataframe(
            [
                {"metric": "messages_seen", "value": table_value(scanner.get("messages_seen", 0))},
                {"metric": "unique_signatures", "value": table_value(scanner.get("unique_signatures", 0))},
                {"metric": "wallet_hit_transactions", "value": table_value(scanner.get("wallet_hit_transactions", 0))},
                {"metric": "wallet_events", "value": table_value(scanner.get("wallet_events", 0))},
                {"metric": "signals_evaluated", "value": table_value(scanner.get("signals_evaluated", 0))},
                {"metric": "paper_trades_opened", "value": table_value(scanner.get("paper_trades_opened", 0))},
            ],
            hide_index=True,
            width="stretch",
        )

    with right:
        st.subheader("Services")
        st.dataframe(
            [
                {"metric": "market_status", "value": table_value(market.get("status"))},
                {"metric": "last_price_source", "value": table_value(market.get("last_price_source"))},
                {"metric": "jupiter_price_successes", "value": table_value(market.get("jupiter_price_successes", 0))},
                {"metric": "dexscreener_successes", "value": table_value(market.get("dexscreener_successes", 0))},
                {"metric": "quote_status", "value": table_value(quotes.get("status"))},
                {"metric": "successful_quotes", "value": table_value(quotes.get("successful_quotes", 0))},
                {"metric": "watchdog_status", "value": table_value(watchdog.get("status"))},
                {"metric": "watchdog_checks", "value": table_value(watchdog.get("successful_checks", 0))},
            ],
            hide_index=True,
            width="stretch",
        )

    stale = [
        name
        for name, component in components
        if component_age(component) is not None and component_age(component) > 180
    ]

    if stale:
        st.warning("Stale components: " + ", ".join(stale))
    else:
        st.success("Runtime health is current for active components.")


def render_system_readiness():
    st.header("System Readiness")

    report = SystemHealth().report()
    counts = report["counts"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall", report["overall"])
    c2.metric("OK", counts["OK"])
    c3.metric("Warnings", counts["WARN"])
    c4.metric("Failures", counts["FAIL"])

    if report["overall"] == "FAIL":
        st.error("Readiness checks found failures that can break the workstation.")
    elif report["overall"] == "WARN":
        st.warning("Readiness checks found warnings. The system can run, but some feeds or services need attention.")
    else:
        st.success("All readiness checks are healthy.")

    st.dataframe(report["rows"], hide_index=True, width="stretch")


def render_execution_safety():
    st.header("Execution Safety")

    report = ExecutionSafetyGate().report()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mode", report["overall"])
    c2.metric("Live Allowed", "YES" if report["live_allowed"] else "NO")
    c3.metric("Blockers", report["blockers"])
    c4.metric("Warnings", report["warnings"])

    if report["live_allowed"]:
        st.success("Live execution gate is open. Use only after confirming wallet, slippage, and risk controls.")
    elif report["live_enabled"]:
        st.error("Live trading is requested but blocked by safety checks.")
    else:
        st.info("Live execution is locked. Paper trading and quote checks remain available.")

    st.dataframe(report["checks"], hide_index=True, width="stretch")


def render_data_store():
    st.header("Data Store")

    try:
        store = EventStore()
        counts = store.counts()
        trade_summary = store.trade_summary()
    except Exception as exc:
        st.error(f"Unable to open SQLite event store: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stored Events", counts.get("events", 0))
    c2.metric("Stored Alerts", counts.get("alerts", 0))
    c3.metric("Stored Trades", counts.get("trades", 0))
    c4.metric("Protected Tokens", counts.get("watchlist", 0))

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("DB Trade PnL", fmt_money(trade_summary.get("total_pnl")))
    t2.metric("DB Open Trades", int(trade_summary.get("open_trades") or 0))
    t3.metric("DB Closed Trades", int(trade_summary.get("closed_trades") or 0))
    t4.metric("DB Winners", int(trade_summary.get("winners") or 0))

    freshness = DataFreshness().report()
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Freshness", freshness["overall"])
    f2.metric("Fresh", freshness["counts"].get("FRESH", 0) + freshness["counts"].get("OK", 0))
    f3.metric(
        "Stale/Old",
        freshness["counts"].get("STALE", 0)
        + freshness["counts"].get("OLD", 0)
        + freshness["counts"].get("UNKNOWN", 0),
    )
    f4.metric("Broken/Missing", freshness["counts"].get("BROKEN", 0) + freshness["counts"].get("MISSING", 0))

    if freshness["overall"] == "FAIL":
        st.error("One or more state sources are missing or malformed.")
    elif freshness["overall"] == "WARN":
        st.warning("Some state sources are stale or do not expose a reliable timestamp.")
    else:
        st.success("Tracked state sources are fresh.")

    tabs = st.tabs(["Freshness", "Recent Alerts", "Recent Events", "Recent Trades", "Top Tokens", "Protection"])

    with tabs[0]:
        st.dataframe(freshness["rows"], hide_index=True, width="stretch")

    with tabs[1]:
        rows = []
        for row in store.recent_alerts(25):
            rows.append({
                "time": fmt_time(row.get("time")),
                "type": row.get("signal_type"),
                "edge": row.get("edge_score"),
                "verdict": row.get("edge_verdict"),
                "score": row.get("total_score"),
                "trade": bool(row.get("should_trade")),
                "risk": row.get("risk_label"),
                "mint": row.get("mint"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

    with tabs[2]:
        rows = []
        for row in store.recent_events(25):
            rows.append({
                "time": fmt_time(row.get("time")),
                "type": row.get("event_type"),
                "wallet": row.get("wallet"),
                "mint": row.get("mint"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

    with tabs[3]:
        rows = []
        for row in store.recent_trades(25):
            rows.append({
                "status": row.get("status"),
                "entry": fmt_time(row.get("entry_time")),
                "close": fmt_time(row.get("close_time")),
                "pnl": fmt_money(row.get("pnl")),
                "pnl_pct": fmt_pct(row.get("pnl_pct")),
                "reason": row.get("reason"),
                "mint": row.get("mint"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

    with tabs[4]:
        rows = []
        for row in store.top_alert_mints(20):
            rows.append({
                "alerts": row.get("alerts"),
                "max_edge": row.get("max_edge"),
                "max_score": row.get("max_score"),
                "last_seen": fmt_time(row.get("last_seen")),
                "mint": row.get("mint"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

    with tabs[5]:
        rows = []
        for row in store.watchlist_rows():
            rows.append({
                "status": row.get("status"),
                "risk": row.get("risk_level"),
                "updated": fmt_time(row.get("updated_at")),
                "mint": row.get("mint"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")


def render_strategy_settings():
    st.header("Strategy Settings")

    settings = load_settings()

    with st.form("strategy_settings_form"):
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            mode = st.selectbox(
                "Mode",
                ["CONFIRMATION", "SNIPER", "SAFE"],
                index=["CONFIRMATION", "SNIPER", "SAFE"].index(settings.get("mode", "CONFIRMATION"))
                if settings.get("mode", "CONFIRMATION") in ["CONFIRMATION", "SNIPER", "SAFE"]
                else 0,
            )
            cluster_threshold = st.number_input(
                "Cluster Wallets",
                min_value=1,
                max_value=12,
                value=int(settings.get("cluster_threshold", 3)),
                step=1,
            )
            cluster_window = st.number_input(
                "Cluster Window Sec",
                min_value=15,
                max_value=600,
                value=int(settings.get("cluster_window", 90)),
                step=15,
            )

        with c2:
            sniper_threshold = st.number_input(
                "SNIPER Score Threshold",
                min_value=1.0,
                max_value=100.0,
                value=float(settings.get("sniper_score_threshold", 55)),
                step=1.0,
            )
            confirmation_threshold = st.number_input(
                "CONFIRMATION Score Threshold",
                min_value=1.0,
                max_value=100.0,
                value=float(settings.get("confirmation_score_threshold", 68)),
                step=1.0,
            )
            safe_threshold = st.number_input(
                "SAFE Score Threshold",
                min_value=1.0,
                max_value=100.0,
                value=float(settings.get("safe_score_threshold", 85)),
                step=1.0,
            )
            jupiter_prescore = st.number_input(
                "Quote Pre-score",
                min_value=1.0,
                max_value=100.0,
                value=float(settings.get("jupiter_prescore_threshold", 40)),
                step=1.0,
            )

        with c3:
            weighted_trigger = st.number_input(
                "Weighted Wallet Trigger",
                min_value=0.0,
                max_value=10.0,
                value=float(settings.get("weighted_wallet_trigger", 1.8)),
                step=0.1,
            )
            weighted_strong = st.number_input(
                "Strong Wallet Bonus Trigger",
                min_value=0.0,
                max_value=10.0,
                value=float(settings.get("weighted_wallet_strong_bonus", 3.0)),
                step=0.1,
            )
            strategy_guard_enabled = st.checkbox(
                "Strategy Guard Enabled",
                value=bool(settings.get("strategy_guard_enabled", True)),
            )

        with c4:
            base_size = st.number_input(
                "Base Paper Size USD",
                min_value=1.0,
                max_value=500.0,
                value=float(settings.get("paper_base_position_usd", 30)),
                step=1.0,
            )
            medium_size = st.number_input(
                "Medium Paper Size USD",
                min_value=1.0,
                max_value=500.0,
                value=float(settings.get("paper_medium_position_usd", 45)),
                step=1.0,
            )
            strong_size = st.number_input(
                "Strong Paper Size USD",
                min_value=1.0,
                max_value=500.0,
                value=float(settings.get("paper_strong_position_usd", 60)),
                step=1.0,
            )

        st.subheader("Confirmation Mode")
        cc1, cc2, cc3, cc4, cc5, cc6 = st.columns(6)
        with cc1:
            confirmation_min_age = st.number_input(
                "Min Launch Age Sec",
                min_value=0,
                max_value=600,
                value=int(settings.get("confirmation_min_launch_age_seconds", 30)),
                step=5,
            )
        with cc2:
            confirmation_max_age = st.number_input(
                "Max Launch Age Sec",
                min_value=15,
                max_value=1800,
                value=int(settings.get("confirmation_max_launch_age_seconds", 180)),
                step=15,
            )
        with cc3:
            confirmation_min_liquidity = st.number_input(
                "Min Liquidity USD",
                min_value=0.0,
                max_value=250000.0,
                value=float(settings.get("confirmation_min_liquidity_usd", 10000)),
                step=1000.0,
            )
        with cc4:
            confirmation_min_wallets = st.number_input(
                "Min Wallets",
                min_value=1,
                max_value=20,
                value=int(settings.get("confirmation_min_wallets", 3)),
                step=1,
            )
        with cc5:
            confirmation_min_repeated = st.number_input(
                "Min Repeat Buys",
                min_value=0,
                max_value=20,
                value=int(settings.get("confirmation_min_repeated_buys", 1)),
                step=1,
            )
        with cc6:
            confirmation_require_momentum = st.checkbox(
                "Require Momentum",
                value=bool(settings.get("confirmation_require_momentum", True)),
            )

        submitted = st.form_submit_button("Save Strategy Settings")

        if submitted:
            save_settings({
                "mode": mode,
                "cluster_threshold": cluster_threshold,
                "cluster_window": cluster_window,
                "sniper_score_threshold": sniper_threshold,
                "confirmation_score_threshold": confirmation_threshold,
                "safe_score_threshold": safe_threshold,
                "jupiter_prescore_threshold": jupiter_prescore,
                "confirmation_min_launch_age_seconds": confirmation_min_age,
                "confirmation_max_launch_age_seconds": confirmation_max_age,
                "confirmation_min_liquidity_usd": confirmation_min_liquidity,
                "confirmation_require_momentum": confirmation_require_momentum,
                "confirmation_min_wallets": confirmation_min_wallets,
                "confirmation_min_repeated_buys": confirmation_min_repeated,
                "weighted_wallet_trigger": weighted_trigger,
                "weighted_wallet_strong_bonus": weighted_strong,
                "strategy_guard_enabled": strategy_guard_enabled,
                "paper_base_position_usd": base_size,
                "paper_medium_position_usd": medium_size,
                "paper_strong_position_usd": strong_size,
            })
            st.success("Strategy settings saved. Restart the bot to apply runtime scanner changes.")
            st.rerun()

    st.caption("Scanner settings are read at bot startup. Save here, then restart the bot from the launcher.")


def run_watchdog_check():
    result = subprocess.run(
        [sys.executable, "-m", "core.rug_watchdog_once"],
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        timeout=90,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "Watchdog check failed")

    return result.stdout.strip()


def add_manual_watch(token_mint, wallet, auto_sell, alert_only):
    data = load_json(WATCHLIST_FILE, [])
    token_mint = token_mint.strip()
    wallet = wallet.strip()

    for item in data:
        if item.get("token_mint") == token_mint and item.get("wallet") == wallet:
            item["auto_sell"] = auto_sell
            item["alert_only"] = alert_only
            item["status"] = "WATCHING"
            item["last_update"] = datetime.now(timezone.utc).isoformat()
            save_json(WATCHLIST_FILE, data)
            return "updated"

    data.append({
        "token_mint": token_mint,
        "wallet": wallet,
        "status": "WATCHING",
        "risk_level": "UNKNOWN",
        "reason": "",
        "auto_sell": auto_sell,
        "alert_only": alert_only,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_update": datetime.now(timezone.utc).isoformat()
    })

    save_json(WATCHLIST_FILE, data)
    return "added"


def remove_manual_watch(index):
    data = load_json(WATCHLIST_FILE, [])
    if 0 <= index < len(data):
        data.pop(index)
        save_json(WATCHLIST_FILE, data)


def trade_card(trade, label):
    display = derive_trade_display(trade)
    exit_advice = trade.get("exit_advice") or {}

    token = pick(trade, ["token_mint", "mint", "token", "address", "ca"])
    name = pick(trade, ["name", "token_name"])
    symbol = pick(trade, ["symbol", "ticker"])
    url = pick(trade, ["url", "dex_url"], None)

    entry_mc = pick(trade, ["entry_market_cap", "entry_mc", "market_cap_at_entry", "buy_market_cap"])
    current_mc = pick(trade, ["current_market_cap", "current_mc", "market_cap"])
    exit_mc = pick(trade, ["exit_market_cap", "exit_mc", "market_cap_at_exit", "sell_market_cap"])

    pnl = pick(trade, ["pnl", "profit_loss", "realized_pnl", "unrealized_pnl"])
    pnl_pct = pick(trade, ["pnl_pct", "pnl_percent", "profit_pct", "return_pct"])

    entry_time = pick(trade, ["entry_time_iso", "entry_time", "opened_at", "buy_time", "created_at", "timestamp"])
    exit_time = pick(trade, ["exit_time_iso", "close_time_iso", "exit_time", "closed_at", "sell_time", "close_time"])
    reason = pick(trade, ["entry_reason", "reason", "exit_reason", "notes"])
    close_reason = pick(trade, ["close_reason", "exit_reason"])

    with st.container(border=True):
        st.subheader(f"{label}: {symbol if symbol != 'N/A' else token}")

        if exit_advice:
            action = exit_advice.get("action", "HOLD")
            severity = exit_advice.get("severity", "OK")
            message = f"{action} | {severity} | " + ", ".join(exit_advice.get("reasons", []))

            if action == "EXIT" or severity == "DANGER":
                st.error(message)
            elif action in ["REDUCE", "WATCH"] or severity in ["WARNING", "STALE"]:
                st.warning(message)
            elif severity == "PROFIT":
                st.success(message)
            else:
                st.info(message)

        c1, c2, c3 = st.columns(3)
        c1.write(f"**Name:** {name}")
        c2.write(f"**Symbol:** {symbol}")
        c3.write(f"**Token:** `{token}`")

        if url:
            st.link_button("Open on Dexscreener", url)

        c4, c5, c6 = st.columns(3)
        c4.metric("Entry MC", fmt_money(entry_mc))
        c5.metric("Current MC", fmt_money(current_mc))
        c6.metric("Exit MC", fmt_money(exit_mc))

        c7, c8, c9 = st.columns(3)
        c7.metric("Entry Value", fmt_money(display["entry_value"]))
        c8.metric("Current Value", fmt_money(display["current_value"]))
        c9.metric("Exit Value", fmt_money(display["exit_value"]))

        c10, c11, c12 = st.columns(3)
        c10.metric("PnL", fmt_money(pnl))
        c11.metric("PnL %", fmt_pct(pnl_pct))
        c12.write(f"**Status:** {pick(trade, ['status'])}")

        c13, c14, c15 = st.columns(3)
        c13.metric("Entry Price", fmt_price(display["entry_price"]))
        c14.metric("Current Price", fmt_price(display["current_price"]))
        c15.metric("Exit Price", fmt_price(display["close_price"]))

        if exit_advice:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("From High", fmt_pct(exit_advice.get("price_from_high_pct")))
            e2.metric("Liquidity Change", fmt_pct(exit_advice.get("liquidity_change_pct")))
            e3.metric("Trade Age", fmt_duration(exit_advice.get("age_seconds")))
            e4.metric("Exit Action", exit_advice.get("action", "N/A"))

        st.write(f"**Entry Reason:** {reason}")
        st.write(f"**Close Reason:** {close_reason}")

        st.write(f"**Entry Time:** {fmt_time(entry_time)}")
        st.write(f"**Exit Time:** {fmt_time(exit_time)}")

        with st.expander("Raw trade data"):
            st.json(trade)


state = load_json(LIVE_STATE_FILE, {})
paper_state = load_json(PAPER_TRADES_FILE, {})
wallet_perf = load_json(WALLET_PERFORMANCE_FILE, {})
watchlist = load_json(WATCHLIST_FILE, [])
runtime_status = load_json(RUNTIME_STATUS_FILE, {})
candidate_ledger = load_candidate_ledger()

open_trades = paper_state.get("open_trades", [])
closed_trades = paper_state.get("closed_trades", [])
failed_trades = paper_state.get("failed_trades", [])
alerts = state.get("alerts", [])
signals = wallet_perf.get("signals", [])

st.title("🚀 MemeTraderPro Dashboard")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Open Trades", len(open_trades))
col2.metric("Closed Trades", len(closed_trades))
col3.metric("Failed Trades", len(failed_trades))
col4.metric("Signals", len(signals))
col5.metric("Alerts", len(alerts))

st.divider()

render_operator_brief(state, paper_state, wallet_perf, watchlist, runtime_status, candidate_ledger)

st.divider()

render_command_center(state, alerts, watchlist, candidate_ledger)

st.divider()

render_token_console(state, paper_state, watchlist, candidate_ledger)

st.divider()

render_runtime_health(runtime_status)

st.divider()

render_system_readiness()

st.divider()

render_execution_safety()

st.divider()

render_data_store()

st.divider()

render_strategy_settings()

st.divider()

render_performance_intelligence(paper_state)

st.divider()

render_trade_postmortem(paper_state)

st.divider()

render_replay_lab(alerts, paper_state)

st.divider()

render_pipeline_health(alerts, signals)

st.divider()

render_wallet_intelligence(wallet_perf)

st.divider()

render_paper_copy_engine(wallet_perf)

st.divider()

st.header("🛡️ Manual Trade Protection")

if st.button("Run Protection Check Now"):
    try:
        output = run_watchdog_check()
        st.success(output or "Protection check complete")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

with st.form("manual_trade_protection_form"):
    token_mint = st.text_input("Token Mint / Contract Address")
    wallet = st.text_input("Your Wallet Address")

    c1, c2 = st.columns(2)
    with c1:
        auto_sell = st.checkbox("Enable Auto Sell", value=False)
    with c2:
        alert_only = st.checkbox("Alert Only", value=True)

    submitted = st.form_submit_button("Add / Update")

    if submitted:
        if not token_mint.strip():
            st.error("Token mint required")
        else:
            result = add_manual_watch(token_mint, wallet, auto_sell, alert_only)
            st.success(f"Watchlist {result}")

st.subheader("📊 Protected Positions")

if not watchlist:
    st.info("No tracked positions")
else:
    counts = Counter(item.get("alert_level") or str(item.get("risk_level", "unknown")).lower() for item in watchlist)
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Protected", len(watchlist))
    p2.metric("Emergency", counts.get("emergency", 0))
    p3.metric("Danger", counts.get("danger", 0))
    p4.metric("Warning", counts.get("warning", 0))
    p5.metric("Info/Safe", counts.get("info", 0) + counts.get("safe", 0))

    for i, item in enumerate(watchlist):
        risk = item.get("risk_level", "UNKNOWN")
        status = item.get("status", "UNKNOWN")
        alert_level = item.get("alert_level") or str(risk).lower()
        last_check_age = age_from_iso(item.get("last_update"))

        with st.container(border=True):
            banner = f"{status} | {risk} | {alert_level.upper()}"
            if alert_level == "emergency":
                st.error(banner)
            elif alert_level == "danger":
                st.error(banner)
            elif alert_level == "warning":
                st.warning(banner)
            else:
                st.success(banner)

            st.write(f"**Token:** `{item.get('token_mint')}`")
            st.write(f"**Wallet:** `{item.get('wallet')}`")
            st.write(f"**Reason:** {item.get('reason', '')}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Price", fmt_price(item.get("current_price")))
            m2.metric("Liquidity", fmt_money(item.get("current_liquidity")))
            m3.metric("Price From Peak", fmt_pct(item.get("price_from_peak_pct")))
            m4.metric("Liquidity From Peak", fmt_pct(item.get("liquidity_from_peak_pct")))

            detail_rows = [
                {"field": "last_check_age", "value": fmt_duration(last_check_age)},
                {"field": "last_update", "value": table_value(item.get("last_update"))},
                {"field": "auto_sell", "value": "armed" if item.get("auto_sell") else "locked/off"},
                {"field": "alert_only", "value": bool(item.get("alert_only", True))},
                {"field": "token_standard", "value": table_value(item.get("token_standard"))},
                {"field": "token_mechanics_risk", "value": table_value(item.get("token_mechanics_risk"))},
                {"field": "extensions", "value": ", ".join(item.get("token_extensions") or []) or "N/A"},
            ]
            st.dataframe(detail_rows, hide_index=True, width="stretch")

            if item.get("url"):
                st.link_button("Open Market", item.get("url"), key=f"market_{i}")

            if st.button("Remove", key=f"remove_watch_{i}"):
                remove_manual_watch(i)
                st.rerun()

st.divider()

st.header("📈 Open Trades")

if not open_trades:
    st.info("No open trades")
else:
    for idx, trade in enumerate(open_trades):
        trade_card(trade, f"Open Trade #{idx + 1}")

st.divider()

st.header("✅ Closed Trades")

if not closed_trades:
    st.info("No closed trades")
else:
    for idx, trade in enumerate(closed_trades[-20:][::-1]):
        trade_card(trade, f"Closed Trade #{idx + 1}")

st.divider()

st.header("❌ Failed Trades")

if not failed_trades:
    st.info("No failed trades")
else:
    for idx, trade in enumerate(failed_trades[-20:][::-1]):
        trade_card(trade, f"Failed Trade #{idx + 1}")

st.divider()

st.header("🚨 Alerts")

if not alerts:
    st.info("No alerts")
else:
    for alert in alerts[-25:][::-1]:
        with st.container(border=True):
            st.write(alert)

st.divider()

with st.expander("🧪 Raw Paper Trades File"):
    st.json(paper_state)

with st.expander("🧪 Raw Live State"):
    st.json(state)

with st.expander("📊 Wallet Signals Sample"):
    st.json(signals[:10])

with st.expander("🛡️ Watchlist"):
    st.json(watchlist)
