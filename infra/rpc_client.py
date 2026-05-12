import asyncio
import json
import os
import time
import aiohttp
import websockets

from dotenv import load_dotenv
from core.redaction import redact_secrets
from core.scanner import Scanner
from core.runtime_status import increment_component, update_component

load_dotenv()

API_KEY = os.getenv("HELIUS_API_KEY")

HELIUS_WS = f"wss://mainnet.helius-rpc.com/?api-key={API_KEY}" if API_KEY else None
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}" if API_KEY else None


def require_helius_url(kind):
    api_key = os.getenv("HELIUS_API_KEY") or API_KEY
    if not api_key:
        raise ValueError("❌ HELIUS_API_KEY not found in .env")
    if kind == "ws":
        return f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
    return f"https://mainnet.helius-rpc.com/?api-key={api_key}"


def env_float(name, default, minimum=None):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None:
        return max(float(minimum), value)
    return value


def env_int(name, default, minimum=None):
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        return max(int(minimum), value)
    return value


class SolanaRPC:
    def __init__(self, tracked_wallets, paper_watch_wallets=None, paper_watch_loader=None):
        self.tracked_wallets = tracked_wallets
        self.paper_watch_wallets = paper_watch_wallets or []
        self.observed_wallets = list(dict.fromkeys(list(tracked_wallets) + list(self.paper_watch_wallets)))
        self.subscribed_wallets = set()
        self.next_sub_id = 1
        self.pending_subscription_wallets = {}
        self.subscription_wallets = {}
        self.paper_watch_loader = paper_watch_loader
        self.scanner = Scanner(tracked_wallets, self, paper_watch_wallets=self.paper_watch_wallets)
        self.session = None
        self.market_checker = None
        self.jupiter_quote = None

        self.event_semaphore = asyncio.Semaphore(25)
        self.max_event_backlog = env_int("MEMETRADER_MAX_EVENT_BACKLOG", 2500, minimum=100)
        self.max_inflight_per_wallet = env_int("MEMETRADER_MAX_INFLIGHT_PER_WALLET", 40, minimum=1)
        self.active_tasks = set()
        self.active_tasks_by_wallet = {}
        self.transaction_cache = {}
        self.transaction_cache_ttl = env_float("MEMETRADER_TRANSACTION_CACHE_TTL_SECONDS", 300, minimum=0)
        self.transaction_cache_max = env_int("MEMETRADER_TRANSACTION_CACHE_MAX", 10000, minimum=100)
        max_rps = env_float("MEMETRADER_GET_TRANSACTION_MAX_RPS", 8, minimum=0)
        self.transaction_min_interval = (1 / max_rps) if max_rps > 0 else 0
        self.transaction_rate_lock = asyncio.Lock()
        self.next_transaction_at = 0
        self.transaction_locks = {}
        update_component(
            "scanner",
            status="initialized",
            tracked_wallets=len(self.tracked_wallets),
            paper_watch_wallets=len(self.paper_watch_wallets),
            observed_wallets=len(self.observed_wallets),
        )

    async def init_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=12)
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def rpc_call(self, method, params):
        await self.init_session()

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        try:
            async with self.session.post(require_helius_url("rpc"), json=payload) as resp:
                update_component(
                    "websocket",
                    last_rpc_method=method,
                    last_rpc_status=resp.status,
                )
                return await resp.json()
        except Exception as e:
            error = redact_secrets(e)
            print("⚠️ RPC error:", error)
            update_component(
                "websocket",
                last_rpc_method=method,
                last_rpc_error=error,
            )
            return None

    def cached_transaction(self, signature):
        item = self.transaction_cache.get(signature)
        if not item:
            return None
        age = time.time() - item["time"]
        if age <= self.transaction_cache_ttl:
            return item["data"]
        self.transaction_cache.pop(signature, None)
        return None

    def store_transaction_cache(self, signature, data):
        if self.transaction_cache_ttl <= 0:
            return
        self.transaction_cache[signature] = {
            "time": time.time(),
            "data": data,
        }
        if len(self.transaction_cache) <= self.transaction_cache_max:
            return
        overflow = len(self.transaction_cache) - self.transaction_cache_max
        for key, _item in sorted(self.transaction_cache.items(), key=lambda row: row[1]["time"])[:overflow]:
            self.transaction_cache.pop(key, None)

    async def wait_for_transaction_budget(self):
        if self.transaction_min_interval <= 0:
            return
        loop = asyncio.get_running_loop()
        async with self.transaction_rate_lock:
            now = loop.time()
            wait_seconds = self.next_transaction_at - now
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = loop.time()
            self.next_transaction_at = max(now, self.next_transaction_at) + self.transaction_min_interval

    async def get_transaction(self, signature):
        cached = self.cached_transaction(signature)
        if cached is not None:
            increment_component(
                "websocket",
                "transaction_cache_hits",
                last_transaction_signature=signature,
            )
            return cached

        lock = self.transaction_locks.setdefault(signature, asyncio.Lock())
        async with lock:
            cached = self.cached_transaction(signature)
            if cached is not None:
                increment_component(
                    "websocket",
                    "transaction_cache_hits",
                    last_transaction_signature=signature,
                )
                return cached

            await self.wait_for_transaction_budget()
            result = await self.rpc_call(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                        "commitment": "confirmed",
                    },
                ],
            )
            self.store_transaction_cache(signature, result)
            increment_component(
                "websocket",
                "transaction_rpc_fetches",
                transaction_cache_size=len(self.transaction_cache),
                transaction_min_interval=round(self.transaction_min_interval, 4),
                last_transaction_signature=signature,
            )
            return result

    def should_drop_for_backlog(self):
        return len(self.active_tasks) >= self.max_event_backlog

    def should_drop_for_wallet(self, wallet):
        if not wallet:
            return False
        return int(self.active_tasks_by_wallet.get(wallet, 0) or 0) >= self.max_inflight_per_wallet

    def transaction_lock_count(self):
        return len(self.transaction_locks)

    def prune_transaction_locks(self):
        if len(self.transaction_locks) <= self.transaction_cache_max:
            return
        for signature in list(self.transaction_locks)[: len(self.transaction_locks) - self.transaction_cache_max]:
            lock = self.transaction_locks.get(signature)
            if lock and lock.locked():
                continue
            self.transaction_locks.pop(signature, None)

    def handle_subscription_ack(self, message):
        try:
            data = json.loads(message)
        except Exception:
            return False
        if not isinstance(data, dict) or "id" not in data or "result" not in data:
            return False
        wallet = self.pending_subscription_wallets.pop(data.get("id"), None)
        if not wallet:
            return False
        self.subscription_wallets[data.get("result")] = wallet
        update_component(
            "websocket",
            status="subscription_ack",
            subscribed_wallets=len(self.subscribed_wallets),
            mapped_subscriptions=len(self.subscription_wallets),
        )
        return True

    def wallet_for_message(self, message):
        try:
            data = json.loads(message)
        except Exception:
            return None
        params = data.get("params") if isinstance(data, dict) else {}
        subscription_id = params.get("subscription") if isinstance(params, dict) else None
        return self.subscription_wallets.get(subscription_id)

    async def enqueue_or_drop_message(self, message):
        if self.handle_subscription_ack(message):
            return None
        wallet = self.wallet_for_message(message)
        if self.should_drop_for_wallet(wallet):
            increment_component(
                "websocket",
                "messages_dropped_wallet_backlog",
                status="wallet_backlog_drop",
                wallet=wallet,
                wallet_active_tasks=int(self.active_tasks_by_wallet.get(wallet, 0) or 0),
                max_inflight_per_wallet=self.max_inflight_per_wallet,
                active_tasks=len(self.active_tasks),
                max_event_backlog=self.max_event_backlog,
            )
            return None
        if self.should_drop_for_backlog():
            increment_component(
                "websocket",
                "messages_dropped_backlog",
                status="backlog_drop",
                active_tasks=len(self.active_tasks),
                max_event_backlog=self.max_event_backlog,
            )
            return None
        task = asyncio.create_task(self.handle_message_fast(message))
        self.track_task(task, wallet=wallet)
        return task

    def runtime_pressure_fields(self):
        return dict(
            active_tasks=len(self.active_tasks),
            wallet_backpressure_wallets=len(self.active_tasks_by_wallet),
            max_inflight_per_wallet=self.max_inflight_per_wallet,
            transaction_cache_size=len(self.transaction_cache),
            transaction_lock_count=self.transaction_lock_count(),
            transaction_min_interval=round(self.transaction_min_interval, 4),
            max_event_backlog=self.max_event_backlog,
        )

    async def subscribe_wallets(self, websocket):
        total = len(self.observed_wallets)

        for wallet in self.observed_wallets:
            await self.subscribe_wallet(websocket, wallet, wait_for_response=True)

        print(f"✅ Subscribed to {total} tracked wallets")
        update_component(
            "websocket",
            status="subscribed",
            subscribed_wallets=len(self.subscribed_wallets),
            tracked_wallets=len(self.tracked_wallets),
            paper_watch_wallets=len(self.paper_watch_wallets),
            observed_wallets=len(self.observed_wallets),
        )

    async def subscribe_wallet(self, websocket, wallet, wait_for_response=False):
        if wallet in self.subscribed_wallets:
            return False

        sub_id = self.next_sub_id
        self.next_sub_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": sub_id,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [wallet]},
                {"commitment": "confirmed"},
            ],
        }

        await websocket.send(json.dumps(msg))
        self.subscribed_wallets.add(wallet)
        self.pending_subscription_wallets[sub_id] = wallet

        if wait_for_response:
            # Initial subscription happens before the listener starts, so it is
            # safe to consume acknowledgements here. Runtime reload subscriptions
            # do not consume from the shared websocket.
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                self.handle_subscription_ack(response)

                if sub_id <= 3:
                    print("SUB RESPONSE:", response)

            except Exception as e:
                print(f"⚠️ Subscription response timeout at {sub_id}:", redact_secrets(e))

        if sub_id % 100 == 0:
            print(f"✅ Subscribed {sub_id}/{len(self.observed_wallets)} wallets")
            update_component(
                "websocket",
                status="subscribing",
                subscribed_wallets=len(self.subscribed_wallets),
                tracked_wallets=len(self.tracked_wallets),
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
            )

        return True

    async def subscribe_new_paper_watch_wallets(self, websocket, wallets):
        added = self.scanner.add_paper_watch_wallets(wallets)
        subscribed = []
        for wallet in added:
            if wallet not in self.paper_watch_wallets:
                self.paper_watch_wallets.append(wallet)
            if wallet not in self.observed_wallets:
                self.observed_wallets.append(wallet)
            did_subscribe = await self.subscribe_wallet(websocket, wallet, wait_for_response=False)
            if did_subscribe:
                subscribed.append(wallet)
        if subscribed:
            update_component(
                "websocket",
                status="paper_watch_reloaded",
                subscribed_wallets=len(self.subscribed_wallets),
                tracked_wallets=len(self.tracked_wallets),
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
                added_paper_watch_wallets=len(subscribed),
            )
        return subscribed

    async def paper_watch_reload_loop(self, websocket, loader, interval=60):
        while True:
            try:
                wallets = loader()
                await self.subscribe_new_paper_watch_wallets(websocket, wallets)
            except Exception as exc:
                update_component(
                    "websocket",
                    status="paper_watch_reload_error",
                    last_error=redact_secrets(exc),
                    heartbeat_interval=interval,
                )
            await asyncio.sleep(interval)

    async def handle_message_fast(self, message):
        async with self.event_semaphore:
            increment_component(
                "websocket",
                "messages_received",
                active_tasks=len(self.active_tasks),
            )
            await self.scanner.handle_event(message)

    def track_task(self, task, wallet=None):
        self.active_tasks.add(task)
        if wallet:
            self.active_tasks_by_wallet[wallet] = int(self.active_tasks_by_wallet.get(wallet, 0) or 0) + 1

        def cleanup(done_task):
            self.active_tasks.discard(done_task)
            if wallet:
                remaining = int(self.active_tasks_by_wallet.get(wallet, 0) or 0) - 1
                if remaining > 0:
                    self.active_tasks_by_wallet[wallet] = remaining
                else:
                    self.active_tasks_by_wallet.pop(wallet, None)

        task.add_done_callback(cleanup)

    async def scanner_heartbeat(self, interval=30):
        while True:
            update_component(
                "scanner",
                status="listening",
                last_error=None,
                tracked_wallets=len(self.tracked_wallets),
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
                seen_signatures=len(self.scanner.seen_signatures),
                seen_signals=len(self.scanner.seen_signals),
                heartbeat_interval=interval,
                **self.runtime_pressure_fields(),
            )
            update_component(
                "websocket",
                status="subscribed" if self.subscribed_wallets else "listening",
                subscribed_wallets=len(self.subscribed_wallets),
                tracked_wallets=len(self.tracked_wallets),
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
                **self.runtime_pressure_fields(),
            )
            self.prune_transaction_locks()
            await asyncio.sleep(interval)

    async def listen(self, websocket):
        while True:
            message = await websocket.recv()
            await self.enqueue_or_drop_message(message)

    async def connect(self):
        reconnect_delay = 1

        while True:
            try:
                print("🔌 Connecting to Helius WebSocket...")
                update_component(
                    "websocket",
                    status="connecting",
                    tracked_wallets=len(self.tracked_wallets),
                )

                async with websockets.connect(
                    require_helius_url("ws"),
                    ping_interval=30,
                    ping_timeout=30,
                    close_timeout=5,
                    max_queue=4096,
                ) as websocket:
                    print("✅ Connected to Helius")
                    update_component(
                        "websocket",
                        status="connected",
                        last_error=None,
                        tracked_wallets=len(self.tracked_wallets),
                    )
                    await self.subscribe_wallets(websocket)
                    tasks = [
                        self.listen(websocket),
                        self.scanner_heartbeat(),
                    ]
                    if self.paper_watch_loader:
                        tasks.append(self.paper_watch_reload_loop(websocket, self.paper_watch_loader))
                    await asyncio.gather(*tasks)

            except websockets.exceptions.ConnectionClosed as e:
                error = redact_secrets(e)
                print("⚠️ WS closed, reconnecting:", error)
                increment_component(
                    "websocket",
                    "reconnects",
                    status="reconnecting",
                    last_error=error,
                )
                await asyncio.sleep(reconnect_delay)

            except Exception as e:
                error = redact_secrets(e)
                print("❌ WS error, reconnecting:", error)
                increment_component(
                    "websocket",
                    "reconnects",
                    status="error_reconnecting",
                    last_error=error,
                )
                await asyncio.sleep(reconnect_delay)
