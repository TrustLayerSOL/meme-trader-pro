import asyncio
import time

from core.decision_ledger import build_decision_record
from core.holder_concentration import HolderConcentrationAnalyzer
from core.runtime_status import increment_component, load_status, update_component
from core.settings_manager import load_settings
from core.storage import EventStore


DEXSCREENER_LATEST_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
DEXSCREENER_LATEST_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"
DEXSCREENER_TOP_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/top/v1"

MAJOR_SYMBOLS = {"btc", "eth", "sol", "usdc", "usdt", "dai", "wbtc", "weth", "wsol"}
QUOTE_RETRYABLE_REASONS = {
    "market_radar_quote_budget_exhausted",
    "market_radar_quote_cooldown",
    "shared_quote_cooldown_after_429",
    "jupiter_cooldown_after_429",
}


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    return int(safe_float(value, default))


def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def age_seconds(timestamp):
    value = safe_float(timestamp, None)
    if value is None:
        return None
    return max(0, time.time() - value)


def timestamp_age_seconds(timestamp):
    value = safe_float(timestamp, None)
    if value is None or value <= 0:
        return None
    if value > 10_000_000_000:
        value = value / 1000
    return max(0, time.time() - value)


def source_bonus(source):
    source = str(source or "")
    if "top_boost" in source:
        return 12
    if "boost" in source:
        return 10
    if "profile" in source:
        return 4
    return 0


def increment_counter(counter, key):
    key = str(key or "unknown")
    counter[key] = counter.get(key, 0) + 1


def market_radar_skip_bucket(reason):
    reason = str(reason or "")
    if "quote" in reason or "429" in reason or "cooldown" in reason:
        return "quote_or_route"
    if "liquidity" in reason:
        return "liquidity"
    if "holder" in reason or "holder_concentration" in reason:
        return "holder_concentration"
    if "volume" in reason:
        return "volume_quality"
    if "momentum" in reason or "collapsing" in reason:
        return "momentum"
    if "flow" in reason:
        return "order_flow"
    if "pair" in reason:
        return "pair_age"
    if "social" in reason or "site" in reason:
        return "social_proof"
    if "market_cap" in reason:
        return "market_cap"
    if "activity" in reason or "score" in reason:
        return "activity_or_score"
    if "major" in reason or "stable" in reason:
        return "universe_filter"
    if "paper_trader" in reason or "existing_trade" in reason or "price" in reason:
        return "runtime_precheck"
    return "other"


def quote_retryable_reason(reason):
    return str(reason or "") in QUOTE_RETRYABLE_REASONS


def has_social_or_site(candidate, market_info):
    candidate = candidate if isinstance(candidate, dict) else {}
    market_info = market_info if isinstance(market_info, dict) else {}
    if market_info.get("twitter") or market_info.get("telegram") or market_info.get("website"):
        return True
    socials = market_info.get("socials") if isinstance(market_info.get("socials"), list) else []
    websites = market_info.get("websites") if isinstance(market_info.get("websites"), list) else []
    links = candidate.get("links") if isinstance(candidate.get("links"), list) else []
    return bool(socials or websites or links)


def market_radar_decision_summary(score, should_trade, buy_analysis=None, sell_analysis=None):
    score = score if isinstance(score, dict) else {}
    buy_analysis = buy_analysis if isinstance(buy_analysis, dict) else {}
    sell_analysis = sell_analysis if isinstance(sell_analysis, dict) else {}
    blockers = list(score.get("blockers") or [])

    skip_reason = None
    quote_block_reason = None
    if should_trade:
        open_reason = "hot_candidate_quote_passed"
    else:
        open_reason = None
        if buy_analysis.get("pass") is False and buy_analysis.get("reason") not in {
            None,
            "quote_not_checked_market_radar_score",
        }:
            quote_block_reason = buy_analysis.get("reason")
            skip_reason = quote_block_reason
        elif sell_analysis.get("pass") is False and sell_analysis.get("reason") not in {
            None,
            "sell_quote_not_checked_market_radar_score",
            "sell_quote_not_checked_buy_failed",
        }:
            quote_block_reason = sell_analysis.get("reason")
            skip_reason = quote_block_reason
        elif blockers:
            skip_reason = blockers[0]
        else:
            skip_reason = "score_below_market_radar_threshold"

    quote_retryable = quote_retryable_reason(quote_block_reason or skip_reason)
    return {
        "action": "open_attempt" if should_trade else "skip",
        "open_reason": open_reason,
        "skip_reason": skip_reason,
        "skip_bucket": market_radar_skip_bucket(skip_reason),
        "quote_block_reason": quote_block_reason,
        "quote_retryable": quote_retryable,
    }


def market_radar_holder_cluster_placeholder():
    """Score gate failed: holder RPC intentionally not invoked."""
    return {
        "holder_concentration_risk": "UNKNOWN",
        "holder_concentration_reasons": ["market_radar_holder_check_not_applicable_score_blocked"],
        "holder_concentration_metrics": {},
        "holder_concentration": None,
    }


def market_radar_holder_cluster_skipped(reason):
    """Enabled path but RPC skipped (disabled, budget, no client, timeout, error)."""
    return {
        "holder_concentration_risk": "UNKNOWN",
        "holder_concentration_reasons": [reason],
        "holder_concentration_metrics": {},
        "holder_concentration": None,
    }


def market_radar_linked_wallet_placeholder(wallet_count=0, wallets=None):
    """Aligned with scanner.wallet_cluster_risk_context when graph source is unavailable."""
    return {
        "risk_label": "NOT_CHECKED",
        "reason": "no_linked_wallet_graph_source",
        "observed_wallet_cluster": {
            "signal_type": "market_radar_hot",
            "wallet_count": wallet_count,
            "cluster_threshold": None,
            "cluster_window_seconds": None,
            "repeated_buys": None,
            "wallets": list(wallets or []),
            "lane": "market_radar",
        },
    }


def market_radar_action_reasons(score, decision):
    score = score if isinstance(score, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    reasons = []
    if decision.get("open_reason"):
        reasons.append(f"market_radar_open: {decision.get('open_reason')}")
    elif decision.get("skip_reason"):
        reasons.append(f"market_radar_skip: {decision.get('skip_reason')}")
    reasons.extend(list(score.get("reasons") or []))
    reasons.extend([f"BLOCK: {item}" for item in score.get("blockers") or []])
    return reasons


def normalize_market_radar_candidates(rows, source):
    candidates = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("chainId") or "").lower() != "solana":
            continue
        mint = (
            row.get("tokenAddress")
            or row.get("token_address")
            or row.get("address")
            or row.get("mint")
        )
        mint = str(mint or "").strip()
        if not mint or mint in seen:
            continue
        seen.add(mint)
        candidates.append({
            "mint": mint,
            "chain_id": row.get("chainId"),
            "source": source,
            "sources": [source],
            "url": row.get("url"),
            "icon": row.get("icon"),
            "header": row.get("header"),
            "description": row.get("description"),
            "boost_amount": safe_float(row.get("amount"), None),
            "boost_total_amount": safe_float(row.get("totalAmount"), None),
            "raw": row,
        })
    return candidates


def merge_candidates(groups):
    merged = {}
    for group in groups or []:
        for item in group or []:
            mint = item.get("mint")
            if not mint:
                continue
            current = merged.setdefault(mint, dict(item))
            current.setdefault("sources", [])
            for source in item.get("sources") or [item.get("source")]:
                if source and source not in current["sources"]:
                    current["sources"].append(source)
            for key, value in item.items():
                if current.get(key) in (None, "", [], 0) and value not in (None, "", [], 0):
                    current[key] = value
    return list(merged.values())


def market_number(info, *keys):
    info = info if isinstance(info, dict) else {}
    for key in keys:
        value = safe_float(info.get(key), None)
        if value is not None:
            return value
    return None


def score_hot_market_candidate(candidate, market_info, settings=None):
    candidate = candidate if isinstance(candidate, dict) else {}
    market_info = market_info if isinstance(market_info, dict) else {}
    settings = settings if isinstance(settings, dict) else {}

    min_score = safe_float(settings.get("market_radar_min_score"), 70)
    min_liquidity = safe_float(settings.get("market_radar_min_liquidity_usd"), 25_000)
    max_market_cap = safe_float(settings.get("market_radar_max_market_cap_usd"), 10_000_000)
    min_market_cap = safe_float(settings.get("market_radar_min_market_cap_usd"), 75_000)
    min_m5_tx = safe_float(settings.get("market_radar_min_m5_tx_count"), 40)
    min_h1_volume = safe_float(settings.get("market_radar_min_h1_volume_usd"), 100_000)
    min_buy_ratio = safe_float(settings.get("market_radar_min_buy_ratio"), 0.48)
    quality_gate_enabled = safe_bool(settings.get("market_radar_quality_gate_enabled"), True)
    entry_min_liquidity = safe_float(settings.get("market_radar_entry_min_liquidity_usd"), 100_000)
    entry_min_market_cap = safe_float(settings.get("market_radar_entry_min_market_cap_usd"), 250_000)
    min_liquidity_to_market_cap = safe_float(settings.get("market_radar_min_liquidity_to_market_cap"), 0.03)
    max_volume_liquidity_ratio = safe_float(settings.get("market_radar_max_volume_liquidity_ratio"), 8.0)
    min_m5_price_change = safe_float(settings.get("market_radar_min_m5_price_change_pct"), -12.0)
    min_h1_price_change = safe_float(settings.get("market_radar_min_h1_price_change_pct"), -25.0)
    max_buy_ratio = safe_float(settings.get("market_radar_max_buy_ratio"), 0.88)
    max_sell_ratio = safe_float(settings.get("market_radar_max_sell_ratio"), 0.70)
    min_avg_tx_usd = safe_float(settings.get("market_radar_min_avg_tx_usd"), 50.0)
    require_social = safe_bool(settings.get("market_radar_require_social_or_site"), True)
    min_pair_age_seconds = safe_float(settings.get("market_radar_min_pair_age_seconds"), 30 * 60)
    max_pair_age_seconds = safe_float(settings.get("market_radar_max_pair_age_seconds"), 24 * 3600)

    symbol = str(market_info.get("symbol") or "").strip().lower()
    price = market_number(market_info, "price")
    liquidity = market_number(market_info, "liquidity", "liquidity_usd")
    market_cap = market_number(market_info, "market_cap", "marketCap", "fdv")
    tx_count = market_number(market_info, "tx_count", "tx_count_m5") or 0
    buy_count = market_number(market_info, "buy_count", "buy_count_m5") or 0
    sell_count = market_number(market_info, "sell_count", "sell_count_m5") or 0
    volume_h1 = market_number(market_info, "volume_h1", "volume")
    volume_h24 = market_number(market_info, "volume_h24", "volume")
    price_change_m5 = market_number(market_info, "price_change_m5")
    price_change_h1 = market_number(market_info, "price_change_h1")
    price_change_h6 = market_number(market_info, "price_change_h6")
    price_change_h24 = market_number(market_info, "price_change_h24", "price_change_24h")

    blockers = []
    reasons = []
    score = 0

    if not price or price <= 0:
        blockers.append("missing_price")
    if liquidity is None or liquidity < min_liquidity:
        blockers.append("liquidity_below_hot_lane")
    if market_cap is not None and market_cap < min_market_cap:
        blockers.append("market_cap_below_hot_lane")
    if market_cap is not None and market_cap > max_market_cap:
        blockers.append("market_cap_above_meme_window")
    if symbol in MAJOR_SYMBOLS:
        blockers.append("known_major_or_stable_symbol")

    total_m5 = buy_count + sell_count
    buy_ratio = (buy_count / total_m5) if total_m5 > 0 else 0
    sell_ratio = (sell_count / total_m5) if total_m5 > 0 else 0
    volume_liquidity_ratio = (volume_h1 / liquidity) if volume_h1 and liquidity else None
    liquidity_to_market_cap = (liquidity / market_cap) if liquidity and market_cap else None
    avg_tx_usd = (volume_h1 / tx_count) if volume_h1 and tx_count else None
    social_or_site = has_social_or_site(candidate, market_info)
    pair_age = timestamp_age_seconds(
        market_info.get("pair_created_at")
        or market_info.get("pairCreatedAt")
        or market_info.get("pair_created")
    )
    market_cap_inside_window = market_cap is not None and min_market_cap <= market_cap <= max_market_cap
    fresh_pair_high_activity_exception = (
        pair_age is not None
        and pair_age < min_pair_age_seconds
        and social_or_site
        and liquidity is not None
        and liquidity >= max(entry_min_liquidity * 3, 300_000)
        and market_cap_inside_window
        and volume_h1 is not None
        and volume_h1 >= max(min_h1_volume * 10, 1_000_000)
        and tx_count >= min_m5_tx * 8
        and buy_ratio >= min_buy_ratio
        and buy_ratio <= max_buy_ratio
        and sell_ratio <= max_sell_ratio
        and (price_change_m5 is None or price_change_m5 >= min_m5_price_change)
        and (price_change_h1 is None or price_change_h1 >= min_h1_price_change)
        and (avg_tx_usd is None or avg_tx_usd >= min_avg_tx_usd)
    )

    if quality_gate_enabled:
        if liquidity is None or liquidity < entry_min_liquidity:
            blockers.append("entry_liquidity_below_quality_gate")
        if market_cap is not None and market_cap < entry_min_market_cap:
            blockers.append("entry_market_cap_below_quality_gate")
        if liquidity_to_market_cap is not None and liquidity_to_market_cap < min_liquidity_to_market_cap:
            blockers.append("liquidity_market_cap_ratio_too_low")
        if volume_liquidity_ratio is not None and volume_liquidity_ratio > max_volume_liquidity_ratio:
            blockers.append("h1_volume_liquidity_anomaly")
        if price_change_m5 is not None and price_change_m5 < min_m5_price_change:
            blockers.append("entry_m5_price_decay")
        if price_change_h1 is not None and price_change_h1 < min_h1_price_change:
            blockers.append("collapsing_h1_momentum")
        if total_m5 >= min_m5_tx and buy_ratio > max_buy_ratio:
            blockers.append("one_sided_buy_flow")
        if total_m5 >= min_m5_tx and sell_ratio > max_sell_ratio:
            blockers.append("one_sided_sell_flow")
        if avg_tx_usd is not None and tx_count >= min_m5_tx * 10 and avg_tx_usd < min_avg_tx_usd:
            blockers.append("micro_tx_volume_anomaly")
        if require_social and not social_or_site:
            blockers.append("missing_social_or_site_quality_gate")
        if fresh_pair_high_activity_exception:
            reasons.append("fresh_pair_high_activity_exception")
        if pair_age is not None and pair_age < min_pair_age_seconds and not fresh_pair_high_activity_exception:
            blockers.append("pair_too_fresh_for_market_radar")
        if pair_age is not None and pair_age > max_pair_age_seconds:
            has_fresh_strength = (
                price_change_h1 is not None
                and price_change_h1 > 0
                and tx_count >= min_m5_tx * 2
                and bool(volume_h1 and volume_h1 >= min_h1_volume * 2)
            )
            if not has_fresh_strength:
                blockers.append("stale_pair_without_fresh_strength")

    if liquidity and liquidity >= 250_000:
        score += 20
        reasons.append("deep_hot_liquidity")
    elif liquidity and liquidity >= min_liquidity:
        score += 12
        reasons.append("sufficient_hot_liquidity")

    if market_cap and min_market_cap <= market_cap <= max_market_cap:
        score += 12
        reasons.append("market_cap_inside_meme_window")

    if tx_count >= min_m5_tx:
        score += 24
        reasons.append("hot_m5_activity")
    elif tx_count >= min_m5_tx * 0.5:
        score += 10
        reasons.append("moderate_m5_activity")

    if volume_h1 and volume_h1 >= min_h1_volume * 5:
        score += 22
        reasons.append("heavy_h1_volume")
    elif volume_h1 and volume_h1 >= min_h1_volume:
        score += 14
        reasons.append("solid_h1_volume")
    elif volume_h24 and volume_h24 >= min_h1_volume * 10:
        score += 8
        reasons.append("large_24h_volume")

    if buy_ratio >= min_buy_ratio and total_m5 >= min_m5_tx:
        score += 8
        reasons.append("healthy_buy_ratio")

    if price_change_h6 is not None and price_change_h6 > 50:
        score += 12
        reasons.append("strong_h6_momentum")
    elif price_change_h24 is not None and price_change_h24 > 100:
        score += 8
        reasons.append("strong_24h_momentum")

    if price_change_h1 is not None and price_change_h1 > -25:
        score += 5
        reasons.append("not_collapsing_h1")

    source_bonuses = []
    source_names = []
    for source in candidate.get("sources") or [candidate.get("source")]:
        bonus = source_bonus(source)
        if bonus:
            source_bonuses.append(bonus)
            source_names.append(str(source))
    if source_bonuses:
        score += max(source_bonuses)
        reasons.extend(source_names)

    if social_or_site:
        score += 6
        reasons.append("has_social_or_site")

    if quality_gate_enabled:
        if tx_count < min_m5_tx or not volume_h1 or volume_h1 < min_h1_volume:
            blockers.append("insufficient_hot_activity")
    elif tx_count < min_m5_tx and (not volume_h1 or volume_h1 < min_h1_volume):
        blockers.append("insufficient_hot_activity")

    allowed = not blockers and score >= min_score
    if not allowed and score < min_score:
        blockers.append("score_below_market_radar_threshold")

    return {
        "allowed": allowed,
        "score": round(score, 2),
        "threshold": min_score,
        "reasons": reasons,
        "blockers": blockers,
        "buy_ratio": round(buy_ratio, 4),
        "sell_ratio": round(sell_ratio, 4),
        "volume_liquidity_ratio": round(volume_liquidity_ratio, 4) if volume_liquidity_ratio is not None else None,
        "liquidity_to_market_cap": round(liquidity_to_market_cap, 4) if liquidity_to_market_cap is not None else None,
        "avg_tx_usd": round(avg_tx_usd, 2) if avg_tx_usd is not None else None,
        "price_change_m5": round(price_change_m5, 2) if price_change_m5 is not None else None,
        "pair_age_seconds": round(pair_age, 2) if pair_age is not None else None,
        "position_size_usd": safe_float(settings.get("market_radar_position_size_usd"), 5),
    }


class MarketRadar:
    holder_analyzer = HolderConcentrationAnalyzer()

    def __init__(
        self,
        market_checker,
        paper_trader,
        jupiter_quote=None,
        store=None,
        rpc=None,
        settings_loader=load_settings,
    ):
        self.market_checker = market_checker
        self.paper_trader = paper_trader
        self.jupiter_quote = jupiter_quote
        self.rpc = rpc
        self.store = store or EventStore()
        self.settings_loader = settings_loader
        self.seen_mints = {}
        self.deferred_mints = {}
        self.last_quote_attempt_at = 0
        self.quotes_this_cycle = 0
        self.holder_checks_this_cycle = 0

    async def fetch_json(self, url):
        await self.market_checker.init_session()
        async with self.market_checker.session.get(url) as resp:
            if resp.status != 200:
                update_component("market_radar", status="fetch_error", last_error=f"{url} status {resp.status}")
                return []
            data = await resp.json()
            return data if isinstance(data, list) else []

    async def fetch_candidates(self):
        latest_profiles, latest_boosts, top_boosts = await asyncio.gather(
            self.fetch_json(DEXSCREENER_LATEST_PROFILES_URL),
            self.fetch_json(DEXSCREENER_LATEST_BOOSTS_URL),
            self.fetch_json(DEXSCREENER_TOP_BOOSTS_URL),
            return_exceptions=True,
        )
        groups = []
        for rows, source in [
            (latest_profiles, "dexscreener_latest_profiles"),
            (latest_boosts, "dexscreener_latest_boosts"),
            (top_boosts, "dexscreener_top_boosts"),
        ]:
            if isinstance(rows, Exception):
                update_component("market_radar", status="fetch_exception", last_error=str(rows)[:180])
                continue
            groups.append(normalize_market_radar_candidates(rows, source))
        return merge_candidates(groups)

    def recently_seen(self, mint, cooldown_seconds):
        deferred_until = self.deferred_mints.get(mint)
        if deferred_until and time.time() < deferred_until:
            return True
        last_seen = self.seen_mints.get(mint)
        return bool(last_seen and time.time() - last_seen < cooldown_seconds)

    def mark_seen(self, mint):
        self.seen_mints[mint] = time.time()

    def defer_candidate(self, mint, seconds):
        if mint and safe_float(seconds, 0) > 0:
            self.deferred_mints[mint] = time.time() + safe_float(seconds, 0)

    def has_existing_trade(self, mint):
        state = self.paper_trader.get_state() if self.paper_trader else {}
        for key in ("open_trades", "closed_trades", "failed_trades"):
            for trade in state.get(key, []) or []:
                if trade.get("mint") == mint or trade.get("token_mint") == mint:
                    return True
        return False

    def mr_holder_budget(self, settings):
        return max(0, safe_int(settings.get("market_radar_max_holder_checks_per_cycle"), 2))

    def mr_holder_timeout(self, settings):
        timeout = safe_float(settings.get("market_radar_holder_check_timeout_seconds"), 3)
        return timeout if timeout and timeout > 0 else 3

    async def evaluate_market_radar_holder_cluster(self, mint, settings):
        if not safe_bool(settings.get("market_radar_holder_check_enabled"), False):
            return market_radar_holder_cluster_skipped("market_radar_holder_check_disabled")
        budget = self.mr_holder_budget(settings)
        if budget <= 0:
            return market_radar_holder_cluster_skipped("market_radar_holder_check_budget_disabled")
        if self.holder_checks_this_cycle >= budget:
            return market_radar_holder_cluster_skipped("market_radar_holder_check_budget_exhausted")
        if not self.rpc or not hasattr(self.rpc, "rpc_call"):
            return market_radar_holder_cluster_skipped("market_radar_holder_check_no_rpc")

        self.holder_checks_this_cycle += 1
        try:
            response = await asyncio.wait_for(
                self.rpc.rpc_call(
                    "getTokenLargestAccounts",
                    [
                        mint,
                        {"commitment": "confirmed"},
                    ],
                ),
                timeout=self.mr_holder_timeout(settings),
            )
        except asyncio.TimeoutError:
            return market_radar_holder_cluster_skipped("market_radar_holder_check_timed_out")
        except Exception as exc:
            return market_radar_holder_cluster_skipped(
                "market_radar_holder_check_error: {}".format(str(exc)[:120]),
            )

        rows = ((response or {}).get("result") or {}).get("value") or []
        holder_result = self.holder_analyzer.analyze(rows)
        return {
            "holder_concentration": holder_result,
            "holder_concentration_risk": holder_result.get("risk_label"),
            "holder_concentration_reasons": holder_result.get("warnings") or [],
            "holder_concentration_metrics": holder_result.get("metrics") or {},
        }

    async def quote_route(self, mint, settings):
        if not self.jupiter_quote:
            return None, None, {"pass": False, "reason": "quote_engine_unavailable", "price_impact_pct": None}, {"pass": False, "reason": "quote_engine_unavailable", "price_impact_pct": None}
        max_quotes = safe_int(settings.get("market_radar_max_quotes_per_cycle"), 1)
        quote_cooldown = safe_float(settings.get("market_radar_quote_cooldown_seconds"), 300)
        if max_quotes <= 0 or self.quotes_this_cycle >= max_quotes:
            return None, None, {"pass": False, "reason": "market_radar_quote_budget_exhausted", "price_impact_pct": None}, {"pass": False, "reason": "sell_quote_not_checked_market_radar_quote_budget", "price_impact_pct": None}
        if quote_cooldown > 0 and time.time() - self.last_quote_attempt_at < quote_cooldown:
            return None, None, {"pass": False, "reason": "market_radar_quote_cooldown", "price_impact_pct": None}, {"pass": False, "reason": "sell_quote_not_checked_market_radar_quote_cooldown", "price_impact_pct": None}
        quote_status = (load_status().get("quotes") or {})
        quote_state = str(quote_status.get("status") or quote_status.get("state") or "").lower()
        quote_age = age_seconds(quote_status.get("updated_at"))
        if quote_state in {"http_429", "cooldown_after_429"} and quote_age is not None and quote_age < quote_cooldown:
            return None, None, {"pass": False, "reason": "shared_quote_cooldown_after_429", "price_impact_pct": None}, {"pass": False, "reason": "sell_quote_not_checked_shared_quote_cooldown_after_429", "price_impact_pct": None}
        if hasattr(self.jupiter_quote, "is_cooling_down") and self.jupiter_quote.is_cooling_down():
            return None, None, {"pass": False, "reason": "jupiter_cooldown_after_429", "price_impact_pct": None}, {"pass": False, "reason": "sell_quote_not_checked_jupiter_cooldown_after_429", "price_impact_pct": None}

        self.quotes_this_cycle += 1
        self.last_quote_attempt_at = time.time()

        buy_quote = await self.jupiter_quote.get_buy_quote(
            output_mint=mint,
            sol_amount=0.1,
            slippage_bps=1500,
        )
        buy_analysis = self.jupiter_quote.analyze_quote(buy_quote, max_price_impact_pct=8)
        sell_quote = None
        sell_analysis = {"pass": False, "reason": "sell_quote_not_checked_buy_failed", "price_impact_pct": None}
        if buy_quote and buy_quote.get("ok"):
            amount = safe_int(buy_quote.get("out_amount"), 0)
            if amount > 0:
                sell_quote = await self.jupiter_quote.get_sell_quote(
                    input_mint=mint,
                    token_amount_raw=amount,
                    slippage_bps=2000,
                )
                sell_analysis = self.jupiter_quote.analyze_quote(sell_quote, max_price_impact_pct=10)
        return buy_quote, sell_quote, buy_analysis, sell_analysis

    def record_snapshot(self, payload, context):
        snapshot = dict(payload)
        snapshot.update({
            "source": "market_radar",
            "context": context,
            "time": payload.get("timestamp") or time.time(),
            "price": (payload.get("market_info") or {}).get("price"),
            "liquidity": (payload.get("market_info") or {}).get("liquidity"),
            "market_cap": (payload.get("market_info") or {}).get("market_cap") or (payload.get("market_info") or {}).get("fdv"),
            "decision_stage": "market_radar_evaluation",
        })
        self.store.insert_token_snapshot(snapshot)

    def record_decision(self, payload):
        decision = build_decision_record(payload)
        return self.store.upsert_decision(decision)

    async def process_candidate(self, candidate, settings):
        mint = candidate.get("mint")
        market_info = await self.market_checker.get_token_info(mint)
        score = score_hot_market_candidate(candidate, market_info, settings)

        buy_quote = sell_quote = None
        buy_analysis = {"pass": False, "reason": "quote_not_checked_market_radar_score", "price_impact_pct": None}
        sell_analysis = {"pass": False, "reason": "sell_quote_not_checked_market_radar_score", "price_impact_pct": None}

        score_allowed = bool(score["allowed"])
        if score_allowed:
            hc = await self.evaluate_market_radar_holder_cluster(mint, settings)
        else:
            hc = market_radar_holder_cluster_placeholder()

        holder_danger = hc.get("holder_concentration_risk") == "DANGER"
        should_trade = score_allowed and not holder_danger

        if should_trade:
            buy_quote, sell_quote, buy_analysis, sell_analysis = await self.quote_route(mint, settings)
            if not buy_analysis.get("pass"):
                should_trade = False
            if not sell_analysis.get("pass"):
                should_trade = False
        elif holder_danger:
            buy_analysis = {"pass": False, "reason": "market_radar_holder_concentration_danger", "price_impact_pct": None}
            sell_analysis = {"pass": False, "reason": "sell_quote_not_checked_holder_blocked", "price_impact_pct": None}

        decision = market_radar_decision_summary(score, should_trade, buy_analysis, sell_analysis)
        reasons = market_radar_action_reasons(score, decision)
        if holder_danger:
            hrs = "; ".join(hc.get("holder_concentration_reasons") or [])
            if hrs:
                reasons.append(f"HOLDER BLOCK: {hrs}")
        elif hc.get("holder_concentration_risk") == "WARNING":
            hrs = "; ".join(hc.get("holder_concentration_reasons") or [])
            if hrs:
                reasons.append(f"HOLDER WARN: {hrs}")
        if buy_analysis.get("pass") is False and buy_analysis.get("reason") not in {None, "quote_not_checked_market_radar_score"}:
            reasons.append(f"BUY QUOTE BLOCK: {buy_analysis.get('reason')}")
        if sell_analysis.get("pass") is False and sell_analysis.get("reason") not in {None, "sell_quote_not_checked_market_radar_score"}:
            reasons.append(f"EXIT LIQUIDITY BLOCK: {sell_analysis.get('reason')}")

        risk_warnings = list(score.get("blockers") or [])
        label = hc.get("holder_concentration_risk")
        if label in {"WARNING", "DANGER"}:
            hrs = "; ".join(hc.get("holder_concentration_reasons") or [])
            if hrs:
                risk_warnings.append(f"Holder {label}: {hrs}")

        payload = {
            "mint": mint,
            "type": "market_radar_hot",
            "signal_type": "market_radar_hot",
            "wallets": [],
            "wallet_count": 0,
            "weighted_wallet_score": 0,
            "market_info": market_info,
            "total_score": score["score"],
            "score_threshold": score["threshold"],
            "threshold": score["threshold"],
            "mode": "MARKET_RADAR",
            "should_trade": should_trade,
            "paper_lane": "market_radar",
            "position_size_usd": score["position_size_usd"] if should_trade else 0,
            "risk_label": "MARKET_RADAR_PRECHECK",
            "risk_score": 0,
            "risk_warnings": risk_warnings,
            "hard_block": holder_danger,
            "hard_block_reason": "; ".join(hc.get("holder_concentration_reasons") or []) if holder_danger else None,
            "buy_quote_pass": buy_analysis.get("pass"),
            "buy_quote_reason": buy_analysis.get("reason"),
            "buy_quote_price_impact_pct": buy_analysis.get("price_impact_pct"),
            "buy_quote": buy_quote,
            "buy_quote_slippage_bps": 1500,
            "buy_quote_max_price_impact_pct": 8,
            "sell_quote_pass": sell_analysis.get("pass"),
            "sell_quote_reason": sell_analysis.get("reason"),
            "sell_quote_price_impact_pct": sell_analysis.get("price_impact_pct"),
            "sell_quote": sell_quote,
            "sell_quote_slippage_bps": 2000,
            "sell_quote_max_price_impact_pct": 10,
            "score_reasons": reasons,
            "edge_score": score["score"],
            "edge_verdict": "HOT_MARKET_RADAR" if should_trade else ("MARKET_RADAR_ROUTE_SKIP" if score["allowed"] else "MARKET_RADAR_SKIP"),
            "edge_quote_worthy": score["allowed"],
            "edge_paper_trade_worthy": should_trade,
            "edge_positives": score["reasons"],
            "edge_risks": score["blockers"] + ([decision["skip_reason"]] if decision.get("skip_reason") and decision.get("skip_reason") not in score["blockers"] else []),
            "market_radar": {
                "candidate": candidate,
                "score": score,
                "decision": decision,
                "sources": candidate.get("sources") or [],
            },
            "timestamp": time.time(),
        }
        payload.update(hc)
        payload["linked_wallet_risk"] = market_radar_linked_wallet_placeholder(
            wallet_count=payload["wallet_count"],
            wallets=payload.get("wallets"),
        )

        decision_id = self.record_decision(payload)
        payload["decision_id"] = decision_id
        self.record_snapshot(payload, "market_radar_entry_candidate" if should_trade else "market_radar_skip")
        if decision.get("quote_retryable"):
            self.defer_candidate(mint, min(safe_float(settings.get("market_radar_quote_cooldown_seconds"), 300), 300))
        else:
            self.mark_seen(mint)

        result = {
            "opened": False,
            "decision_id": decision_id,
            "score": score,
            "skip_reason": decision.get("skip_reason"),
            "skip_bucket": decision.get("skip_bucket"),
            "open_reason": decision.get("open_reason"),
            "retry_soon": bool(decision.get("quote_retryable")),
        }

        if not should_trade:
            try:
                from analysis.rejection_hooks import maybe_log_market_radar_skip

                maybe_log_market_radar_skip(payload, decision, decision_id, settings)
            except Exception:
                pass
            return result

        if not self.paper_trader:
            self.store.update_decision_action(decision_id, {
                "scanner_stage": "market_radar_precheck",
                "final_action": "runtime_skip",
                "reason": "no_paper_trader",
                "paper_lane": "market_radar",
                "position_size_usd": 0,
            })
            result.update({"skip_reason": "no_paper_trader", "skip_bucket": "runtime_precheck"})
            try:
                from analysis.rejection_hooks import maybe_log_market_radar_runtime_skip

                maybe_log_market_radar_runtime_skip(payload, decision_id, "no_paper_trader", settings)
            except Exception:
                pass
            return result

        if self.has_existing_trade(mint):
            self.store.update_decision_action(decision_id, {
                "scanner_stage": "market_radar_precheck",
                "final_action": "duplicate_open",
                "reason": "existing_trade_for_mint",
                "paper_lane": "market_radar",
                "position_size_usd": 0,
            })
            result.update({"skip_reason": "existing_trade_for_mint", "skip_bucket": "runtime_precheck"})
            try:
                from analysis.rejection_hooks import maybe_log_market_radar_runtime_skip

                maybe_log_market_radar_runtime_skip(
                    payload, decision_id, "existing_trade_for_mint", settings
                )
            except Exception:
                pass
            return result

        liquidity = safe_float((market_info or {}).get("liquidity"), 0)
        price = safe_float((market_info or {}).get("price"), 0)
        if price <= 0 or liquidity <= 0:
            self.store.update_decision_action(decision_id, {
                "scanner_stage": "market_radar_precheck",
                "final_action": "runtime_skip",
                "reason": "missing_market_price_or_liquidity",
                "paper_lane": "market_radar",
                "position_size_usd": 0,
            })
            result.update({"skip_reason": "missing_market_price_or_liquidity", "skip_bucket": "runtime_precheck"})
            try:
                from analysis.rejection_hooks import maybe_log_market_radar_runtime_skip

                maybe_log_market_radar_runtime_skip(
                    payload, decision_id, "missing_market_price_or_liquidity", settings
                )
            except Exception:
                pass
            return result

        trade = self.paper_trader.open_trade(
            mint=mint,
            entry_price=price,
            size_usd=score["position_size_usd"],
            liquidity_usd=liquidity,
            reason=f"market_radar_hot_score_{score['score']}",
            wallets=[],
            market_info=market_info,
            paper_lane="market_radar",
            exploration=False,
            signal_metadata={
                "decision_id": decision_id,
                "signal_type": "market_radar_hot",
                "paper_lane": "market_radar",
                "market_radar": payload["market_radar"],
                "score": score["score"],
                "threshold": score["threshold"],
                "buy_quote_analysis": buy_analysis,
                "sell_quote_analysis": sell_analysis,
                "score_reasons": reasons,
            },
        )
        result["opened"] = bool(trade)
        return result

    async def process_once(self):
        settings = self.settings_loader()
        if not safe_bool(settings.get("market_radar_enabled"), True):
            update_component("market_radar", status="disabled")
            return {"candidates": 0, "opened": 0}

        candidates = await self.fetch_candidates()
        limit = safe_int(settings.get("market_radar_max_candidates_per_cycle"), 8)
        scan_limit = safe_int(settings.get("market_radar_scan_candidates_per_cycle"), max(limit * 5, limit))
        scan_limit = max(limit, scan_limit)
        max_entries = safe_int(settings.get("market_radar_max_entries_per_cycle"), 1)
        cooldown = safe_float(settings.get("market_radar_mint_cooldown_seconds"), 6 * 3600)

        opened = 0
        processed = 0
        scanned = 0
        skipped_recent = 0
        skipped_missing_mint = 0
        skip_reasons = {}
        skip_buckets = {}
        self.quotes_this_cycle = 0
        self.holder_checks_this_cycle = 0
        for candidate in candidates[:scan_limit]:
            scanned += 1
            mint = candidate.get("mint")
            if not mint:
                skipped_missing_mint += 1
                continue
            if self.recently_seen(mint, cooldown):
                skipped_recent += 1
                continue
            if processed >= limit:
                break
            result = await self.process_candidate(candidate, settings)
            processed += 1
            if result.get("opened"):
                opened += 1
                if opened >= max_entries:
                    break
            elif result.get("skip_reason"):
                increment_counter(skip_reasons, result.get("skip_reason"))
                increment_counter(skip_buckets, result.get("skip_bucket"))

        update_component(
            "market_radar",
            status="cycle_ok",
            candidates=len(candidates),
            scanned=scanned,
            processed=processed,
            opened=opened,
            skipped_recent=skipped_recent,
            skipped_missing_mint=skipped_missing_mint,
            skip_reasons=skip_reasons,
            skip_buckets=skip_buckets,
            quotes_this_cycle=self.quotes_this_cycle,
            live_execution_locked=True,
        )
        return {
            "candidates": len(candidates),
            "scanned": scanned,
            "processed": processed,
            "opened": opened,
            "skipped_recent": skipped_recent,
            "skipped_missing_mint": skipped_missing_mint,
            "skip_reasons": skip_reasons,
            "skip_buckets": skip_buckets,
        }


async def run_market_radar_loop(market_checker, paper_trader, jupiter_quote=None, interval=120, rpc=None):
    radar = MarketRadar(
        market_checker=market_checker,
        paper_trader=paper_trader,
        jupiter_quote=jupiter_quote,
        rpc=rpc,
    )
    update_component("market_radar", status="starting", heartbeat_interval=interval, live_execution_locked=True)
    while True:
        try:
            await radar.process_once()
            update_component("market_radar", heartbeat_interval=interval)
        except Exception as exc:
            update_component("market_radar", status="cycle_error", heartbeat_interval=interval, last_error=str(exc)[:180])
        await asyncio.sleep(interval)
