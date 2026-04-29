import json
import os
import time
from datetime import datetime, timezone

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
        with open(PAPER_TRADES_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
        self.sync_trades_to_store()

    def sync_trades_to_store(self):
        try:
            for key in ["open_trades", "closed_trades", "failed_trades"]:
                for trade in self.state.get(key, []):
                    if isinstance(trade, dict):
                        self.store.upsert_trade(trade)
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

    def market_cap_from_info(self, market_info):
        if not isinstance(market_info, dict):
            return None
        return self.first_number(
            market_info.get("market_cap"),
            market_info.get("marketCap"),
            market_info.get("fdv"),
        )

    def apply_trade_aliases(self, trade):
        if not isinstance(trade, dict):
            return trade

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
    ):
        existing = self.find_open_trade(mint)
        if existing:
            print("⚠️ Trade already open:", mint)
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
                "time": failed_time,
                "time_iso": self.iso_time(failed_time),
                "reason": result.get("reason", "buy_failed"),
                "fee_usd": result.get("fee_usd", 0),
                "wallets": wallets or [],
                "entry_reason": reason,
                "size_usd": size_usd,
                "entry_value": size_usd,
                "liquidity_usd": liquidity_usd,
                "market_info": market_info or {},
                "signal_metadata": signal_metadata or {},
            }

            self.state.setdefault("failed_trades", []).insert(0, failed)
            self.update_stats()
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
            "wallets": wallets or [],
            "signal_metadata": signal_metadata or {},

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

        self.state.setdefault("open_trades", []).append(trade)
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

        self.update_pnl(trade)
        trade["exit_advice"] = self.exit_advisor.advise(trade)

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

        trade["sells"].append({
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
        })

        print("\n💰 PARTIAL SELL")
        print("MINT:", trade["mint"])
        print("REASON:", reason)
        print("PNL:", round(pnl, 2))
        print("REMAINING:", round(trade["remaining_pct"], 2), "%")

        self.update_pnl(trade)
        trade["exit_advice"] = self.exit_advisor.advise(trade)
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
        size_usd = float(trade.get("size_usd", 0))

        unrealized = (current - entry) * remaining_tokens
        realized = float(trade.get("realized_pnl", 0))

        total = realized + unrealized
        total_pct = (total / size_usd) * 100 if size_usd > 0 else 0

        trade["unrealized_pnl"] = unrealized
        trade["total_pnl"] = total
        trade["pnl"] = total
        trade["total_pnl_pct"] = total_pct
        trade["pnl_pct"] = total_pct
        trade["current_value"] = current * remaining_tokens
        trade["entry_value"] = size_usd

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
