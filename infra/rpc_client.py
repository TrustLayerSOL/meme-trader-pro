import asyncio
import json
import os
import aiohttp
import websockets

from dotenv import load_dotenv
from core.scanner import Scanner
from core.runtime_status import increment_component, update_component

load_dotenv()

API_KEY = os.getenv("HELIUS_API_KEY")

if not API_KEY:
    raise ValueError("❌ HELIUS_API_KEY not found in .env")

HELIUS_WS = f"wss://mainnet.helius-rpc.com/?api-key={API_KEY}"
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"


class SolanaRPC:
    def __init__(self, tracked_wallets):
        self.tracked_wallets = tracked_wallets
        self.scanner = Scanner(tracked_wallets, self)
        self.session = None
        self.market_checker = None
        self.jupiter_quote = None

        self.event_semaphore = asyncio.Semaphore(25)
        self.active_tasks = set()

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
            async with self.session.post(RPC_URL, json=payload) as resp:
                update_component(
                    "websocket",
                    last_rpc_method=method,
                    last_rpc_status=resp.status,
                )
                return await resp.json()
        except Exception as e:
            print("⚠️ RPC error:", e)
            update_component(
                "websocket",
                last_rpc_method=method,
                last_rpc_error=str(e),
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
        sub_id = 1
        total = len(self.tracked_wallets)

        for wallet in self.tracked_wallets:
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

            # Read subscription response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5)

                if sub_id <= 3:
                    print("SUB RESPONSE:", response)

            except Exception as e:
                print(f"⚠️ Subscription response timeout at {sub_id}:", e)

            if sub_id % 100 == 0:
                print(f"✅ Subscribed {sub_id}/{total} wallets")
                update_component(
                    "websocket",
                    status="subscribing",
                    subscribed_wallets=sub_id,
                    tracked_wallets=total,
                )

            sub_id += 1

        print(f"✅ Subscribed to {total} tracked wallets")
        update_component(
            "websocket",
            status="subscribed",
            subscribed_wallets=total,
            tracked_wallets=total,
        )

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
                    HELIUS_WS,
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
                    await self.listen(websocket)

            except websockets.exceptions.ConnectionClosed as e:
                print("⚠️ WS closed, reconnecting:", e)
                increment_component(
                    "websocket",
                    "reconnects",
                    status="reconnecting",
                    last_error=str(e),
                )
                await asyncio.sleep(reconnect_delay)

            except Exception as e:
                print("❌ WS error, reconnecting:", e)
                increment_component(
                    "websocket",
                    "reconnects",
                    status="error_reconnecting",
                    last_error=str(e),
                )
                await asyncio.sleep(reconnect_delay)
