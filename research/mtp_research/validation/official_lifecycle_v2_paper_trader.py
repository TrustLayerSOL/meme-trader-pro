"""Paper-only v2 lifecycle trade monitor.

This sidecar reads official lifecycle v2 label files and records simulated
paper entries/exits. It never builds, signs, routes, or submits transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv
import html
import json
import time

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleV2Config, _read_jsonl


ENTRY_RULE_ID = "MTP_V2_BASELINE_ACTIONABLE_20K_ENTRY"
EXIT_RULE_ID = "MTP_V2_E2_TRAILING_DRAWDOWN_EXIT"


@dataclass(frozen=True)
class OfficialV2PaperTradeConfig:
    data_root: Path | str | None = None
    starting_wallet_usd: float = 300.0
    position_fraction: float = 0.05

    @property
    def root(self) -> Path:
        return Path(self.data_root or data_lake_root()).expanduser()

    @property
    def lifecycle(self) -> OfficialLifecycleV2Config:
        return OfficialLifecycleV2Config(data_root=self.root)

    @property
    def observation_root(self) -> Path:
        return self.lifecycle.observation_root

    @property
    def report_root(self) -> Path:
        return self.lifecycle.report_root / "paper_trade_monitor"

    @property
    def config_path(self) -> Path:
        return self.observation_root / "paper_trading_v2_config.json"

    @property
    def state_path(self) -> Path:
        return self.observation_root / "paper_trading_v2_state.json"

    @property
    def ledger_path(self) -> Path:
        return self.observation_root / "paper_trading_v2_ledger.jsonl"

    @property
    def trades_csv_path(self) -> Path:
        return self.report_root / "paper_trading_v2_trades.csv"

    @property
    def monitor_json_path(self) -> Path:
        return self.report_root / "paper_trading_v2_monitor.json"

    @property
    def monitor_md_path(self) -> Path:
        return self.report_root / "paper_trading_v2_monitor.md"

    @property
    def monitor_html_path(self) -> Path:
        return self.report_root / "paper_trading_v2_monitor.html"


def initialize_paper_trader(config: OfficialV2PaperTradeConfig, *, reset: bool = False) -> dict[str, Any]:
    config.observation_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    if reset or not config.state_path.exists():
        _write_json(config.state_path, _initial_state(config))
        config.ledger_path.write_text("", encoding="utf-8")
    config.ledger_path.touch(exist_ok=True)
    payload = {
        "enabled": True,
        "mode": "paper_only_sidecar",
        "entry_rule_id": ENTRY_RULE_ID,
        "entry_rule": "Buy when official v2 baseline actionable crossed-20k label appears.",
        "exit_rule_id": EXIT_RULE_ID,
        "exit_rule": "Sell when E2 hypothetical exit condition appears.",
        "starting_wallet_usd": config.starting_wallet_usd,
        "position_fraction": config.position_fraction,
        "position_sizing": "5% of current paper wallet per buy",
        "no_live_trading": True,
        "no_wallet_execution": True,
        "no_transaction_signing": True,
        "no_order_routing": True,
    }
    _write_json(config.config_path, payload)
    _write_monitor(config, _load_state(config), _read_ledger(config))
    return {
        "enabled": True,
        "state_path": str(config.state_path),
        "ledger_path": str(config.ledger_path),
        "monitor_html_path": str(config.monitor_html_path),
        "monitor_md_path": str(config.monitor_md_path),
        "monitor_json_path": str(config.monitor_json_path),
    }


def run_paper_trade_once(config: OfficialV2PaperTradeConfig) -> dict[str, Any]:
    if not config.state_path.exists():
        initialize_paper_trader(config)
    state = _load_state(config)
    ledger = _read_ledger(config)
    metadata = _metadata_by_mint(config)
    paths_by_mint = _paths_by_mint(config)
    buys_created = 0
    sells_created = 0

    for label in _read_jsonl(config.lifecycle.paper_shadow_labels_path):
        mint = str(label.get("mint") or "")
        if not mint or mint in state["open_positions"] or mint in state["closed_mints"]:
            continue
        if label.get("official_baseline_entry_eligible") is not True or label.get("baseline_all_actionable_20k") is not True:
            continue
        label_time = _num(label.get("label_time") or label.get("timestamp")) or time.time()
        path = _nearest_path(paths_by_mint.get(mint, []), label_time, require_crossed_20k=True)
        buy_marketcap = _num((path or {}).get("fdv_proxy"))
        if buy_marketcap is None or buy_marketcap <= 0:
            continue
        meta = metadata.get(mint, {})
        wallet_before = float(state["wallet_usd"])
        allocation = _round_money(min(wallet_before * float(state["position_fraction"]), float(state["cash_usd"])))
        if allocation <= 0:
            continue
        units = allocation / buy_marketcap
        position = {
            "mint": mint,
            "token_name": meta.get("token_name"),
            "token_symbol": meta.get("token_symbol"),
            "image_uri": meta.get("image_uri"),
            "opened_at": label_time,
            "buy_marketcap": buy_marketcap,
            "buy_reason": ENTRY_RULE_ID,
            "buy_reason_detail": "official baseline actionable crossed-20k label",
            "allocation_usd": allocation,
            "paper_units": units,
            "entry_label": _b_label(label),
        }
        state["cash_usd"] = _round_money(float(state["cash_usd"]) - allocation)
        state["open_positions"][mint] = position
        row = {
            **position,
            "timestamp": label_time,
            "side": "paper_buy",
            "wallet_before_usd": _round_money(wallet_before),
            "wallet_after_usd": _round_money(state["cash_usd"] + _open_cost_basis(state)),
            "paper_profit_loss_usd": 0.0,
            "no_live_trade": True,
        }
        ledger.append(row)
        buys_created += 1

    for exit_row in _read_jsonl(config.lifecycle.paper_shadow_exit_labels_path):
        mint = str(exit_row.get("mint") or "")
        if not mint or mint not in state["open_positions"] or mint in state["closed_mints"]:
            continue
        if exit_row.get("hypothetical_exit_condition_met") is not True:
            continue
        position = state["open_positions"].pop(mint)
        sell_time = _num(exit_row.get("timestamp")) or time.time()
        sell_marketcap = _num(exit_row.get("current_fdv")) or _num((_nearest_path(paths_by_mint.get(mint, []), sell_time) or {}).get("fdv_proxy"))
        if sell_marketcap is None or sell_marketcap <= 0:
            state["open_positions"][mint] = position
            continue
        wallet_before = _round_money(float(state["cash_usd"]) + _open_cost_basis(state) + float(position["allocation_usd"]))
        proceeds = _round_money(float(position["paper_units"]) * sell_marketcap)
        profit_loss = _round_money(proceeds - float(position["allocation_usd"]))
        state["cash_usd"] = _round_money(float(state["cash_usd"]) + proceeds)
        state["closed_mints"].append(mint)
        row = {
            **position,
            "timestamp": sell_time,
            "side": "paper_sell",
            "sell_marketcap": sell_marketcap,
            "sell_reason": exit_row.get("hypothetical_exit_reason") or EXIT_RULE_ID,
            "exit_rule_id": EXIT_RULE_ID,
            "wallet_before_usd": wallet_before,
            "wallet_after_usd": _round_money(float(state["cash_usd"]) + _open_cost_basis(state)),
            "paper_profit_loss_usd": profit_loss,
            "paper_return_pct": _round_pct(profit_loss / float(position["allocation_usd"]) if position.get("allocation_usd") else 0),
            "no_live_trade": True,
        }
        ledger.append(row)
        sells_created += 1

    state["wallet_usd"] = _round_money(float(state["cash_usd"]) + _open_cost_basis(state))
    state["updated_at"] = _utc_now()
    _write_json(config.state_path, state)
    _write_ledger(config, ledger)
    _write_monitor(config, state, ledger)
    return {
        "enabled": True,
        "buys_created": buys_created,
        "sells_created": sells_created,
        "open_positions": len(state["open_positions"]),
        "closed_trades": len([row for row in ledger if row.get("side") == "paper_sell"]),
        "wallet_usd": state["wallet_usd"],
        "monitor_html_path": str(config.monitor_html_path),
        "ledger_path": str(config.ledger_path),
    }


def paper_trade_status(config: OfficialV2PaperTradeConfig) -> dict[str, Any]:
    if not config.state_path.exists():
        return {"enabled": False}
    state = _load_state(config)
    ledger = _read_ledger(config)
    return {
        "enabled": True,
        "wallet_usd": state.get("wallet_usd"),
        "cash_usd": state.get("cash_usd"),
        "open_positions": len(state.get("open_positions") or {}),
        "closed_trades": len([row for row in ledger if row.get("side") == "paper_sell"]),
        "ledger_rows": len(ledger),
        "monitor_html_path": str(config.monitor_html_path),
        "monitor_md_path": str(config.monitor_md_path),
        "ledger_path": str(config.ledger_path),
        "state_path": str(config.state_path),
    }


def _initial_state(config: OfficialV2PaperTradeConfig) -> dict[str, Any]:
    wallet = _round_money(config.starting_wallet_usd)
    return {
        "enabled": True,
        "mode": "paper_only_sidecar",
        "starting_wallet_usd": wallet,
        "wallet_usd": wallet,
        "cash_usd": wallet,
        "position_fraction": float(config.position_fraction),
        "open_positions": {},
        "closed_mints": [],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "guardrails": ["no_live_trading", "no_wallet_execution", "no_transaction_signing", "paper_only_accounting"],
    }


def _write_monitor(config: OfficialV2PaperTradeConfig, state: dict[str, Any], ledger: list[dict[str, Any]]) -> None:
    sells = [row for row in ledger if row.get("side") == "paper_sell"]
    current_marketcaps = _latest_marketcaps_by_mint(config)
    open_positions = [
        _enrich_open_position(row, current_marketcaps.get(str(row.get("mint") or "")))
        for row in (state.get("open_positions") or {}).values()
    ]
    payload = {
        "updated_at": _utc_now(),
        "wallet_usd": state.get("wallet_usd"),
        "cash_usd": state.get("cash_usd"),
        "starting_wallet_usd": state.get("starting_wallet_usd"),
        "position_fraction": state.get("position_fraction"),
        "open_positions": open_positions,
        "closed_trades": sells,
        "current_market_caps": [
            {
                "mint": row.get("mint"),
                "token_name": row.get("token_name"),
                "token_symbol": row.get("token_symbol"),
                "current_marketcap": row.get("current_marketcap"),
                "buy_marketcap": row.get("buy_marketcap"),
            }
            for row in open_positions
        ],
        "ledger_rows": len(ledger),
        "total_paper_profit_loss_usd": _round_money(sum(float(row.get("paper_profit_loss_usd") or 0) for row in sells)),
        "no_live_trade": True,
    }
    _write_json(config.monitor_json_path, payload)
    config.monitor_md_path.write_text(_monitor_markdown(payload), encoding="utf-8")
    config.monitor_html_path.write_text(_monitor_html(payload), encoding="utf-8")
    _write_csv(config.trades_csv_path, ledger)


def _monitor_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Official Lifecycle v2 Paper Trade Monitor",
        "",
        f"Updated: {payload['updated_at']}",
        f"Wallet: ${payload['wallet_usd']}",
        f"Cash: ${payload['cash_usd']}",
        f"Open positions: {len(payload['open_positions'])}",
        f"Closed trades: {len(payload['closed_trades'])}",
        f"Total paper P/L: ${payload['total_paper_profit_loss_usd']}",
        "",
        "This is paper-only accounting. No live trades, wallet execution, signing, swaps, or routing.",
        "",
        "## Current Market Caps",
    ]
    for row in payload["current_market_caps"]:
        lines.append(
            f"- {row.get('token_name') or row.get('mint')}: CA {row.get('mint')}, "
            f"current MC ${row.get('current_marketcap')} (bought MC ${row.get('buy_marketcap')})"
        )
    lines.extend(
        [
            "",
            "## Open Positions",
        ]
    )
    for row in payload["open_positions"]:
        lines.append(
            f"- {row.get('token_name') or row.get('mint')} ({row.get('token_symbol') or 'n/a'}): "
            f"CA {row.get('mint')}, bought at MC ${row.get('buy_marketcap')}, "
            f"current MC ${row.get('current_marketcap')} because {row.get('buy_reason')}"
        )
    lines.append("")
    lines.append("## Closed Trades")
    for row in payload["closed_trades"]:
        lines.append(
            f"- {row.get('token_name') or row.get('mint')}: bought MC ${row.get('buy_marketcap')}, sold MC ${row.get('sell_marketcap')}, P/L ${row.get('paper_profit_loss_usd')}, sell reason {row.get('sell_reason')}"
        )
    return "\n".join(lines) + "\n"


def _monitor_html(payload: dict[str, Any]) -> str:
    rows = payload["open_positions"] + payload["closed_trades"]
    current_marketcap_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('token_name') or row.get('mint') or ''))}</td>"
        f"<td>{_ca_button(row.get('mint'))}</td>"
        f"<td>${html.escape(str(row.get('current_marketcap') or ''))}</td>"
        f"<td>${html.escape(str(row.get('buy_marketcap') or ''))}</td>"
        "</tr>"
        for row in payload["current_market_caps"]
    )
    table = "\n".join(
        "<tr>"
        f"<td>{_img(row.get('image_uri'))}</td>"
        f"<td>{html.escape(str(row.get('token_name') or row.get('mint') or ''))}<br><small>{html.escape(str(row.get('token_symbol') or ''))}</small><br>{_ca_button(row.get('mint'))}</td>"
        f"<td>{html.escape(str(row.get('side') or 'open'))}</td>"
        f"<td>${html.escape(str(row.get('allocation_usd') or ''))}</td>"
        f"<td>${html.escape(str(row.get('buy_marketcap') or ''))}</td>"
        f"<td>${html.escape(str(row.get('current_marketcap') or row.get('sell_marketcap') or 'open'))}</td>"
        f"<td>${html.escape(str(row.get('sell_marketcap') or 'open'))}</td>"
        f"<td>${html.escape(str(row.get('paper_profit_loss_usd') if row.get('paper_profit_loss_usd') is not None else 'open'))}</td>"
        f"<td>{html.escape(str(row.get('buy_reason') or ''))}<br>{html.escape(str(row.get('sell_reason') or ''))}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"10\">
<title>MTP v2 Paper Monitor</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f7f7f4;color:#1f2933}}
.stats{{display:flex;gap:12px;flex-wrap:wrap}} .stat{{background:white;border:1px solid #ddd;border-radius:8px;padding:12px 16px}}
table{{border-collapse:collapse;width:100%;background:white;margin-top:18px}} th,td{{border-bottom:1px solid #e5e7eb;padding:10px;text-align:left;vertical-align:middle}} img{{width:44px;height:44px;object-fit:cover;border-radius:6px}}
small{{color:#667085}} .guard{{color:#7a2e0e;margin-top:12px}} button.ca{{border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:4px 8px;cursor:pointer;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
</style><script>
function copyCA(value){{navigator.clipboard.writeText(value).then(function(){{document.getElementById('copy-status').textContent='Copied CA: '+value;}});}}
</script></head><body>
<h1>MemeTraderPro v2 Paper Monitor</h1>
<div class=\"stats\"><div class=\"stat\">Wallet<br><b>${payload['wallet_usd']}</b></div><div class=\"stat\">Cash<br><b>${payload['cash_usd']}</b></div><div class=\"stat\">Open<br><b>{len(payload['open_positions'])}</b></div><div class=\"stat\">Closed<br><b>{len(payload['closed_trades'])}</b></div><div class=\"stat\">Paper P/L<br><b>${payload['total_paper_profit_loss_usd']}</b></div></div>
<p class=\"guard\">Paper-only monitor. No live trades, wallet execution, signing, swaps, or routing.</p>
<p id=\"copy-status\"><small>Click any CA to copy it.</small></p>
<h2>Current Market Caps</h2>
<table><thead><tr><th>Token</th><th>CA</th><th>Current MC</th><th>Buy MC</th></tr></thead><tbody>{current_marketcap_rows}</tbody></table>
<h2>Trades</h2>
<table><thead><tr><th>Image</th><th>Token / CA</th><th>Status</th><th>Size</th><th>Buy MC</th><th>Current MC</th><th>Sell MC</th><th>P/L</th><th>Why</th></tr></thead><tbody>{table}</tbody></table>
<p><small>Updated {payload['updated_at']}. Auto-refreshes every 10 seconds.</small></p>
</body></html>"""


def _img(uri: Any) -> str:
    if not uri:
        return ""
    return f"<img src=\"{html.escape(str(uri), quote=True)}\" alt=\"token image\">"


def _ca_button(mint: Any) -> str:
    if not mint:
        return ""
    value = str(mint)
    return (
        f"<button class=\"ca\" onclick=\"copyCA('{html.escape(value, quote=True)}')\" "
        f"title=\"Copy contract address\">{html.escape(value)}</button>"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["timestamp", "side", "mint", "token_name", "token_symbol", "allocation_usd", "buy_marketcap", "current_marketcap", "sell_marketcap", "paper_profit_loss_usd", "buy_reason", "sell_reason", "image_uri"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def _metadata_by_mint(config: OfficialV2PaperTradeConfig) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(config.lifecycle.metadata_snapshots_path) + _read_jsonl(config.lifecycle.metadata_path)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mint = row.get("mint")
        if mint:
            out[str(mint)] = {**out.get(str(mint), {}), **row}
    return out


def _paths_by_mint(config: OfficialV2PaperTradeConfig) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(config.lifecycle.followup_paths_path):
        mint = row.get("mint")
        if mint:
            out.setdefault(str(mint), []).append(row)
    return out


def _latest_marketcaps_by_mint(config: OfficialV2PaperTradeConfig) -> dict[str, float]:
    out: dict[str, float] = {}
    latest_ts: dict[str, float] = {}
    for row in _read_jsonl(config.lifecycle.followup_paths_path):
        mint = str(row.get("mint") or "")
        fdv = _num(row.get("fdv_proxy"))
        timestamp = _num(row.get("timestamp")) or 0.0
        if not mint or fdv is None:
            continue
        if mint not in latest_ts or timestamp >= latest_ts[mint]:
            latest_ts[mint] = timestamp
            out[mint] = fdv
    return out


def _enrich_open_position(row: dict[str, Any], current_marketcap: float | None) -> dict[str, Any]:
    enriched = dict(row)
    if current_marketcap is not None:
        enriched["current_marketcap"] = current_marketcap
        allocation = _num(enriched.get("allocation_usd")) or 0.0
        units = _num(enriched.get("paper_units")) or 0.0
        current_value = _round_money(units * current_marketcap)
        enriched["current_paper_value_usd"] = current_value
        enriched["unrealized_paper_profit_loss_usd"] = _round_money(current_value - allocation)
    return enriched


def _nearest_path(rows: list[dict[str, Any]], timestamp: float, *, require_crossed_20k: bool = False) -> dict[str, Any] | None:
    candidates = [row for row in rows if not require_crossed_20k or row.get("crossed_20k") is True]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs((_num(row.get("timestamp")) or timestamp) - timestamp))


def _b_label(row: dict[str, Any]) -> str:
    for label in ["B1", "B2", "B3", "B4"]:
        if row.get(f"{label}_pass") is True:
            return label
    return "baseline"


def _open_cost_basis(state: dict[str, Any]) -> float:
    return sum(float(row.get("allocation_usd") or 0) for row in (state.get("open_positions") or {}).values())


def _load_state(config: OfficialV2PaperTradeConfig) -> dict[str, Any]:
    return json.loads(config.state_path.read_text(encoding="utf-8"))


def _read_ledger(config: OfficialV2PaperTradeConfig) -> list[dict[str, Any]]:
    if not config.ledger_path.exists():
        return []
    return [json.loads(line) for line in config.ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_ledger(config: OfficialV2PaperTradeConfig, rows: list[dict[str, Any]]) -> None:
    config.ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _round_pct(value: float) -> float:
    return round(float(value) * 100, 4)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
