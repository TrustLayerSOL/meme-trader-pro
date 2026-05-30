import aiohttp
import json
from config import RPC_URL

class TransactionFetcher:
    def __init__(self):
        self.url = RPC_URL

    async def get_transaction(self, signature):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, json=payload) as resp:
                data = await resp.json()
                return data