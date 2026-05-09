import asyncio
import json
import os
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


class SolanaRPC:
    def __init__(self, tracked_wallets, paper_watch_wallets=None, paper_watch_loader=None):
        self.tracked_wallets = tracked_wallets
        self.paper_watch_wallets = paper_watch_wallets or []
        self.observed_wallets = list(dict.fromkeys(list(tracked_wallets) + list(self.paper_watch_wallets)))
        self.subscribed_wallets = set()
        self.next_sub_id = 1
        self.paper_watch_loader = paper_watch_loader
        self.scanner = Scanner(tracked_wallets, self, paper_watch_wallets=self.paper_watch_wallets)
        self.session = None
        self.market_checker = None
        self.jupiter_quote = None

        self.event_semaphore = asyncio.Semaphore(25)
        self.active_tasks = set()
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

    async def get_transaction(self, signature):
        return await self.rpc_call(
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

        if wait_for_response:
            # Initial subscription happens before the listener starts, so it is
            # safe to consume acknowledgements here. Runtime reload subscriptions
            # do not consume from the shared websocket.
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)

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

    def track_task(self, task):
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    async def scanner_heartbeat(self, interval=30):
        while True:
            update_component(
                "scanner",
                status="listening",
                tracked_wallets=len(self.tracked_wallets),
                paper_watch_wallets=len(self.paper_watch_wallets),
                observed_wallets=len(self.observed_wallets),
                active_tasks=len(self.active_tasks),
                seen_signatures=len(self.scanner.seen_signatures),
                seen_signals=len(self.scanner.seen_signals),
                heartbeat_interval=interval,
            )
            await asyncio.sleep(interval)

    async def listen(self, websocket):
        while True:
            message = await websocket.recv()
            task = asyncio.create_task(self.handle_message_fast(message))
            self.track_task(task)

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
