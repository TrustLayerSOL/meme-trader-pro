import time


class TokenLaunchAgeTracker:
    def __init__(self, rpc):
        self.rpc = rpc
        self.cache = {}

    async def get_launch_info(self, mint):
        if mint in self.cache:
            return self.cache[mint]

        info = {
            "mint": mint,
            "launch_time": None,
            "launch_age_seconds": None,
            "source": "unknown",
        }

        try:
            sigs = await self.rpc.rpc_call(
                "getSignaturesForAddress",
                [mint, {"limit": 1000}]
            )

            if not sigs or not sigs.get("result"):
                self.cache[mint] = info
                return info

            results = sigs["result"]

            oldest = results[-1]
            block_time = oldest.get("blockTime")

            if block_time:
                age = time.time() - float(block_time)

                info = {
                    "mint": mint,
                    "launch_time": block_time,
                    "launch_age_seconds": age,
                    "source": "oldest_mint_signature",
                    "oldest_signature": oldest.get("signature"),
                }

            self.cache[mint] = info
            return info

        except Exception as e:
            print("⚠️ Token launch age lookup failed:", e)
            self.cache[mint] = info
            return info