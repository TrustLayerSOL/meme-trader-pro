import asyncio
import json
import time

from core.dev_analyzer import DevAnalyzer
from core.scoring_engine import ScoringEngine
from core.anti_rug import AntiRugAnalyzer
from core.confirmation_filter import ConfirmationFilter
from core.decision_ledger import build_decision_record
from core.holder_concentration import HolderConcentrationAnalyzer
from core.wallet_quality import WalletQualityAnalyzer
from core.wallet_performance import WalletPerformanceTracker
from core.position_sizer import PositionSizer
from core.edge_analyzer import EdgeAnalyzer
from core.paper_exploration import evaluate_paper_exploration
from core.runtime_status import increment_component, update_component
from core.settings_manager import load_settings
from core.storage import EventStore
from core.strategy_guard import StrategyGuard
from core.token_age import TokenAgeTracker
from core.token_inspector import TokenInspector
from core.token_launch_age import TokenLaunchAgeTracker
from dashboard.live_state import add_event, add_alert, update_token
from social.social_signal import SocialSignalEngine

try:
    from paper_trader import PaperTrader
except Exception:
    PaperTrader = None


BASE_TOKENS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
}

WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
USD_QUOTE_MINTS = {USDC_MINT, USDT_MINT}
TRADE_QUOTE_MINTS = {WRAPPED_SOL_MINT, USDC_MINT, USDT_MINT}

KNOWN_DEX_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter_v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "jupiter_v4",
    "JUP2jxv4U8UeQ27vyWq6PZ3zKdwUTNnyN2tJ9pUcRFT": "jupiter_v2",
    "JUP3c2Uh1gYWNU3c5DqE3vdJmpsVbQ5nCjSV5zCWFFm": "jupiter_v3",
    "JUP5cHjnnCx2DppVsufsLrXs8EBZeEZzGtEK9Gdz6ow": "jupiter_v5",
    "6EF8rrecthR5DkPXkqW6fBsyPVAaeWwH4wjFnXRZHYD": "pump_fun",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pump_swap",
    "675kPX9MHTjS2zt1qfr1NYa9U1mHsyYF8ykLuXKCW3d": "raydium_amm",
    "CPMMoo8L3F4NbTegBCKVN8guJJy5cc5sXUQK4WgB3hK": "raydium_cpmm",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUQWqKn8ZKTaHj7YpY": "raydium_clmm",
    "whirLbMiicVdio4qvUfM5KAg6CtC8L5dbsPBk2hh7y": "orca_whirlpool",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "meteora_dlmm",
    "srmqPvymJeFKQ4zJr3AEbGMBHXPP6YQZpiFinF1BYBY": "openbook_v3",
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "phoenix",
}

KNOWN_MAJOR_SYMBOLS = {
    "btc",
    "eth",
    "sol",
    "usdc",
    "usdt",
    "usds",
    "dai",
    "wbtc",
    "weth",
    "wsol",
}

MAX_MEME_MARKET_CAP_USD = 10_000_000
MAX_MEME_LIQUIDITY_USD = 2_500_000


class Scanner:
    def __init__(self, tracked_wallets, rpc, paper_watch_wallets=None):
        self.tracked_wallets = set(tracked_wallets)
        self.paper_watch_wallets = set(paper_watch_wallets or [])
        self.observed_wallets = self.tracked_wallets | self.paper_watch_wallets
        self.rpc = rpc

        self.token_buys = {}
        self.settings = load_settings()
        self.cluster_window = int(self.settings.get("cluster_window", 90))
        self.cluster_threshold = int(self.settings.get("cluster_threshold", 3))

        self.dev_analyzer = DevAnalyzer()
        self.scoring_engine = ScoringEngine()
        self.anti_rug = AntiRugAnalyzer()
        self.wallet_quality = WalletQualityAnalyzer()
        self.wallet_performance = WalletPerformanceTracker()
        self.position_sizer = PositionSizer()
        self.edge_analyzer = EdgeAnalyzer()
        self.confirmation_filter = ConfirmationFilter(self.settings)
        self.strategy_guard = StrategyGuard()
        self.token_age = TokenAgeTracker()
        self.token_inspector = TokenInspector()
        self.token_launch_age = TokenLaunchAgeTracker(rpc)
        self.holder_analyzer = HolderConcentrationAnalyzer()
        self.social_signal = SocialSignalEngine()
        self.store = EventStore()

        self.paper_trader = PaperTrader() if PaperTrader else None

        self.seen_signatures = set()
        self.seen_signals = {}
        self.signal_locks = {}
        self.pending_signal_reruns = set()
        self.quote_price_cache = {}
        self.swap_quote_request_times = []

    def is_observed_wallet(self, wallet):
        return wallet in self.observed_wallets

    def add_paper_watch_wallets(self, wallets):
        added = []
        for wallet in wallets or []:
            wallet = str(wallet or "").strip()
            if not wallet or wallet in self.observed_wallets:
                continue
            self.paper_watch_wallets.add(wallet)
            self.observed_wallets.add(wallet)
            added.append(wallet)
        if added:
            update_component(
                "scanner",
                status="wallet_reload",
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
                added_paper_watch_wallets=len(added),
            )
        return added

    def wallet_source(self, wallet):
        if wallet in self.tracked_wallets:
            return "tracked"
        if wallet in self.paper_watch_wallets:
            return "paper_watch"
        return "unobserved"

    def wallet_can_drive_live(self, wallet):
        return wallet in self.tracked_wallets

    def first_number(self, *values):
        for value in values:
            try:
                if value not in [None, ""]:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def jupiter_prescore_threshold(self):
        value = self.first_number(self.settings.get("jupiter_prescore_threshold"))
        return value if value is not None else 40

    def scanner_holder_check_enabled(self):
        value = self.settings.get("scanner_holder_check_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def scanner_holder_check_timeout(self):
        value = self.first_number(self.settings.get("scanner_holder_check_timeout_seconds"))
        return value if value is not None and value > 0 else 3

    def skipped_holder_cluster_risk(self, reason):
        return {
            "holder_concentration_risk": "UNKNOWN",
            "holder_concentration_reasons": [reason],
            "holder_concentration_metrics": {},
            "holder_concentration": None,
        }

    def holder_check_candidate_worthy(self, decision, edge_result):
        score = self.first_number((decision or {}).get("score")) or 0
        return (
            score >= self.jupiter_prescore_threshold()
            or bool((edge_result or {}).get("quote_worthy"))
            or bool((edge_result or {}).get("paper_trade_worthy"))
        )

    async def evaluate_holder_cluster_risk(self, mint):
        if not self.scanner_holder_check_enabled():
            return self.skipped_holder_cluster_risk("Scanner holder check disabled")
        if not self.rpc or not hasattr(self.rpc, "rpc_call"):
            return self.skipped_holder_cluster_risk("Scanner holder check unavailable")

        try:
            response = await asyncio.wait_for(
                self.rpc.rpc_call(
                    "getTokenLargestAccounts",
                    [
                        mint,
                        {
                            "commitment": "confirmed",
                        },
                    ],
                ),
                timeout=self.scanner_holder_check_timeout(),
            )
        except asyncio.TimeoutError:
            return self.skipped_holder_cluster_risk("Scanner holder check timed out")
        except Exception as exc:
            return self.skipped_holder_cluster_risk(f"Scanner holder check error: {str(exc)[:160]}")

        rows = ((response or {}).get("result") or {}).get("value") or []
        holder_result = self.holder_analyzer.analyze(rows)
        return {
            "holder_concentration": holder_result,
            "holder_concentration_risk": holder_result.get("risk_label"),
            "holder_concentration_reasons": holder_result.get("warnings", []),
            "holder_concentration_metrics": holder_result.get("metrics", {}),
        }

    def wallet_cluster_risk_context(self, signal_type, wallets, wallet_count, repeated_buys):
        return {
            "risk_label": "NOT_CHECKED",
            "reason": "no_linked_wallet_graph_source",
            "observed_wallet_cluster": {
                "signal_type": signal_type,
                "wallet_count": wallet_count,
                "cluster_threshold": self.cluster_threshold,
                "cluster_window_seconds": self.cluster_window,
                "repeated_buys": repeated_buys,
                "wallets": wallets,
            },
        }

    def apply_holder_cluster_to_rug_result(self, rug_result, holder_context, cluster_context):
        rug_result = rug_result if isinstance(rug_result, dict) else {}
        holder_context = holder_context if isinstance(holder_context, dict) else {}

        rug_result.update(holder_context)
        rug_result["linked_wallet_risk"] = cluster_context

        holder_risk = holder_context.get("holder_concentration_risk")
        holder_reasons = holder_context.get("holder_concentration_reasons") or []
        if holder_risk in {"DANGER", "WARNING"}:
            prefix = "Holder concentration"
            for reason in holder_reasons:
                warning = f"{prefix}: {reason}"
                if warning not in rug_result.setdefault("warnings", []):
                    rug_result["warnings"].append(warning)

        if holder_risk == "DANGER":
            rug_result["hard_block"] = True
            rug_result["hard_block_reason"] = (
                "Holder concentration: " + "; ".join(holder_reasons)
                if holder_reasons
                else "Holder concentration danger"
            )
            rug_result["risk_score"] = max(self.first_number(rug_result.get("risk_score")) or 0, 22)
            rug_result["risk_label"] = "HIGH_RISK"
            rug_result.setdefault("penalties", []).append({
                "label": "Dangerous holder concentration",
                "amount": 12,
            })
        elif holder_risk == "WARNING":
            rug_result["risk_score"] = max(self.first_number(rug_result.get("risk_score")) or 0, 10)
            if rug_result.get("risk_label") == "LOW_RISK":
                rug_result["risk_label"] = "MEDIUM_RISK"
            rug_result.setdefault("penalties", []).append({
                "label": "Holder concentration warning",
                "amount": 6,
            })

        return rug_result

    def market_cap_from_info(self, market_info):
        if not isinstance(market_info, dict):
            return None
        return self.first_number(
            market_info.get("market_cap"),
            market_info.get("marketCap"),
            market_info.get("fdv"),
        )

    def transaction_signature(self, result):
        transaction = result.get("transaction") if isinstance(result, dict) else {}
        signatures = transaction.get("signatures") if isinstance(transaction, dict) else []
        if isinstance(signatures, list) and signatures:
            return signatures[0]
        return None

    def transaction_account_keys(self, result):
        transaction = result.get("transaction") if isinstance(result, dict) else {}
        message = transaction.get("message") if isinstance(transaction, dict) else {}
        keys = message.get("accountKeys") if isinstance(message, dict) else []
        normalized = []
        for key in keys if isinstance(keys, list) else []:
            if isinstance(key, str):
                normalized.append(key)
            elif isinstance(key, dict):
                normalized.append(key.get("pubkey") or key.get("account") or "")
            else:
                normalized.append(str(key or ""))
        return normalized

    def collect_instruction_program_ids(self, result):
        transaction = result.get("transaction") if isinstance(result, dict) else {}
        message = transaction.get("message") if isinstance(transaction, dict) else {}
        meta = result.get("meta") if isinstance(result, dict) else {}
        programs = []

        def collect(rows):
            for instruction in rows if isinstance(rows, list) else []:
                if not isinstance(instruction, dict):
                    continue
                program_id = instruction.get("programId")
                if program_id:
                    programs.append(str(program_id))
                parsed = instruction.get("parsed")
                if isinstance(parsed, dict):
                    nested = parsed.get("info")
                    if isinstance(nested, dict) and nested.get("programId"):
                        programs.append(str(nested.get("programId")))

        collect(message.get("instructions") if isinstance(message, dict) else [])
        for group in meta.get("innerInstructions") if isinstance(meta, dict) and isinstance(meta.get("innerInstructions"), list) else []:
            if isinstance(group, dict):
                collect(group.get("instructions"))

        return programs

    def dex_route_metadata(self, result):
        seen_programs = []
        seen_labels = []
        for program_id in self.transaction_account_keys(result) + self.collect_instruction_program_ids(result):
            label = KNOWN_DEX_PROGRAMS.get(program_id)
            if not label:
                continue
            if program_id not in seen_programs:
                seen_programs.append(program_id)
            if label not in seen_labels:
                seen_labels.append(label)
        return {
            "detected": bool(seen_labels),
            "programs": seen_labels,
            "program_ids": seen_programs,
        }

    def quote_decision_fields(self, prefix, quote, slippage_bps, max_price_impact_pct):
        quote = quote if isinstance(quote, dict) else {}
        return {
            f"{prefix}_quote_input_mint": quote.get("input_mint"),
            f"{prefix}_quote_output_mint": quote.get("output_mint"),
            f"{prefix}_quote_in_amount_raw": quote.get("in_amount_raw"),
            f"{prefix}_quote_out_amount": quote.get("out_amount"),
            f"{prefix}_quote_route_count": quote.get("route_count"),
            f"{prefix}_quote_slippage_bps": slippage_bps,
            f"{prefix}_quote_max_price_impact_pct": max_price_impact_pct,
            f"{prefix}_quote_route_plan": quote.get("route_plan", []),
        }

    def native_delta_for_wallet(self, result, wallet):
        meta = result.get("meta") if isinstance(result, dict) else {}
        pre_balances = meta.get("preBalances") if isinstance(meta, dict) else []
        post_balances = meta.get("postBalances") if isinstance(meta, dict) else []
        keys = self.transaction_account_keys(result)
        try:
            index = keys.index(wallet)
            pre = float(pre_balances[index])
            post = float(post_balances[index])
        except (ValueError, IndexError, TypeError):
            return None
        return (post - pre) / 1_000_000_000

    async def market_info_for_tick(self, mint):
        checker = getattr(self.rpc, "market_checker", None)
        if not checker or not hasattr(checker, "get_token_info"):
            return None
        try:
            return await checker.get_token_info(mint)
        except Exception as exc:
            update_component("scanner", status="swap_tick_market_error", last_error=str(exc))
            return None

    def estimated_market_cap_for_tick(self, mint, price, fallback):
        fallback = self.first_number(fallback)
        if not str(mint or "").endswith("pump"):
            return fallback
        price = self.first_number(price)
        if not price or price <= 0:
            return fallback
        return round(price * 1_000_000_000, 2)

    async def quote_token_price_usd(self, mint):
        if mint in USD_QUOTE_MINTS:
            return 1.0
        if mint != WRAPPED_SOL_MINT:
            return None

        now = time.time()
        cached = self.quote_price_cache.get(mint)
        if cached and now - cached.get("time", 0) <= 5:
            return cached.get("price")

        info = await self.market_info_for_tick(mint)
        price = self.first_number((info or {}).get("price"))
        if price and price > 0:
            self.quote_price_cache[mint] = {"time": now, "price": price}
            return price
        return None

    async def execution_price_from_event(self, event, token_amount):
        if not event.get("dex_route_detected"):
            return None

        quote_mint = event.get("quote_mint")
        quote_delta = self.first_number(event.get("quote_delta"))
        if quote_mint and quote_delta and token_amount > 0:
            quote_price = await self.quote_token_price_usd(quote_mint)
            if quote_price and quote_price > 0:
                return {
                    "price": abs(quote_delta) * quote_price / token_amount,
                    "quote_mint": quote_mint,
                    "quote_amount": abs(quote_delta),
                    "quote_price_usd": quote_price,
                    "source": "wallet_event_dex_route_delta",
                }

        native_delta = self.first_number(event.get("native_delta"))
        if native_delta and token_amount > 0:
            sol_price = await self.quote_token_price_usd(WRAPPED_SOL_MINT)
            if sol_price and sol_price > 0:
                return {
                    "price": abs(native_delta) * sol_price / token_amount,
                    "quote_mint": WRAPPED_SOL_MINT,
                    "quote_amount": abs(native_delta),
                    "quote_price_usd": sol_price,
                    "source": "wallet_event_dex_route_native_delta",
                }
        return None

    async def record_swap_tick_from_event(self, event, event_type):
        signature = event.get("signature")
        native_delta = self.first_number(event.get("native_delta"))
        token_amount = abs(self.first_number(event.get("delta")) or 0)
        if not signature or native_delta is None or token_amount <= 0:
            return False

        market_info = await self.market_info_for_tick(event.get("mint"))
        execution = await self.execution_price_from_event(event, token_amount)
        price = self.first_number((execution or {}).get("price"))
        if not price:
            price = self.first_number((market_info or {}).get("price"))
        if not price or price <= 0:
            return False

        market_cap = self.estimated_market_cap_for_tick(
            event.get("mint"),
            price,
            self.market_cap_from_info(market_info),
        )
        quote_mint = (execution or {}).get("quote_mint") or event.get("quote_mint")
        quote_amount = self.first_number((execution or {}).get("quote_amount"))
        tick = {
            "time": event.get("block_time") or event.get("timestamp") or time.time(),
            "mint": event.get("mint"),
            "signature": signature,
            "wallet": event.get("wallet"),
            "side": event_type,
            "price": price,
            "market_cap": market_cap,
            "liquidity": self.first_number((market_info or {}).get("liquidity")),
            "token_amount": token_amount,
            "sol_amount": quote_amount if quote_mint == WRAPPED_SOL_MINT else abs(native_delta),
            "quote_amount": quote_amount,
            "quote_mint": quote_mint,
            "quote_price_usd": self.first_number((execution or {}).get("quote_price_usd")),
            "source": (execution or {}).get("source") or "wallet_event_market_enriched",
            "dex_route_detected": bool(event.get("dex_route_detected")),
            "dex_route_programs": event.get("dex_route_programs") or [],
            "dex_route_program_ids": event.get("dex_route_program_ids") or [],
            "market_info": market_info if isinstance(market_info, dict) else {},
        }
        try:
            inserted = self.store.insert_swap_tick(tick)
            if inserted:
                increment_component(
                    "scanner",
                    "swap_ticks_written",
                    last_swap_tick_mint=event.get("mint"),
                    last_swap_tick_at=tick["time"],
                    wallet_feed_fresh_seconds=300,
                )
            return bool(inserted)
        except Exception as exc:
            update_component("scanner", status="swap_tick_write_error", last_error=str(exc))
            return False

    def evaluate_candidate_market_sanity(self, mint, market_info):
        market_info = market_info if isinstance(market_info, dict) else {}
        reasons = []
        symbol = str(market_info.get("symbol") or "").strip().lower()
        name = str(market_info.get("name") or "").strip().lower()
        market_cap = self.market_cap_from_info(market_info)
        liquidity = self.first_number(
            market_info.get("liquidity"),
            market_info.get("liquidity_usd"),
        )

        if mint in BASE_TOKENS:
            reasons.append("known_major_or_stable_mint")
        if symbol in KNOWN_MAJOR_SYMBOLS or name in KNOWN_MAJOR_SYMBOLS:
            reasons.append("known_major_or_stable_symbol")
        if market_cap is not None and market_cap > MAX_MEME_MARKET_CAP_USD:
            reasons.append("market_cap_above_meme_window")
        if liquidity is not None and liquidity > MAX_MEME_LIQUIDITY_USD:
            reasons.append("liquidity_above_meme_window")

        return {
            "allow": not reasons,
            "reasons": reasons,
            "market_cap": market_cap,
            "liquidity": liquidity,
            "symbol": symbol,
            "name": name,
        }

    def wallet_quality_rapid_flip_count(self, wallet_quality):
        total = 0
        for row in (wallet_quality or {}).get("wallet_scores", []) or []:
            stats = row.get("stats") if isinstance(row, dict) else {}
            total += int(self.first_number((stats or {}).get("rapid_flip_count")) or 0)
        return total

    def wallet_main_quality_gate(self, signal_type, decision, wallet_count, wallet_quality, rug_result, market_info):
        if not self.settings.get("wallet_main_quality_gate_enabled", True):
            return {"allow": True, "reasons": []}

        decision = decision if isinstance(decision, dict) else {}
        if not decision.get("should_trade", False):
            return {"allow": True, "reasons": []}

        wallet_count = int(wallet_count or 0)
        if wallet_count > 2:
            return {"allow": True, "reasons": []}

        signal_type = str(signal_type or "")
        if signal_type not in {"early_signal", "weighted_early_signal"}:
            return {"allow": True, "reasons": []}

        wallet_quality = wallet_quality if isinstance(wallet_quality, dict) else {}
        rug_result = rug_result if isinstance(rug_result, dict) else {}
        market_info = market_info if isinstance(market_info, dict) else {}

        score = self.first_number(decision.get("score")) or 0
        avg_quality = self.first_number(wallet_quality.get("avg_score")) or 0
        max_quality = self.first_number(wallet_quality.get("max_score")) or 0
        rapid_flips = self.wallet_quality_rapid_flip_count(wallet_quality)
        risk_label = str(rug_result.get("risk_label") or "UNKNOWN").upper()
        liquidity = self.first_number(market_info.get("liquidity"), market_info.get("liquidity_usd")) or 0
        market_cap = self.market_cap_from_info(market_info) or 0

        min_liquidity = self.first_number(self.settings.get("wallet_main_min_liquidity_usd")) or 100_000
        min_market_cap = self.first_number(self.settings.get("wallet_main_min_market_cap_usd")) or 250_000
        solo_min_score = self.first_number(self.settings.get("wallet_main_solo_min_score")) or 90
        solo_min_quality = self.first_number(self.settings.get("wallet_main_solo_min_wallet_quality")) or 90
        two_min_avg_quality = self.first_number(self.settings.get("wallet_main_two_wallet_min_avg_quality")) or 80
        two_min_max_quality = self.first_number(self.settings.get("wallet_main_two_wallet_min_max_quality")) or 85
        max_rapid_flips = self.first_number(self.settings.get("wallet_main_max_rapid_flips")) or 0

        reasons = []
        if risk_label != "LOW_RISK":
            reasons.append("two_wallet_requires_low_risk" if wallet_count == 2 else "solo_requires_low_risk")
        if liquidity < min_liquidity:
            reasons.append("weighted_signal_liquidity_below_main_gate")
        if market_cap and market_cap < min_market_cap:
            reasons.append("weighted_signal_market_cap_below_main_gate")

        if wallet_count <= 1:
            if score < solo_min_score:
                reasons.append("solo_requires_elite_score")
            if max_quality < solo_min_quality:
                reasons.append("solo_requires_elite_wallet_quality")
        elif wallet_count == 2:
            if avg_quality < two_min_avg_quality:
                reasons.append("two_wallet_requires_strong_avg_quality")
            if max_quality < two_min_max_quality:
                reasons.append("two_wallet_requires_strong_top_wallet")
            if rapid_flips > max_rapid_flips:
                reasons.append("two_wallet_rapid_flip_history")

        return {
            "allow": not reasons,
            "reasons": reasons,
            "metrics": {
                "score": score,
                "wallet_count": wallet_count,
                "avg_wallet_quality": avg_quality,
                "max_wallet_quality": max_quality,
                "rapid_flip_count": rapid_flips,
                "risk_label": risk_label,
                "liquidity_usd": liquidity,
                "market_cap": market_cap,
            },
        }

    def record_token_snapshot(self, snapshot):
        try:
            self.store.insert_token_snapshot(snapshot)
        except Exception as exc:
            print("⚠️ Token snapshot write failed:", exc)
            update_component("scanner", status="snapshot_write_error", last_error=str(exc))

    def update_decision_runtime_skip(self, decision_id, reason):
        if not decision_id:
            return
        try:
            self.store.update_decision_action(decision_id, {
                "scanner_stage": "paper_trade_precheck",
                "final_action": "runtime_skip",
                "reason": reason,
            })
        except Exception as exc:
            print("⚠️ Decision runtime-skip update failed:", exc)

    async def handle_event(self, message):
        try:
            data = json.loads(message)
            increment_component("scanner", "messages_seen")

            if "params" not in data:
                return

            value = data["params"]["result"]["value"]
            signature = value.get("signature")
            err = value.get("err")

            if err or not signature:
                return

            if signature in self.seen_signatures:
                increment_component("scanner", "duplicate_signatures")
                return

            self.seen_signatures.add(signature)
            increment_component("scanner", "unique_signatures")

            tx = await self.rpc.get_transaction(signature)

            if not tx or not tx.get("result"):
                increment_component("scanner", "missing_transactions")
                return

            result = tx["result"]

            wallet_hits = self.extract_wallet_hits(result)
            if not wallet_hits:
                return

            increment_component(
                "scanner",
                "wallet_hit_transactions",
                last_signature=signature,
                wallet_hits=len(wallet_hits),
            )

            changes = self.extract_token_changes(result, wallet_hits)
            if changes:
                increment_component(
                    "scanner",
                    "parsed_token_change_batches",
                    token_changes=len(changes),
                )

            for event in changes:
                await self.process_event(event)

        except Exception as e:
            print("❌ Scanner error:", e)
            update_component("scanner", status="error", last_error=str(e))

    async def process_event(self, event):
        try:
            wallet = event["wallet"]
            mint = event["mint"]
            delta = event["delta"]

            if not self.is_observed_wallet(wallet):
                return

            if mint in BASE_TOKENS:
                return

            now = time.time()
            event_type = "buy" if delta > 0 else "sell"
            source = self.wallet_source(wallet)
            increment_component(
                "scanner",
                "wallet_events",
                last_event_type=event_type,
                last_event_mint=mint,
                last_event_wallet=wallet,
                last_event_wallet_source=source,
            )

            self.token_age.mark_seen(mint)
            self.wallet_quality.record_event(wallet, event_type, mint)

            quality = self.wallet_quality.score_wallet(wallet)
            performance = self.wallet_performance.get_wallet_score(wallet)

            combined_wallet_score = self.combined_wallet_score(
                quality_score=quality.get("score", 50),
                performance_score=performance.get("score", 50),
            )

            if combined_wallet_score <= 15:
                print("\n🚫 Ignoring very low-quality wallet")
                print("WALLET:", wallet)
                print("QUALITY:", quality.get("score"))
                print("PERFORMANCE:", performance.get("score"))
                return

            print("\n==============================")
            print("DEBUG EVENT:", event)

            add_event({
                "type": event_type,
                "wallet": wallet,
                "mint": mint,
                "amount": abs(delta),
                "timestamp": now,
                "signature": event.get("signature"),
                "block_time": event.get("block_time"),
                "native_delta": event.get("native_delta"),
                "wallet_quality_score": quality.get("score"),
                "wallet_performance_score": performance.get("score"),
                "combined_wallet_score": combined_wallet_score,
                "wallet_source": source,
                "live_trade_driver": self.wallet_can_drive_live(wallet),
            })

            await self.record_swap_tick_from_event(event, event_type)

            print(f"{'🟢 BUY' if delta > 0 else '🔴 SELL'}")
            print("WALLET:", wallet)
            print("MINT:", mint)
            print("DELTA:", delta)
            print("👛 WALLET COMBINED SCORE:", combined_wallet_score)

            if delta <= 0:
                return

            increment_component(
                "scanner",
                "buy_events",
                last_buy_mint=mint,
                last_buy_wallet=wallet,
            )

            if mint not in self.token_buys:
                self.token_buys[mint] = []

            self.token_buys[mint].append({
                "wallet": wallet,
                "time": now,
                "quality_score": quality.get("score", 50),
                "performance_score": performance.get("score", 50),
                "combined_score": combined_wallet_score,
                "wallet_source": source,
                "live_trade_driver": self.wallet_can_drive_live(wallet),
            })

            self.token_buys[mint] = [
                item
                for item in self.token_buys[mint]
                if now - item["time"] <= self.cluster_window
            ]

            wallets = list(set(item["wallet"] for item in self.token_buys[mint]))
            unique_wallets = len(wallets)
            weighted_wallet_score = self.weighted_wallet_signal_score(mint)

            print(f"👀 Smart wallets: {unique_wallets}/{self.cluster_threshold}")
            print("⚖️ WEIGHTED WALLET SIGNAL:", weighted_wallet_score)

            if self.should_evaluate_fast(
                wallet_count=unique_wallets,
                weighted_wallet_score=weighted_wallet_score,
                combined_wallet_score=combined_wallet_score,
            ):
                increment_component(
                    "scanner",
                    "evaluation_triggers",
                    last_evaluation_mint=mint,
                    last_weighted_wallet_score=weighted_wallet_score,
                    last_wallet_count=unique_wallets,
                )
                await self.evaluate_signal(mint)

        except Exception as e:
            print("❌ Process event error:", e)
            update_component("scanner", status="process_event_error", last_error=str(e))

    def combined_wallet_score(self, quality_score, performance_score):
        quality_score = float(quality_score or 50)
        performance_score = float(performance_score or 50)

        return round((quality_score * 0.55) + (performance_score * 0.45), 2)

    def weighted_wallet_signal_score(self, mint):
        items = self.token_buys.get(mint, [])

        if not items:
            return 0

        unique = {}

        for item in items:
            wallet = item["wallet"]
            combined = float(item.get("combined_score", 50))

            if wallet not in unique:
                unique[wallet] = combined
            else:
                unique[wallet] = max(unique[wallet], combined)

        total = 0

        for score in unique.values():
            if score >= 90:
                total += 3.0
            elif score >= 80:
                total += 2.4
            elif score >= 70:
                total += 1.8
            elif score >= 60:
                total += 1.2
            elif score >= 45:
                total += 0.8
            else:
                total += 0.3

        return round(total, 2)

    def should_evaluate_fast(self, wallet_count, weighted_wallet_score, combined_wallet_score):
        if combined_wallet_score >= 78:
            return True

        if weighted_wallet_score >= self.first_number(self.settings.get("weighted_wallet_trigger")):
            return True

        if wallet_count >= self.cluster_threshold:
            return True

        activity_enabled = self.settings.get("paper_activity_evaluation_enabled", True)
        if isinstance(activity_enabled, str):
            activity_enabled = activity_enabled.strip().lower() not in {"0", "false", "no", "off"}

        activity_weighted_trigger = self.first_number(
            self.settings.get("paper_activity_evaluation_weighted_trigger")
        )
        if activity_weighted_trigger is None:
            activity_weighted_trigger = 0.8

        activity_min_combined = self.first_number(
            self.settings.get("paper_activity_evaluation_min_combined_wallet_score")
        )
        if activity_min_combined is None:
            activity_min_combined = 45

        if (
            activity_enabled
            and weighted_wallet_score >= activity_weighted_trigger
            and combined_wallet_score >= activity_min_combined
        ):
            return True

        return False

    def swap_quote_budget_enabled(self):
        value = self.settings.get("swap_quote_budget_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def swap_quote_budget_window_seconds(self):
        value = self.first_number(self.settings.get("swap_quote_budget_window_seconds"))
        return value if value is not None and value > 0 else 60

    def swap_quote_budget_max_requests(self):
        value = self.first_number(self.settings.get("swap_quote_max_requests_per_minute"))
        return int(value) if value is not None and value > 0 else 18

    def prune_swap_quote_budget(self, now=None):
        now = time.time() if now is None else now
        window = self.swap_quote_budget_window_seconds()
        self.swap_quote_request_times = [
            item for item in self.swap_quote_request_times if now - item < window
        ]

    def consume_swap_quote_budget(self, now=None):
        if not self.swap_quote_budget_enabled():
            return True

        now = time.time() if now is None else now
        self.prune_swap_quote_budget(now)

        if len(self.swap_quote_request_times) >= self.swap_quote_budget_max_requests():
            return False

        self.swap_quote_request_times.append(now)
        return True

    def should_request_swap_quote(self, decision, edge_result, rug_result, market_sanity):
        decision = decision if isinstance(decision, dict) else {}
        edge_result = edge_result if isinstance(edge_result, dict) else {}
        rug_result = rug_result if isinstance(rug_result, dict) else {}
        market_sanity = market_sanity if isinstance(market_sanity, dict) else {}

        if not self.swap_quote_budget_enabled():
            return True, "swap_quote_budget_disabled"

        if rug_result.get("hard_block"):
            return False, "hard_risk_block"

        if not market_sanity.get("allow", True):
            return False, "market_sanity_block"

        if decision.get("wallet_main_quality_block"):
            return False, "wallet_main_quality_block"

        if (decision.get("strategy_guard") or {}).get("action") == "BLOCK":
            return False, "strategy_guard_block"

        score = self.first_number(decision.get("score")) or 0
        edge_score = self.first_number(edge_result.get("edge_score")) or 0
        score_threshold = self.first_number(self.settings.get("swap_quote_score_threshold"))
        edge_threshold = self.first_number(self.settings.get("swap_quote_min_edge_score"))
        score_threshold = score_threshold if score_threshold is not None else 68
        edge_threshold = edge_threshold if edge_threshold is not None else 65

        if score >= score_threshold or edge_score >= edge_threshold:
            return True, "swap_quote_quality_gate_passed"

        return False, "below_swap_quote_quality_gate"

    def learning_mode_penalties(self, penalties):
        cleaned = []

        ignore_labels = {
            "Bad dev",
            "Weak cluster",
            "No conviction buys",
        }

        for p in penalties or []:
            label = str(p.get("label", ""))

            if label in ignore_labels:
                continue

            cleaned.append(p)

        return cleaned

    def apply_social_bonus(self, decision, social_match):
        if not social_match or not social_match.get("matched"):
            return decision

        bonus = float(social_match.get("score_bonus", 0) or 0)
        account = social_match.get("matched_account", "unknown")
        keywords = social_match.get("matched_keywords", [])

        if bonus <= 0:
            return decision

        decision["score"] = min(100, round(decision["score"] + bonus, 2))
        decision["reasons"].append(
            f"Social catalyst bonus: +{bonus} from @{account} keywords={keywords}"
        )
        decision["should_trade"] = decision["score"] >= decision["threshold"]

        return decision

    async def evaluate_signal(self, mint):
        lock = self.signal_locks.setdefault(mint, asyncio.Lock())
        if lock.locked():
            self.pending_signal_reruns.add(mint)
            return

        async with lock:
            while True:
                self.pending_signal_reruns.discard(mint)
                await self._evaluate_signal_once(mint)
                if mint not in self.pending_signal_reruns:
                    break
                self.seen_signals.pop(mint, None)

    async def _evaluate_signal_once(self, mint):
        now = time.time()
        increment_component("scanner", "signals_evaluated", current_mint=mint)

        last_signal = self.seen_signals.get(mint, 0)
        if now - last_signal < 30:
            return

        self.seen_signals[mint] = now

        buy_items = self.token_buys.get(mint, [])

        wallets = list(set(item["wallet"] for item in buy_items))
        wallet_count = len(wallets)
        weighted_wallet_score = self.weighted_wallet_signal_score(mint)

        token_age_seconds = self.token_age.get_age_seconds(mint)
        launch_info = await self.token_launch_age.get_launch_info(mint)
        true_launch_age_seconds = launch_info.get("launch_age_seconds")

        if weighted_wallet_score >= 1.8 and wallet_count < self.cluster_threshold:
            signal_type = "weighted_early_signal"
        elif wallet_count >= self.cluster_threshold:
            signal_type = "cluster"
        else:
            signal_type = "early_signal"

        print(f"\n🧠 EVALUATING {signal_type.upper()}:", mint)

        dev_wallet = await self.find_dev_wallet(mint)
        dev_score = self.dev_analyzer.score_dev(dev_wallet)
        token_inspection = await self.token_inspector.inspect_with_rpc(self.rpc, mint)

        repeated_buys = len(buy_items) - wallet_count

        wallet_quality = self.wallet_quality.score_wallets(wallets)
        wallet_performance = self.wallet_performance.score_wallets(wallets)

        liquidity_score = 0
        volume_score = 0
        market_info = None

        if hasattr(self.rpc, "market_checker") and self.rpc.market_checker:
            market_info = await self.rpc.market_checker.get_token_info(mint)

            if market_info:
                liquidity_score = self.rpc.market_checker.liquidity_score(
                    market_info.get("liquidity", 0)
                )
                volume_score = self.rpc.market_checker.volume_score(
                    market_info.get("volume", 0)
                )

        social_match = self.social_signal.match_token(
            mint=mint,
            market_info=market_info,
        )
        market_sanity = self.evaluate_candidate_market_sanity(mint, market_info)

        rug_result = self.anti_rug.analyze(
            mint=mint,
            market_info=market_info,
            dev_score=dev_score,
            token_inspection=token_inspection,
            wallet_count=wallet_count,
            repeated_buys=repeated_buys,
        )

        filtered_penalties = self.learning_mode_penalties(
            rug_result.get("penalties", [])
        )

        decision = self.scoring_engine.score_token(
            mint=mint,
            wallets=wallets,
            dev_score_data=dev_score,
            liquidity_score=liquidity_score,
            volume_score=volume_score,
            repeated_buys=repeated_buys,
            token_age_seconds=token_age_seconds,
            true_launch_age_seconds=true_launch_age_seconds,
            risk_penalties=filtered_penalties,
            wallet_quality=wallet_quality,
            wallet_performance=wallet_performance,
        )

        if weighted_wallet_score >= 1.8:
            decision["score"] = min(100, decision["score"] + 8)
            decision["reasons"].append(f"Weighted wallet signal bonus: +8 ({weighted_wallet_score})")

        if weighted_wallet_score >= 3.0:
            decision["score"] = min(100, decision["score"] + 8)
            decision["reasons"].append(f"Strong weighted wallet signal bonus: +8 ({weighted_wallet_score})")

        decision["should_trade"] = decision["score"] >= decision["threshold"]

        if not market_sanity["allow"]:
            decision["should_trade"] = False
            for reason in market_sanity["reasons"]:
                decision["reasons"].append(f"MARKET SANITY BLOCK: {reason}")

        decision = self.apply_social_bonus(
            decision=decision,
            social_match=social_match,
        )

        edge_result = self.edge_analyzer.analyze(
            wallet_count=wallet_count,
            weighted_wallet_score=weighted_wallet_score,
            repeated_buys=repeated_buys,
            wallet_quality=wallet_quality,
            wallet_performance=wallet_performance,
            liquidity_usd=(market_info or {}).get("liquidity", 0),
            volume_usd=(market_info or {}).get("volume", 0),
            true_launch_age_seconds=true_launch_age_seconds,
            token_age_seconds=token_age_seconds,
            social_match=social_match,
            rug_result=rug_result,
            decision_score=decision["score"],
        )

        if edge_result["paper_trade_worthy"] and decision["score"] < decision["threshold"]:
            old_score = decision["score"]
            decision["score"] = min(
                100,
                max(decision["score"], decision["threshold"] + 1),
            )
            decision["reasons"].append(
                f'Edge override: {edge_result["edge_verdict"]} edge_score={edge_result["edge_score"]} lifted score {old_score}->{decision["score"]}'
            )

        decision["should_trade"] = decision["score"] >= decision["threshold"]

        if self.holder_check_candidate_worthy(decision, edge_result):
            holder_context = await self.evaluate_holder_cluster_risk(mint)
        else:
            holder_context = self.skipped_holder_cluster_risk(
                "Scanner holder check skipped below quote threshold"
            )
        cluster_context = self.wallet_cluster_risk_context(
            signal_type=signal_type,
            wallets=wallets,
            wallet_count=wallet_count,
            repeated_buys=repeated_buys,
        )
        rug_result = self.apply_holder_cluster_to_rug_result(
            rug_result=rug_result,
            holder_context=holder_context,
            cluster_context=cluster_context,
        )

        confirmation_result = self.confirmation_filter.evaluate(
            signal_type=signal_type,
            wallet_count=wallet_count,
            repeated_buys=repeated_buys,
            liquidity_usd=(market_info or {}).get("liquidity", 0),
            true_launch_age_seconds=true_launch_age_seconds,
            token_age_seconds=token_age_seconds,
        )
        decision["confirmation"] = confirmation_result

        if not confirmation_result["allow"]:
            decision["should_trade"] = False
            for reason in confirmation_result["reasons"]:
                decision["reasons"].append(f"CONFIRMATION BLOCK: {reason}")
        else:
            for warning in confirmation_result.get("warnings", []):
                decision["reasons"].append(f"CONFIRMATION: {warning}")

        strategy_guard_result = {
            "action": "ALLOW",
            "reason": "No paper-trade history available",
            "stats": None,
        }

        if self.paper_trader and self.settings.get("strategy_guard_enabled", True):
            strategy_guard_result = self.strategy_guard.evaluate_family(
                signal_type=signal_type,
                paper_state=self.paper_trader.get_state(),
            )

        decision["strategy_guard"] = strategy_guard_result

        if strategy_guard_result["action"] == "BLOCK":
            decision["should_trade"] = False
            decision["reasons"].append(
                f'STRATEGY GUARD BLOCK: {strategy_guard_result["reason"]}'
            )
        elif strategy_guard_result["action"] == "REDUCE_SIZE":
            decision["reasons"].append(
                f'STRATEGY GUARD SIZE CAUTION: {strategy_guard_result["reason"]}'
            )

        if not market_sanity["allow"]:
            decision["should_trade"] = False
            for reason in market_sanity["reasons"]:
                message = f"MARKET SANITY BLOCK: {reason}"
                if message not in decision["reasons"]:
                    decision["reasons"].append(message)

        wallet_main_quality = self.wallet_main_quality_gate(
            signal_type=signal_type,
            decision=decision,
            wallet_count=wallet_count,
            wallet_quality=wallet_quality,
            rug_result=rug_result,
            market_info=market_info,
        )
        decision["wallet_main_quality_gate"] = wallet_main_quality
        if not wallet_main_quality["allow"]:
            decision["should_trade"] = False
            decision["wallet_main_quality_block"] = True
            for reason in wallet_main_quality["reasons"]:
                decision["reasons"].append(f"WALLET MAIN QUALITY BLOCK: {reason}")

        print("⚡ PRE-SCORE:", decision["score"])
        print("🧬 EDGE:", edge_result["edge_verdict"], edge_result["edge_score"])
        print("🧯 STRATEGY GUARD:", strategy_guard_result["action"], strategy_guard_result["reason"])

        buy_quote = None
        buy_quote_analysis = {
            "pass": False,
            "reason": "quote_not_checked_low_prescore",
            "price_impact_pct": None,
        }

        sell_quote = None
        sell_quote_analysis = {
            "pass": False,
            "reason": "sell_quote_not_checked_low_prescore",
            "price_impact_pct": None,
        }

        if rug_result["hard_block"]:
            decision["should_trade"] = False
            decision["reasons"].append(
                f'HARD BLOCK: {rug_result["hard_block_reason"]}'
            )

        if decision["score"] < self.jupiter_prescore_threshold() and not edge_result["quote_worthy"]:
            decision["should_trade"] = False
            decision["reasons"].append("Pre-score and edge below Jupiter quote threshold")

            position_size_usd = 0

            self.print_decision(
                decision=decision,
                wallet_quality=wallet_quality,
                wallet_performance=wallet_performance,
                weighted_wallet_score=weighted_wallet_score,
                social_match=social_match,
                rug_result=rug_result,
                buy_quote_analysis=buy_quote_analysis,
                sell_quote_analysis=sell_quote_analysis,
                position_size_usd=position_size_usd,
                token_age_seconds=token_age_seconds,
                true_launch_age_seconds=true_launch_age_seconds,
                edge_result=edge_result,
            )

            decision_id = self.record_signal(
                mint=mint,
                now=now,
                signal_type=signal_type,
                wallets=wallets,
                wallet_count=wallet_count,
                weighted_wallet_score=weighted_wallet_score,
                social_match=social_match,
                wallet_quality=wallet_quality,
                wallet_performance=wallet_performance,
                dev_wallet=dev_wallet,
                dev_score=dev_score,
                token_inspection=token_inspection,
                liquidity_score=liquidity_score,
                volume_score=volume_score,
                market_info=market_info,
                rug_result=rug_result,
                buy_quote_analysis=buy_quote_analysis,
                sell_quote_analysis=sell_quote_analysis,
                buy_quote=buy_quote,
                sell_quote=sell_quote,
                position_size_usd=position_size_usd,
                token_age_seconds=token_age_seconds,
                true_launch_age_seconds=true_launch_age_seconds,
                launch_info=launch_info,
                decision=decision,
                edge_result=edge_result,
            )

            self.wallet_performance.record_signal(
                wallets=wallets,
                mint=mint,
                signal_type=signal_type,
                score=decision["score"],
                should_trade=False,
                token_age_seconds=true_launch_age_seconds,
            )

            print("⛔ Paper trade skipped early.")
            return

        quote_allowed, quote_gate_reason = self.should_request_swap_quote(
            decision=decision,
            edge_result=edge_result,
            rug_result=rug_result,
            market_sanity=market_sanity,
        )

        if not quote_allowed:
            decision["should_trade"] = False
            decision["reasons"].append(f"SWAP QUOTE SKIPPED: {quote_gate_reason}")
            buy_quote_analysis = {
                "pass": False,
                "reason": quote_gate_reason,
                "price_impact_pct": None,
            }
            sell_quote_analysis = {
                "pass": False,
                "reason": f"sell_quote_not_checked_{quote_gate_reason}",
                "price_impact_pct": None,
            }
            increment_component(
                "scanner",
                "swap_quote_quality_skips",
                last_swap_quote_skip_reason=quote_gate_reason,
                last_swap_quote_skip_mint=mint,
                last_swap_quote_skip_score=decision["score"],
                last_swap_quote_skip_edge=edge_result["edge_score"],
            )
        elif hasattr(self.rpc, "jupiter_quote") and self.rpc.jupiter_quote:
            if not self.consume_swap_quote_budget():
                buy_quote_analysis = {
                    "pass": False,
                    "reason": "swap_quote_budget_exhausted",
                    "price_impact_pct": None,
                }
                increment_component(
                    "scanner",
                    "swap_quote_budget_skips",
                    last_swap_quote_skip_reason="swap_quote_budget_exhausted",
                    last_swap_quote_skip_mint=mint,
                )
            else:
                buy_quote = await self.rpc.jupiter_quote.get_buy_quote(
                    output_mint=mint,
                    sol_amount=0.1,
                    slippage_bps=1500,
                )

                buy_quote_analysis = self.rpc.jupiter_quote.analyze_quote(
                    buy_quote,
                    max_price_impact_pct=8,
                )

            if buy_quote and buy_quote.get("ok"):
                token_amount_raw = int(buy_quote.get("out_amount") or 0)

                if token_amount_raw > 0:
                    if not self.consume_swap_quote_budget():
                        sell_quote_analysis = {
                            "pass": False,
                            "reason": "swap_quote_budget_exhausted_before_sell",
                            "price_impact_pct": None,
                        }
                        increment_component(
                            "scanner",
                            "swap_quote_budget_skips",
                            last_swap_quote_skip_reason="swap_quote_budget_exhausted_before_sell",
                            last_swap_quote_skip_mint=mint,
                        )
                    else:
                        sell_quote = await self.rpc.jupiter_quote.get_sell_quote(
                            input_mint=mint,
                            token_amount_raw=token_amount_raw,
                            slippage_bps=2000,
                        )

                        sell_quote_analysis = self.rpc.jupiter_quote.analyze_quote(
                            sell_quote,
                            max_price_impact_pct=10,
                        )

        if not buy_quote_analysis["pass"]:
            decision["should_trade"] = False
            decision["reasons"].append(
                f'BUY QUOTE BLOCK: {buy_quote_analysis["reason"]}'
            )

        if not sell_quote_analysis["pass"]:
            decision["should_trade"] = False
            decision["reasons"].append(
                f'EXIT LIQUIDITY BLOCK: {sell_quote_analysis["reason"]}'
            )

        if quote_allowed and buy_quote_analysis["pass"]:
            position_size_usd = self.position_sizer.size_trade(
                decision=decision,
                rug_result=rug_result,
                quote_analysis=buy_quote_analysis,
            )
        else:
            position_size_usd = 0

        if position_size_usd <= 0:
            decision["should_trade"] = False
            decision["reasons"].append("Position size resolved to 0")

        exploration_result = evaluate_paper_exploration(
            decision=decision,
            settings=self.settings,
            rug_result=rug_result,
            market_sanity=market_sanity,
            buy_quote_analysis=buy_quote_analysis,
            sell_quote_analysis=sell_quote_analysis,
            edge_result=edge_result,
            position_size_usd=position_size_usd,
            paper_state=self.paper_trader.get_state() if self.paper_trader else None,
        )
        decision = exploration_result["decision"]
        position_size_usd = exploration_result["position_size_usd"]

        self.print_decision(
            decision=decision,
            wallet_quality=wallet_quality,
            wallet_performance=wallet_performance,
            weighted_wallet_score=weighted_wallet_score,
            social_match=social_match,
            rug_result=rug_result,
            buy_quote_analysis=buy_quote_analysis,
            sell_quote_analysis=sell_quote_analysis,
            position_size_usd=position_size_usd,
            token_age_seconds=token_age_seconds,
            true_launch_age_seconds=true_launch_age_seconds,
            edge_result=edge_result,
        )

        decision_id = self.record_signal(
            mint=mint,
            now=now,
            signal_type=signal_type,
            wallets=wallets,
            wallet_count=wallet_count,
            weighted_wallet_score=weighted_wallet_score,
            social_match=social_match,
            wallet_quality=wallet_quality,
            wallet_performance=wallet_performance,
            dev_wallet=dev_wallet,
            dev_score=dev_score,
            token_inspection=token_inspection,
            liquidity_score=liquidity_score,
            volume_score=volume_score,
            market_info=market_info,
            rug_result=rug_result,
            buy_quote_analysis=buy_quote_analysis,
            sell_quote_analysis=sell_quote_analysis,
            buy_quote=buy_quote,
            sell_quote=sell_quote,
            position_size_usd=position_size_usd,
            token_age_seconds=token_age_seconds,
            true_launch_age_seconds=true_launch_age_seconds,
            launch_info=launch_info,
            decision=decision,
            edge_result=edge_result,
        )

        self.wallet_performance.record_signal(
            wallets=wallets,
            mint=mint,
            signal_type=signal_type,
            score=decision["score"],
            should_trade=decision["should_trade"],
            token_age_seconds=true_launch_age_seconds,
        )

        if not decision["should_trade"]:
            print("⛔ Paper trade skipped.")
            increment_component(
                "scanner",
                "paper_trade_skips",
                last_skip_mint=mint,
                last_skip_score=decision["score"],
                last_skip_edge=edge_result["edge_score"],
            )
            return

        if not self.paper_trader:
            print("⚠️ No paper trader available.")
            increment_component("scanner", "paper_trade_skips", last_skip_reason="no_paper_trader")
            self.update_decision_runtime_skip(decision_id, "no_paper_trader")
            try:
                from analysis.rejection_hooks import maybe_log_scanner_runtime_skip

                maybe_log_scanner_runtime_skip(
                    mint=mint,
                    decision_id=decision_id,
                    reason="no_paper_trader",
                    decision=decision,
                    settings=self.settings,
                    extra={"edge_score": edge_result.get("edge_score")},
                )
            except Exception:
                pass
            self.record_token_snapshot({
                "time": time.time(),
                "timestamp": time.time(),
                "source": "scanner",
                "context": "scanner_runtime_skip",
                "decision_id": decision_id,
                "decision_stage": "paper_trade_precheck",
                "mint": mint,
                "price": (market_info or {}).get("price") if isinstance(market_info, dict) else None,
                "liquidity": (market_info or {}).get("liquidity") if isinstance(market_info, dict) else None,
                "market_cap": self.market_cap_from_info(market_info),
                "risk_label": rug_result.get("risk_label"),
                "skip_reason": "no_paper_trader",
                "total_score": decision.get("score"),
                "edge_score": edge_result.get("edge_score"),
                "should_trade": decision.get("should_trade"),
            })
            return

        if not market_info:
            print("⚠️ No market data, skipping trade.")
            increment_component("scanner", "paper_trade_skips", last_skip_reason="no_market_data")
            self.update_decision_runtime_skip(decision_id, "no_market_data")
            try:
                from analysis.rejection_hooks import maybe_log_scanner_runtime_skip

                maybe_log_scanner_runtime_skip(
                    mint=mint,
                    decision_id=decision_id,
                    reason="no_market_data",
                    decision=decision,
                    settings=self.settings,
                    extra={"edge_score": edge_result.get("edge_score")},
                )
            except Exception:
                pass
            self.record_token_snapshot({
                "time": time.time(),
                "timestamp": time.time(),
                "source": "scanner",
                "context": "scanner_runtime_skip",
                "decision_id": decision_id,
                "decision_stage": "paper_trade_precheck",
                "mint": mint,
                "risk_label": rug_result.get("risk_label"),
                "skip_reason": "no_market_data",
                "total_score": decision.get("score"),
                "edge_score": edge_result.get("edge_score"),
                "should_trade": decision.get("should_trade"),
            })
            return

        entry_price = float(market_info.get("price") or 0)
        liquidity_usd = float(market_info.get("liquidity") or 10000)

        if entry_price <= 0:
            print("⚠️ Invalid entry price, skipping trade.")
            increment_component("scanner", "paper_trade_skips", last_skip_reason="invalid_entry_price")
            self.update_decision_runtime_skip(decision_id, "invalid_entry_price")
            try:
                from analysis.rejection_hooks import maybe_log_scanner_runtime_skip

                maybe_log_scanner_runtime_skip(
                    mint=mint,
                    decision_id=decision_id,
                    reason="invalid_entry_price",
                    decision=decision,
                    settings=self.settings,
                    extra={"edge_score": edge_result.get("edge_score")},
                )
            except Exception:
                pass
            self.record_token_snapshot({
                "time": time.time(),
                "timestamp": time.time(),
                "source": "scanner",
                "context": "scanner_runtime_skip",
                "decision_id": decision_id,
                "decision_stage": "paper_trade_precheck",
                "mint": mint,
                "price": entry_price,
                "liquidity": liquidity_usd,
                "market_cap": self.market_cap_from_info(market_info),
                "risk_label": rug_result.get("risk_label"),
                "skip_reason": "invalid_entry_price",
                "total_score": decision.get("score"),
                "edge_score": edge_result.get("edge_score"),
                "should_trade": decision.get("should_trade"),
            })
            return

        exploration = decision.get("exploration") or {}
        if exploration.get("route_observation_only"):
            route_label = "route_failed_observation"
        elif exploration.get("confirmation_observation_only"):
            route_label = "confirmation_block_observation"
        else:
            route_label = "quote_ok"

        trade = self.paper_trader.open_trade(
            mint=mint,
            entry_price=entry_price,
            size_usd=position_size_usd,
            liquidity_usd=liquidity_usd,
            reason=f'{signal_type}_{decision.get("paper_lane", "main")}_{decision["mode"]}_score_{decision["score"]}_{rug_result["risk_label"]}_{route_label}',
            wallets=wallets,
            market_info=market_info,
            paper_lane=decision.get("paper_lane", "main"),
            exploration=decision.get("paper_lane") == "exploration",
            signal_metadata={
                "decision_id": decision_id,
                "signal_type": signal_type,
                "paper_lane": decision.get("paper_lane", "main"),
                "exploration": decision.get("paper_lane") == "exploration",
                "main_strategy_should_trade": decision.get("main_strategy_should_trade"),
                "exploration_result": decision.get("exploration"),
                "wallet_count": wallet_count,
                "weighted_wallet_score": weighted_wallet_score,
                "wallet_quality": wallet_quality,
                "wallet_performance": wallet_performance,
                "risk_label": rug_result["risk_label"],
                "risk_score": rug_result["risk_score"],
                "buy_quote_analysis": buy_quote_analysis,
                "sell_quote_analysis": sell_quote_analysis,
                "score": decision["score"],
                "threshold": decision["threshold"],
                "mode": decision["mode"],
                "score_reasons": decision["reasons"],
                "edge_result": edge_result,
            },
        )

        if trade:
            increment_component(
                "scanner",
                "paper_trades_opened",
                last_trade_mint=mint,
                last_trade_score=decision["score"],
                last_trade_edge=edge_result["edge_score"],
            )

    def print_decision(
        self,
        decision,
        wallet_quality,
        wallet_performance,
        weighted_wallet_score,
        social_match,
        rug_result,
        buy_quote_analysis,
        sell_quote_analysis,
        position_size_usd,
        token_age_seconds,
        true_launch_age_seconds,
        edge_result,
    ):
        print("🧠 FINAL SCORE:", decision["score"])
        print("🎯 THRESHOLD:", decision["threshold"])
        print("📊 MODE:", decision["mode"])
        print("⏱️ BOT-SEEN AGE:", round(token_age_seconds or 0, 2), "sec")
        print("🚀 TRUE LAUNCH AGE:", round(true_launch_age_seconds or 0, 2), "sec")
        print("⚖️ WEIGHTED WALLET SIGNAL:", weighted_wallet_score)
        print("🧲 SOCIAL MATCH:", social_match.get("reason"), social_match.get("score_bonus"))
        print("👛 WALLET QUALITY AVG/MAX:", wallet_quality["avg_score"], wallet_quality["max_score"])
        print("📈 WALLET PERFORMANCE AVG/MAX:", wallet_performance["avg_score"], wallet_performance["max_score"])
        print("🛡️ RISK:", rug_result["risk_label"], rug_result["risk_score"])
        print("🧬 EDGE:", edge_result["edge_verdict"], edge_result["edge_score"])
        guard = decision.get("strategy_guard", {})
        print("🧯 STRATEGY GUARD:", guard.get("action"), guard.get("reason"))
        print("🧾 BUY QUOTE:", buy_quote_analysis["reason"], buy_quote_analysis["price_impact_pct"])
        print("🚪 SELL QUOTE:", sell_quote_analysis["reason"], sell_quote_analysis["price_impact_pct"])
        print("💵 POSITION SIZE:", position_size_usd)
        print("✅ SHOULD TRADE:", decision["should_trade"])

        for warning in rug_result["warnings"]:
            print(" ⚠️", warning)

        for reason in decision["reasons"]:
            print(" -", reason)

        for positive in edge_result.get("positives", []):
            print(" +", positive)

        for risk in edge_result.get("risks", []):
            print(" !", risk)

    def record_signal(
        self,
        mint,
        now,
        signal_type,
        wallets,
        wallet_count,
        weighted_wallet_score,
        social_match,
        wallet_quality,
        wallet_performance,
        dev_wallet,
        dev_score,
        token_inspection,
        liquidity_score,
        volume_score,
        market_info,
        rug_result,
        buy_quote_analysis,
        sell_quote_analysis,
        buy_quote,
        sell_quote,
        position_size_usd,
        token_age_seconds,
        true_launch_age_seconds,
        launch_info,
        decision,
        edge_result,
    ):
        payload = {
            "mint": mint,
            "type": signal_type,
            "wallets": wallets,
            "wallet_count": wallet_count,
            "weighted_wallet_score": weighted_wallet_score,
            "social_match": social_match,
            "social_bonus": social_match.get("score_bonus", 0),
            "social_matched": social_match.get("matched", False),
            "social_keywords": social_match.get("matched_keywords", []),
            "social_account": social_match.get("matched_account"),
            "wallet_quality": wallet_quality,
            "wallet_performance": wallet_performance,
            "dev_wallet": dev_wallet,
            "dev_score": dev_score.get("score", 0),
            "dev_label": dev_score.get("label", "Unknown"),
            "dev_bonded_tokens": dev_score.get("bonded_tokens", 0),
            "token_inspection": token_inspection,
            "token_standard": token_inspection.get("token_standard"),
            "token_extensions": token_inspection.get("extensions", []),
            "token_mechanics_risk": token_inspection.get("risk_label"),
            "token_mechanics_reasons": token_inspection.get("reasons", []),
            "liquidity_score": liquidity_score,
            "volume_score": volume_score,
            "market_info": market_info,
            "risk_label": rug_result["risk_label"],
            "risk_score": rug_result["risk_score"],
            "risk_warnings": rug_result["warnings"],
            "hard_block": rug_result["hard_block"],
            "hard_block_reason": rug_result["hard_block_reason"],
            "holder_concentration": rug_result.get("holder_concentration"),
            "holder_concentration_risk": rug_result.get("holder_concentration_risk"),
            "holder_concentration_reasons": rug_result.get("holder_concentration_reasons", []),
            "holder_concentration_metrics": rug_result.get("holder_concentration_metrics", {}),
            "linked_wallet_risk": rug_result.get("linked_wallet_risk"),
            "buy_quote_pass": buy_quote_analysis["pass"],
            "buy_quote_reason": buy_quote_analysis["reason"],
            "buy_quote_price_impact_pct": buy_quote_analysis["price_impact_pct"],
            **self.quote_decision_fields("buy", buy_quote, 1500, 8),
            "sell_quote_pass": sell_quote_analysis["pass"],
            "sell_quote_reason": sell_quote_analysis["reason"],
            "sell_quote_price_impact_pct": sell_quote_analysis["price_impact_pct"],
            **self.quote_decision_fields("sell", sell_quote, 2000, 10),
            "position_size_usd": position_size_usd,
            "token_age_seconds": token_age_seconds,
            "true_launch_age_seconds": true_launch_age_seconds,
            "launch_info": launch_info,
            "total_score": decision["score"],
            "score_threshold": decision["threshold"],
            "mode": decision["mode"],
            "should_trade": decision["should_trade"],
            "paper_lane": decision.get("paper_lane", "main"),
            "exploration": decision.get("paper_lane") == "exploration",
            "main_strategy_should_trade": decision.get("main_strategy_should_trade"),
            "exploration_result": decision.get("exploration"),
            "wallet_main_quality_gate": decision.get("wallet_main_quality_gate"),
            "score_reasons": decision["reasons"],
            "edge_score": edge_result.get("edge_score"),
            "edge_verdict": edge_result.get("edge_verdict"),
            "edge_quote_worthy": edge_result.get("quote_worthy"),
            "edge_paper_trade_worthy": edge_result.get("paper_trade_worthy"),
            "edge_positives": edge_result.get("positives", []),
            "edge_risks": edge_result.get("risks", []),
            "confirmation_allow": decision.get("confirmation", {}).get("allow"),
            "confirmation_reasons": decision.get("confirmation", {}).get("reasons", []),
            "confirmation_warnings": decision.get("confirmation", {}).get("warnings", []),
            "strategy_guard_action": decision.get("strategy_guard", {}).get("action"),
            "strategy_guard_reason": decision.get("strategy_guard", {}).get("reason"),
            "strategy_guard_stats": decision.get("strategy_guard", {}).get("stats"),
            "timestamp": now,
        }

        decision_id = None
        try:
            decision_record = build_decision_record(payload)
            decision_id = self.store.upsert_decision(decision_record)
            payload["decision_id"] = decision_id
        except Exception as exc:
            print("⚠️ Decision ledger write failed:", exc)

        if decision_id and not decision.get("should_trade"):
            try:
                from analysis.rejection_hooks import maybe_log_scanner_strategy_skip

                maybe_log_scanner_strategy_skip(payload, decision, decision_id, self.settings)
            except Exception:
                pass

        snapshot_context = (
            "scanner_entry_candidate"
            if decision.get("should_trade")
            else "scanner_skip"
        )
        self.record_token_snapshot({
            **payload,
            "source": "scanner",
            "context": snapshot_context,
            "time": now,
            "price": (market_info or {}).get("price") if isinstance(market_info, dict) else None,
            "liquidity": (market_info or {}).get("liquidity") if isinstance(market_info, dict) else None,
            "volume": (market_info or {}).get("volume") if isinstance(market_info, dict) else None,
            "market_cap": self.market_cap_from_info(market_info),
            "decision_stage": "signal_evaluation",
        })

        add_alert(payload)

        update_token(mint, {
            "last_signal_time": now,
            "signal_type": signal_type,
            "wallet_count": wallet_count,
            "weighted_wallet_score": weighted_wallet_score,
            "social_match": social_match,
            "social_bonus": social_match.get("score_bonus", 0),
            "social_matched": social_match.get("matched", False),
            "social_keywords": social_match.get("matched_keywords", []),
            "social_account": social_match.get("matched_account"),
            "wallet_quality": wallet_quality,
            "wallet_performance": wallet_performance,
            "dev_wallet": dev_wallet,
            "dev_score": dev_score.get("score", 0),
            "dev_label": dev_score.get("label", "Unknown"),
            "dev_bonded_tokens": dev_score.get("bonded_tokens", 0),
            "token_inspection": token_inspection,
            "token_standard": token_inspection.get("token_standard"),
            "token_extensions": token_inspection.get("extensions", []),
            "token_mechanics_risk": token_inspection.get("risk_label"),
            "token_mechanics_reasons": token_inspection.get("reasons", []),
            "liquidity_score": liquidity_score,
            "volume_score": volume_score,
            "market_info": market_info,
            "risk_label": rug_result["risk_label"],
            "risk_score": rug_result["risk_score"],
            "risk_warnings": rug_result["warnings"],
            "hard_block": rug_result["hard_block"],
            "hard_block_reason": rug_result["hard_block_reason"],
            "holder_concentration": rug_result.get("holder_concentration"),
            "holder_concentration_risk": rug_result.get("holder_concentration_risk"),
            "holder_concentration_reasons": rug_result.get("holder_concentration_reasons", []),
            "holder_concentration_metrics": rug_result.get("holder_concentration_metrics", {}),
            "linked_wallet_risk": rug_result.get("linked_wallet_risk"),
            "buy_quote_pass": buy_quote_analysis["pass"],
            "buy_quote_reason": buy_quote_analysis["reason"],
            "buy_quote_price_impact_pct": buy_quote_analysis["price_impact_pct"],
            "sell_quote_pass": sell_quote_analysis["pass"],
            "sell_quote_reason": sell_quote_analysis["reason"],
            "sell_quote_price_impact_pct": sell_quote_analysis["price_impact_pct"],
            "position_size_usd": position_size_usd,
            "token_age_seconds": token_age_seconds,
            "true_launch_age_seconds": true_launch_age_seconds,
            "launch_info": launch_info,
            "total_score": decision["score"],
            "score_threshold": decision["threshold"],
            "mode": decision["mode"],
            "should_trade": decision["should_trade"],
            "paper_lane": decision.get("paper_lane", "main"),
            "exploration": decision.get("paper_lane") == "exploration",
            "main_strategy_should_trade": decision.get("main_strategy_should_trade"),
            "exploration_result": decision.get("exploration"),
            "wallet_main_quality_gate": decision.get("wallet_main_quality_gate"),
            "score_reasons": decision["reasons"],
            "edge_score": edge_result.get("edge_score"),
            "edge_verdict": edge_result.get("edge_verdict"),
            "edge_quote_worthy": edge_result.get("quote_worthy"),
            "edge_paper_trade_worthy": edge_result.get("paper_trade_worthy"),
            "edge_positives": edge_result.get("positives", []),
            "edge_risks": edge_result.get("risks", []),
            "confirmation_allow": decision.get("confirmation", {}).get("allow"),
            "confirmation_reasons": decision.get("confirmation", {}).get("reasons", []),
            "confirmation_warnings": decision.get("confirmation", {}).get("warnings", []),
            "strategy_guard_action": decision.get("strategy_guard", {}).get("action"),
            "strategy_guard_reason": decision.get("strategy_guard", {}).get("reason"),
            "strategy_guard_stats": decision.get("strategy_guard", {}).get("stats"),
            "decision_id": decision_id,
        })
        return decision_id

    async def find_dev_wallet(self, mint):
        try:
            sigs = await self.rpc.rpc_call(
                "getSignaturesForAddress",
                [mint, {"limit": 20}]
            )

            if not sigs:
                return None

            results = sigs.get("result", [])
            if not results:
                return None

            oldest_sig = results[-1]["signature"]

            tx = await self.rpc.get_transaction(oldest_sig)
            if not tx or not tx.get("result"):
                return None

            accounts = tx["result"]["transaction"]["message"]["accountKeys"]

            if not accounts:
                return None

            first = accounts[0]

            if isinstance(first, dict):
                return first.get("pubkey")

            return first

        except Exception as e:
            print("⚠️ Dev lookup failed:", e)
            return None

    def extract_wallet_hits(self, result):
        accounts = set()

        try:
            keys = result["transaction"]["message"]["accountKeys"]

            for acc in keys:
                if isinstance(acc, dict):
                    pubkey = acc.get("pubkey")
                else:
                    pubkey = acc

                if pubkey:
                    accounts.add(pubkey)

        except Exception:
            return []

        return [w for w in self.observed_wallets if w in accounts]

    def extract_token_changes(self, result, wallet_hits):
        changes = []

        try:
            meta = result.get("meta", {})

            pre = meta.get("preTokenBalances", [])
            post = meta.get("postTokenBalances", [])

            pre_map = self.build_token_balance_map(pre)
            post_map = self.build_token_balance_map(post)

            keys = set(pre_map.keys()) | set(post_map.keys())
            owner_deltas = {}
            for owner, mint in keys:
                owner_deltas[(owner, mint)] = post_map.get((owner, mint), 0) - pre_map.get((owner, mint), 0)
            route = self.dex_route_metadata(result)

            for owner, mint in keys:
                if owner not in wallet_hits:
                    continue

                delta = owner_deltas.get((owner, mint), 0)

                if abs(delta) < 1e-9:
                    continue
                if mint in TRADE_QUOTE_MINTS:
                    continue

                quote_mint, quote_delta = self.trade_quote_delta_for_owner(
                    owner=owner,
                    token_mint=mint,
                    token_delta=delta,
                    owner_deltas=owner_deltas,
                )
                changes.append({
                    "wallet": owner,
                    "mint": mint,
                    "delta": delta,
                    "signature": self.transaction_signature(result),
                    "block_time": result.get("blockTime"),
                    "native_delta": self.native_delta_for_wallet(result, owner),
                    "quote_mint": quote_mint,
                    "quote_delta": quote_delta,
                    "dex_route_detected": route["detected"],
                    "dex_route_programs": route["programs"],
                    "dex_route_program_ids": route["program_ids"],
                })

        except Exception as e:
            print("❌ Token parsing error:", e)

        return changes

    def trade_quote_delta_for_owner(self, owner, token_mint, token_delta, owner_deltas):
        if token_mint in TRADE_QUOTE_MINTS:
            return None, None

        candidates = []
        for quote_mint in TRADE_QUOTE_MINTS:
            quote_delta = owner_deltas.get((owner, quote_mint))
            if quote_delta is None or abs(quote_delta) < 1e-12:
                continue
            if token_delta and quote_delta and (token_delta > 0) == (quote_delta > 0):
                continue
            candidates.append((quote_mint, quote_delta))

        if not candidates:
            return None, None

        candidates.sort(key=lambda item: abs(item[1]), reverse=True)
        return candidates[0]

    def build_token_balance_map(self, balances):
        balance_map = {}

        for item in balances:
            try:
                owner = item.get("owner")
                mint = item.get("mint")

                amt_info = item.get("uiTokenAmount", {})
                amount = amt_info.get("uiAmount")

                if amount is None:
                    amount = float(amt_info.get("uiAmountString") or 0)

                if owner and mint:
                    balance_map[(owner, mint)] = float(amount or 0)

            except Exception:
                continue

        return balance_map
