import json
import os
import time
from datetime import datetime, timezone

from core.json_store import locked_update_json
from core.decision_ledger import build_trade_result
from core.paper_trade_decision_ids import (
    synthetic_decision_payload_from_trade,
    synthetic_trade_decision_id,
    trade_decision_id,
)
from execution.execution_engine import ExecutionEngine
from core.wallet_performance import WalletPerformanceTracker
from core.exit_advisor import ExitAdvisor
from core.storage import EventStore


PAPER_TRADES_FILE = "data/paper_trades.json"


class PaperTrader:
    def __init__(self):
        self.engine = ExecutionEngine()
        self.wallet_performance = WalletPerformanceTracker()
        self.exit_advisor = ExitAdvisor()
        self.store = EventStore()
        self.state = self.load_state()

    def load_state(self):
        if not os.path.exists(PAPER_TRADES_FILE):
            return self.normalize_state({
                "balance": 10000,
                "open_trades": [],
                "closed_trades": [],
                "failed_trades": [],
                "stats": {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "failed_trades": 0,
                    "realized_pnl": 0,
                    "total_fees": 0,
                    "win_rate": 0,
                },
            })

        with open(PAPER_TRADES_FILE, "r") as f:
            return self.normalize_state(json.load(f))

    def save_state(self):
        os.makedirs(os.path.dirname(PAPER_TRADES_FILE), exist_ok=True)
        self.state = locked_update_json(
            PAPER_TRADES_FILE,
            self.default_state(),
            lambda current: self.merge_state_for_save(current, self.state),
        )
        self.sync_trades_to_store()

    def default_state(self):
        return self.normalize_state({
            "balance": 10000,
            "open_trades": [],
            "closed_trades": [],
            "failed_trades": [],
            "stats": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "failed_trades": 0,
                "realized_pnl": 0,
                "total_fees": 0,
                "win_rate": 0,
            },
        })

    def trade_key(self, trade):
        if not isinstance(trade, dict):
            return None
        return (
            trade.get("id")
            or trade.get("trade_id")
            or (
                trade.get("mint"),
                trade.get("entry_time") or trade.get("time") or trade.get("time_iso"),
            )
        )

    def open_trade_key(self, trade):
        if not isinstance(trade, dict):
            return None
        mint = trade.get("mint") or trade.get("token_mint")
        return ("open", mint) if mint and trade.get("status") == "open" else self.trade_key(trade)

    def merge_trade_lists(self, current_list, updated_list, limit=None):
        merged = []
        seen = set()
        for trade in updated_list or []:
            key = self.trade_key(trade)
            if key is None or key in seen:
                continue
            merged.append(trade)
            seen.add(key)
        for trade in current_list or []:
            key = self.trade_key(trade)
            if key is None or key in seen:
                continue
            merged.append(trade)
            seen.add(key)
        return merged[:limit] if limit else merged

    def merge_open_trades(self, current_list, updated_list):
        merged = []
        seen = set()
        current_by_mint = {
            self.open_trade_key(trade): trade
            for trade in current_list or []
            if self.open_trade_key(trade) is not None
        }
        for trade in updated_list or []:
            key = self.open_trade_key(trade)
            if key is None or key in seen:
                continue
            current_trade = current_by_mint.get(key)
            if (
                current_trade
                and current_trade.get("entry_time") != trade.get("entry_time")
            ):
                kept = dict(current_trade)
                kept["duplicate_open_attempts"] = int(kept.get("duplicate_open_attempts", 0) or 0) + 1
                kept["last_duplicate_open_attempt_at"] = self.iso_time()
                kept["last_duplicate_open_attempt_reason"] = trade.get("entry_reason") or trade.get("reason")
                merged.append(kept)
            else:
                merged.append(trade)
            seen.add(key)

        for trade in current_list or []:
            key = self.open_trade_key(trade)
            if key is None or key in seen:
                continue
            merged.append(trade)
            seen.add(key)
        return merged

    def hydrate_missing_trade_decision_lineage(self, state):
        """Mutate ``state`` so every trade has decision_id / signal_metadata.decision_id."""
        if not isinstance(state, dict):
            return 0
        hydrated = 0
        for bucket in ("open_trades", "closed_trades", "failed_trades"):
            rows = state.get(bucket)
            if not isinstance(rows, list):
                continue
            for trade in rows:
                if not isinstance(trade, dict):
                    continue
                if trade_decision_id(trade):
                    continue
                decision_id = synthetic_trade_decision_id(trade, bucket)
                metadata = dict(trade.get("signal_metadata") or {})
                metadata.setdefault("signal_type", metadata.get("signal_type") or "legacy_paper_trade")
                metadata["decision_id"] = decision_id
                trade["signal_metadata"] = metadata
                trade["decision_id"] = decision_id
                try:
                    self.store.upsert_decision(
                        synthetic_decision_payload_from_trade(trade, bucket, decision_id)
                    )
                except Exception as exc:
                    print("⚠️ Legacy decision upsert failed:", exc)
                hydrated += 1
        return hydrated

    def merge_state_for_save(self, current, updated):
        if not isinstance(current, dict):
            current = self.default_state()
        if not isinstance(updated, dict):
            updated = self.default_state()

        merged = dict(current)
        merged.update(updated)
        terminal_keys = {
            self.trade_key(trade)
            for trade in (
                (current.get("closed_trades", []) or [])
                + (current.get("failed_trades", []) or [])
                + (updated.get("closed_trades", []) or [])
                + (updated.get("failed_trades", []) or [])
            )
            if self.trade_key(trade) is not None
        }
        current_open = [
            trade for trade in current.get("open_trades", [])
            if self.trade_key(trade) not in terminal_keys
        ]
        updated_open = [
            trade for trade in updated.get("open_trades", [])
            if self.trade_key(trade) not in terminal_keys
        ]
        merged["open_trades"] = self.merge_open_trades(
            current_open,
            updated_open,
        )
        merged["closed_trades"] = self.merge_trade_lists(
            current.get("closed_trades", []),
            updated.get("closed_trades", []),
            limit=500,
        )
        merged["failed_trades"] = self.merge_trade_lists(
            current.get("failed_trades", []),
            updated.get("failed_trades", []),
            limit=500,
        )
        return self.normalize_state(merged)

    def sync_trades_to_store(self):
        try:
            for key in ["open_trades", "closed_trades", "failed_trades"]:
                for trade in self.state.get(key, []):
                    if isinstance(trade, dict):
                        self.store.upsert_trade(trade)
            from utils.sync_state_to_sqlite import sync_decision_results
            sync_decision_results(self.store, self.state, create_missing=True)
        except Exception:
            pass

    def iso_time(self, timestamp=None):
        timestamp = time.time() if timestamp is None else float(timestamp)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    def first_number(self, *values):
        for value in values:
            try:
                if value not in [None, ""]:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def normalize_signal_metadata(self, signal_metadata, decision_id=None):
        metadata = dict(signal_metadata) if isinstance(signal_metadata, dict) else {}
        decision_id = decision_id or metadata.get("decision_id")
        if decision_id:
            metadata["decision_id"] = decision_id
        return metadata

    def attach_decision_lineage(self, trade, signal_metadata=None):
        if not isinstance(trade, dict):
            return trade

        metadata = self.normalize_signal_metadata(
            signal_metadata if signal_metadata is not None else trade.get("signal_metadata"),
            trade.get("decision_id"),
        )
        decision_id = trade.get("decision_id") or metadata.get("decision_id")
        trade["signal_metadata"] = metadata
        if decision_id:
            trade["decision_id"] = decision_id
        return trade

    def market_cap_from_info(self, market_info):
        if not isinstance(market_info, dict):
            return None
        return self.first_number(
            market_info.get("market_cap"),
            market_info.get("marketCap"),
            market_info.get("fdv"),
        )

    def record_trade_snapshot(self, trade, context, extra=None):
        if not isinstance(trade, dict):
            return

        mint = trade.get("mint") or trade.get("token_mint")
        if not mint:
            return

        market_info = trade.get("market_info") if isinstance(trade.get("market_info"), dict) else {}
        signal_metadata = (
            trade.get("signal_metadata")
            if isinstance(trade.get("signal_metadata"), dict)
            else {}
        )
        decision_id = trade.get("decision_id") or signal_metadata.get("decision_id")
        if decision_id:
            signal_metadata = self.normalize_signal_metadata(signal_metadata, decision_id)
            trade["signal_metadata"] = signal_metadata
            trade["decision_id"] = decision_id
        now = time.time()
        snapshot = {
            "time": now,
            "timestamp": now,
            "source": "paper_trader",
            "context": context,
            "decision_id": decision_id,
            "mint": mint,
            "token_mint": mint,
            "status": trade.get("status"),
            "price": self.first_number(
                trade.get("current_price"),
                trade.get("entry_price"),
                market_info.get("price"),
            ),
            "liquidity": self.first_number(
                trade.get("current_liquidity_usd"),
                trade.get("entry_liquidity_usd"),
                trade.get("liquidity_usd"),
                market_info.get("liquidity"),
            ),
            "market_cap": self.first_number(
                trade.get("current_market_cap"),
                trade.get("entry_market_cap"),
                self.market_cap_from_info(market_info),
            ),
            "risk_label": signal_metadata.get("risk_label"),
            "risk_score": signal_metadata.get("risk_score"),
            "entry_price": trade.get("entry_price"),
            "quoted_entry_price": trade.get("quoted_entry_price"),
            "size_usd": trade.get("size_usd"),
            "remaining_pct": trade.get("remaining_pct"),
            "remaining_token_amount": trade.get("remaining_token_amount"),
            "initial_token_amount": trade.get("initial_token_amount"),
            "total_pnl": trade.get("total_pnl"),
            "total_pnl_pct": trade.get("total_pnl_pct"),
            "realized_pnl": trade.get("realized_pnl"),
            "unrealized_pnl": trade.get("unrealized_pnl"),
            "entry_time": trade.get("entry_time"),
            "close_time": trade.get("close_time"),
            "entry_reason": trade.get("entry_reason") or trade.get("reason"),
            "exit_reason": trade.get("exit_reason") or trade.get("close_reason"),
            "wallets": trade.get("wallets", []),
            "signal_metadata": signal_metadata,
        }

        if isinstance(extra, dict):
            snapshot.update(extra)

        try:
            self.store.insert_token_snapshot(snapshot)
        except Exception as exc:
            print("⚠️ Paper trade snapshot write failed:", exc)

        if decision_id:
            try:
                final_action = {
                    "paper_entry_opened": "paper_opened",
                    "paper_entry_failed": "paper_failed",
                    "paper_partial_exit": "paper_partial_exit",
                    "paper_exit_closed": "paper_closed",
                    "paper_exit_failed": "paper_exit_failed",
                    "paper_price_update": "paper_monitor",
                }.get(context)
                action_reason = None
                if isinstance(extra, dict):
                    action_reason = extra.get("failure_reason") or extra.get("exit_reason")
                if final_action:
                    self.store.update_decision_action(decision_id, {
                        "scanner_stage": extra.get("decision_stage") if isinstance(extra, dict) else context,
                        "final_action": final_action,
                        "reason": (
                            trade.get("failure_reason")
                            or action_reason
                            or trade.get("exit_reason")
                            or trade.get("close_reason")
                            or context
                        ),
                        "paper_lane": trade.get("paper_lane") or signal_metadata.get("paper_lane"),
                    })
                self.store.update_decision_result(
                    decision_id,
                    build_trade_result(trade, context, extra),
                )
            except Exception as exc:
                print("⚠️ Decision result update failed:", exc)

    def apply_trade_aliases(self, trade):
        if not isinstance(trade, dict):
            return trade

        self.attach_decision_lineage(trade)

        mint = trade.get("mint") or trade.get("token_mint")
        if mint:
            trade["mint"] = mint
            trade["token_mint"] = mint

        reason = trade.get("entry_reason") or trade.get("reason")
        if reason:
            trade["reason"] = reason
            trade["entry_reason"] = reason

        entry_time = trade.get("entry_time") or trade.get("opened_at")
        if entry_time and not trade.get("entry_time_iso"):
            trade["entry_time_iso"] = self.iso_time(entry_time)

        close_time = trade.get("close_time") or trade.get("exit_time") or trade.get("closed_at")
        if close_time and not trade.get("close_time_iso"):
            trade["close_time_iso"] = self.iso_time(close_time)
            trade["exit_time_iso"] = trade["close_time_iso"]

        size_usd = self.first_number(trade.get("size_usd"), trade.get("entry_value"))
        entry_price = self.first_number(trade.get("entry_price"))
        current_price = self.first_number(trade.get("current_price"), entry_price)
        close_price = self.first_number(trade.get("close_price"))
        initial_tokens = self.first_number(trade.get("initial_token_amount"))
        remaining_tokens = self.first_number(trade.get("remaining_token_amount"))

        if size_usd is not None:
            trade["size_usd"] = size_usd
            trade["entry_value"] = size_usd

        if entry_price is not None:
            trade["entry_price"] = entry_price

        if current_price is not None:
            trade["current_price"] = current_price

        if initial_tokens is not None and remaining_tokens is not None and current_price is not None:
            trade["current_value"] = remaining_tokens * current_price

        if close_price is not None:
            trade["exit_price"] = close_price

        if close_price is not None and initial_tokens is not None:
            trade.setdefault("exit_value", sum(
                self.first_number(sell.get("net_proceeds")) or 0
                for sell in trade.get("sells", [])
                if isinstance(sell, dict)
            ))

        pnl = self.first_number(trade.get("total_pnl"), trade.get("pnl"))
        pnl_pct = self.first_number(trade.get("total_pnl_pct"), trade.get("pnl_pct"))

        if pnl is not None:
            trade["pnl"] = pnl
            trade["total_pnl"] = pnl

        if pnl_pct is not None:
            trade["pnl_pct"] = pnl_pct
            trade["total_pnl_pct"] = pnl_pct

        entry_market_cap = self.first_number(
            trade.get("entry_market_cap"),
            trade.get("market_cap_at_entry"),
        )
        current_market_cap = self.first_number(
            trade.get("current_market_cap"),
            trade.get("market_cap"),
            entry_market_cap,
        )
        exit_market_cap = self.first_number(
            trade.get("exit_market_cap"),
            trade.get("market_cap_at_exit"),
        )

        if entry_market_cap is not None:
            trade["entry_market_cap"] = entry_market_cap
            trade["market_cap_at_entry"] = entry_market_cap

        if current_market_cap is not None:
            trade["current_market_cap"] = current_market_cap
            trade["market_cap"] = current_market_cap

        if exit_market_cap is not None:
            trade["exit_market_cap"] = exit_market_cap
            trade["market_cap_at_exit"] = exit_market_cap

        if trade.get("status") == "open":
            trade["exit_advice"] = self.exit_advisor.advise(trade)

        return trade

    def normalize_state(self, state):
        if not isinstance(state, dict):
            state = {}

        state.setdefault("balance", 10000)
        state.setdefault("open_trades", [])
        state.setdefault("closed_trades", [])
        state.setdefault("failed_trades", [])
        state.setdefault("stats", {})

        for key in ["open_trades", "closed_trades", "failed_trades"]:
            state[key] = [
                self.apply_trade_aliases(trade)
                for trade in state.get(key, [])
                if isinstance(trade, dict)
            ]

        lineage_linked = self.hydrate_missing_trade_decision_lineage(state)
        if lineage_linked:
            print(
                f"🔗 Linked {lineage_linked} paper trade(s) without decision_id to synthetic ledger ids."
            )

        return state

    def find_open_trade(self, mint):
        for trade in self.state.get("open_trades", []):
            if (trade.get("mint") == mint or trade.get("token_mint") == mint) and trade.get("status") == "open":
                return trade
        return None

    def open_trade(
        self,
        mint,
        entry_price,
        size_usd,
        liquidity_usd,
        reason="",
        wallets=None,
        market_info=None,
        signal_metadata=None,
        paper_lane="main",
        exploration=False,
    ):
        signal_metadata = self.normalize_signal_metadata(signal_metadata)
        existing = self.find_open_trade(mint)
        if existing:
            print("⚠️ Trade already open:", mint)
            decision_id = signal_metadata.get("decision_id")
            if decision_id:
                try:
                    self.store.update_decision_action(decision_id, {
                        "scanner_stage": "paper_trade_precheck",
                        "final_action": "duplicate_open",
                        "reason": "trade_already_open",
                        "paper_lane": paper_lane or "main",
                    })
                except Exception as exc:
                    print("⚠️ Decision duplicate-open update failed:", exc)
            return existing

        result = self.engine.simulate_buy_fill(
            quoted_price=entry_price,
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
        )

        if not result.get("success"):
            failed_time = time.time()
            failed = {
                "mint": mint,
                "token_mint": mint,
                "side": "buy",
                "status": "failed",
                "time": failed_time,
                "time_iso": self.iso_time(failed_time),
                "reason": result.get("reason", "buy_failed"),
                "failure_reason": result.get("reason", "buy_failed"),
                "fee_usd": result.get("fee_usd", 0),
                "wallets": wallets or [],
                "entry_reason": reason,
                "paper_lane": paper_lane or "main",
                "exploration": bool(exploration),
                "size_usd": size_usd,
                "entry_value": size_usd,
                "liquidity_usd": liquidity_usd,
                "market_info": market_info or {},
                "signal_metadata": signal_metadata,
            }
            self.attach_decision_lineage(failed, signal_metadata)

            self.state.setdefault("failed_trades", []).insert(0, failed)
            self.update_stats()
            self.record_trade_snapshot(failed, "paper_entry_failed", {
                "failure_reason": failed.get("reason"),
                "decision_stage": "paper_buy_fill",
            })
            self.save_state()

            print("❌ BUY FAILED:", failed["reason"])
            return None

        now = time.time()
        market_cap = self.market_cap_from_info(market_info)
        source = market_info.get("source") if isinstance(market_info, dict) else None
        name = market_info.get("name") if isinstance(market_info, dict) else None
        symbol = market_info.get("symbol") if isinstance(market_info, dict) else None
        url = market_info.get("url") if isinstance(market_info, dict) else None

        trade = {
            "mint": mint,
            "token_mint": mint,
            "name": name,
            "symbol": symbol,
            "market_source": source,
            "url": url,
            "status": "open",
            "reason": reason,
            "entry_reason": reason,
            "paper_lane": paper_lane or "main",
            "exploration": bool(exploration),
            "wallets": wallets or [],
            "signal_metadata": signal_metadata,

            "quoted_entry_price": entry_price,
            "entry_price": result["effective_price"],
            "current_price": result["effective_price"],

            "size_usd": size_usd,
            "entry_value": size_usd,
            "current_value": result["tokens"] * result["effective_price"],
            "liquidity_usd": liquidity_usd,
            "entry_liquidity_usd": liquidity_usd,
            "current_liquidity_usd": liquidity_usd,
            "entry_market_cap": market_cap,
            "current_market_cap": market_cap,
            "market_cap_at_entry": market_cap,
            "market_cap": market_cap,
            "market_info": market_info or {},

            "initial_token_amount": result["tokens"],
            "remaining_token_amount": result["tokens"],
            "remaining_pct": 100,

            "entry_fee_usd": result.get("fee_usd", 0),
            "total_fees_usd": result.get("fee_usd", 0),

            "realized_pnl": 0,
            "unrealized_pnl": 0,
            "total_pnl": -result.get("fee_usd", 0),
            "pnl": -result.get("fee_usd", 0),
            "total_pnl_pct": 0,
            "pnl_pct": 0,

            "highest_price_seen": result["effective_price"],
            "entry_time": now,
            "entry_time_iso": self.iso_time(now),
            "close_time": None,
            "close_time_iso": None,
            "exit_time_iso": None,
            "close_price": None,
            "exit_price": None,
            "exit_value": None,
            "close_reason": None,

            "sells": [],
        }
        self.attach_decision_lineage(trade, signal_metadata)

        self.state.setdefault("open_trades", []).append(trade)
        self.record_trade_snapshot(trade, "paper_entry_opened", {
            "decision_stage": "paper_entry",
        })
        self.save_state()

        print("\n📄 PAPER TRADE OPENED")
        print("MINT:", mint)
        print("ENTRY:", trade["entry_price"])
        print("SIZE:", size_usd)
        print("WALLETS:", len(trade["wallets"]))

        return trade

    def update_price(self, mint, price, liquidity_usd=10000, market_info=None):
        trade = self.find_open_trade(mint)
        if not trade:
            return None

        price = float(price)
        if price <= 0:
            return trade

        trade["current_price"] = price
        trade["current_liquidity_usd"] = liquidity_usd
        trade["last_price_update"] = time.time()
        trade["last_price_update_iso"] = self.iso_time(trade["last_price_update"])

        if isinstance(market_info, dict):
            trade["market_info"] = market_info
            for key in ["name", "symbol", "url"]:
                if market_info.get(key):
                    trade[key] = market_info.get(key)

            current_market_cap = self.market_cap_from_info(market_info)
            if current_market_cap is not None:
                trade["current_market_cap"] = current_market_cap
                trade["market_cap"] = current_market_cap

        if price > float(trade.get("highest_price_seen", trade["entry_price"])):
            trade["highest_price_seen"] = price

        if self.update_pnl(trade) is False:
            trade["exit_advice"] = self.exit_advisor.advise(trade)
            self.record_trade_snapshot(trade, "paper_price_update", {
                "decision_stage": "paper_monitor",
                "market_info": market_info if isinstance(market_info, dict) else {},
            })
            self.save_state()
            return trade
        trade["exit_advice"] = self.exit_advisor.advise(trade)
        self.record_trade_snapshot(trade, "paper_price_update", {
            "decision_stage": "paper_monitor",
            "market_info": market_info if isinstance(market_info, dict) else {},
        })

        entry = float(trade["entry_price"])
        multiple = price / entry if entry > 0 else 0

        if multiple >= 2.5 and trade["remaining_pct"] > 65:
            self.partial_sell(trade, 35, price, liquidity_usd, "take_profit_2.5x")

        if multiple >= 6.0 and trade["remaining_pct"] > 30:
            self.partial_sell(trade, 35, price, liquidity_usd, "take_profit_6x")

        pnl_pct = ((price - entry) / entry) * 100 if entry > 0 else 0

        if pnl_pct <= -30:
            self.close_trade(trade, price, liquidity_usd, "hard_stop_loss")

        self.save_state()
        return trade

    def partial_sell(self, trade, sell_pct, price, liquidity_usd, reason):
        if trade.get("status") != "open":
            return False

        remaining_tokens = float(trade.get("remaining_token_amount", 0))
        if remaining_tokens <= 0:
            return False

        tokens_to_sell = remaining_tokens * (sell_pct / 100)

        result = self.engine.simulate_sell_fill(
            quoted_price=price,
            tokens_to_sell=tokens_to_sell,
            liquidity_usd=liquidity_usd,
        )

        if not result.get("success"):
            print("❌ PARTIAL SELL FAILED:", result.get("reason"))
            self.record_trade_snapshot(trade, "paper_exit_failed", {
                "decision_stage": "paper_exit",
                "exit_reason": reason,
                "failure_reason": result.get("reason", "sell_failed"),
                "sell_pct": sell_pct,
            })
            return False

        entry = float(trade["entry_price"])
        net_proceeds = float(result["net_proceeds"])
        fee = float(result.get("fee_usd", 0))

        cost_basis = tokens_to_sell * entry
        pnl = net_proceeds - cost_basis

        trade["remaining_token_amount"] -= tokens_to_sell
        trade["remaining_pct"] = (
            trade["remaining_token_amount"] / trade["initial_token_amount"]
        ) * 100

        trade["realized_pnl"] += pnl
        trade["total_fees_usd"] += fee

        sell_event = {
            "time": time.time(),
            "reason": reason,
            "quoted_price": price,
            "effective_price": result["effective_price"],
            "tokens_sold": tokens_to_sell,
            "sell_pct": sell_pct,
            "net_proceeds": net_proceeds,
            "fee_usd": fee,
            "pnl": pnl,
            "remaining_pct": trade["remaining_pct"],
            "time_iso": self.iso_time(),
        }
        trade["sells"].append(sell_event)

        print("\n💰 PARTIAL SELL")
        print("MINT:", trade["mint"])
        print("REASON:", reason)
        print("PNL:", round(pnl, 2))
        print("REMAINING:", round(trade["remaining_pct"], 2), "%")

        self.update_pnl(trade)
        trade["exit_advice"] = self.exit_advisor.advise(trade)
        self.record_trade_snapshot(trade, "paper_partial_exit", {
            "decision_stage": "paper_exit",
            "exit_reason": reason,
            "sell_event": sell_event,
        })
        self.save_state()
        return True

    def close_trade(self, trade, price, liquidity_usd, reason):
        if trade.get("status") != "open":
            return False

        remaining_tokens = float(trade.get("remaining_token_amount", 0))

        if remaining_tokens > 0:
            result = self.engine.simulate_sell_fill(
                quoted_price=price,
                tokens_to_sell=remaining_tokens,
                liquidity_usd=liquidity_usd,
            )

            if not result.get("success"):
                print("❌ CLOSE SELL FAILED:", result.get("reason"))
                self.record_trade_snapshot(trade, "paper_exit_failed", {
                    "decision_stage": "paper_exit",
                    "exit_reason": reason,
                    "failure_reason": result.get("reason", "sell_failed"),
                    "sell_pct": 100,
                })
                return False

            entry = float(trade["entry_price"])
            net_proceeds = float(result["net_proceeds"])
            fee = float(result.get("fee_usd", 0))

            cost_basis = remaining_tokens * entry
            pnl = net_proceeds - cost_basis

            trade["realized_pnl"] += pnl
            trade["total_fees_usd"] += fee

            trade["sells"].append({
                "time": time.time(),
                "reason": reason,
                "quoted_price": price,
                "effective_price": result["effective_price"],
                "tokens_sold": remaining_tokens,
                "sell_pct": 100,
                "net_proceeds": net_proceeds,
                "fee_usd": fee,
                "pnl": pnl,
                "remaining_pct": 0,
            })

            trade["close_price"] = result["effective_price"]
            trade["exit_price"] = result["effective_price"]
            trade["exit_value"] = sum(
                float(sell.get("net_proceeds", 0))
                for sell in trade.get("sells", [])
            )

        trade["remaining_token_amount"] = 0
        trade["remaining_pct"] = 0
        trade["status"] = "closed"
        trade["close_time"] = time.time()
        trade["close_time_iso"] = self.iso_time(trade["close_time"])
        trade["exit_time_iso"] = trade["close_time_iso"]
        trade["close_reason"] = reason
        trade["exit_reason"] = reason

        if trade.get("current_market_cap") is not None:
            trade["exit_market_cap"] = trade.get("current_market_cap")
            trade["market_cap_at_exit"] = trade.get("current_market_cap")

        self.update_pnl(trade)
        trade["exit_advice"] = self.exit_advisor.advise(trade)
        self.record_trade_snapshot(trade, "paper_exit_closed", {
            "decision_stage": "paper_exit",
            "exit_reason": reason,
        })

        self.state["open_trades"] = [
            t for t in self.state.get("open_trades", [])
            if t.get("mint") != trade.get("mint")
        ]

        self.state.setdefault("closed_trades", []).insert(0, trade)

        wallets = trade.get("wallets", [])
        if wallets:
            self.wallet_performance.record_trade_result(
                wallets=wallets,
                pnl=trade.get("total_pnl", 0),
            )

        self.update_stats()
        self.save_state()

        print("\n🔒 PAPER TRADE CLOSED")
        print("MINT:", trade["mint"])
        print("REASON:", reason)
        print("TOTAL PNL:", round(trade["total_pnl"], 2))

        return True

    def update_pnl(self, trade):
        entry = float(trade["entry_price"])
        current = float(trade["current_price"])
        remaining_tokens = float(trade.get("remaining_token_amount", 0))
        initial_tokens = float(trade.get("initial_token_amount", remaining_tokens) or 0)
        size_usd = float(trade.get("size_usd", 0))

        if initial_tokens > 0 and remaining_tokens > initial_tokens * 1.05:
            trade["status"] = "invalid"
            trade["invalid_reason"] = "paper_value_sanity_remaining_tokens_exceed_initial"
            return False

        unrealized = (current - entry) * remaining_tokens
        realized = float(trade.get("realized_pnl", 0))
        entry_fee = float(trade.get("entry_fee_usd", 0) or 0)

        total = realized + unrealized - entry_fee
        total_pct = (total / size_usd) * 100 if size_usd > 0 else 0
        current_value = current * remaining_tokens

        if size_usd > 0 and abs(total_pct) > 10_000:
            trade["status"] = "invalid"
            trade["invalid_reason"] = "paper_value_sanity_pnl_pct_out_of_range"
            return False
        if size_usd > 0 and current_value > size_usd * 250:
            trade["status"] = "invalid"
            trade["invalid_reason"] = "paper_value_sanity_current_value_out_of_range"
            return False

        trade["unrealized_pnl"] = unrealized
        trade["total_pnl"] = total
        trade["pnl"] = total
        trade["total_pnl_pct"] = total_pct
        trade["pnl_pct"] = total_pct
        trade["current_value"] = current_value
        trade["entry_value"] = size_usd
        return True

    def update_stats(self):
        closed = self.state.get("closed_trades", [])
        failed = self.state.get("failed_trades", [])

        total = len(closed)
        wins = len([t for t in closed if float(t.get("total_pnl", 0)) > 0])
        losses = len([t for t in closed if float(t.get("total_pnl", 0)) <= 0])
        realized = sum(float(t.get("total_pnl", 0)) for t in closed)
        total_fees = sum(float(t.get("total_fees_usd", 0)) for t in closed)

        win_rate = (wins / total) * 100 if total > 0 else 0

        self.state["stats"] = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "failed_trades": len(failed),
            "realized_pnl": realized,
            "total_fees": total_fees,
            "win_rate": win_rate,
        }

    def get_state(self):
        return self.state
