import json


class WalletTracker:
    def __init__(self, file_path="tracked_wallets.json"):
        self.wallets = {}
        self.load_wallets(file_path)

    def load_wallets(self, file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)

                for entry in data:
                    address = entry.get("trackedWalletAddress")
                    name = entry.get("name")
                    groups = entry.get("groups", [])

                    # ✅ Only track "Main" group
                    if "Main" in groups and address:
                        self.wallets[address] = name

            print(f"✅ Loaded {len(self.wallets)} tracked wallets")

        except Exception as e:
            print("❌ Failed to load wallets:", e)

    def check_wallets_in_tx(self, tx):
        try:
            if not tx:
                return []

            result = tx.get("result")
            if not result or not isinstance(result, dict):
                return []

            accounts = result.get("transaction", {}).get("message", {}).get("accountKeys", [])

            found = []

            for acc in accounts:
                if isinstance(acc, dict):
                    acc = acc.get("pubkey")

                if acc in self.wallets:
                    found.append({
                        "address": acc,
                        "name": self.wallets[acc]
                    })

            return found

        except Exception as e:
            print("❌ Wallet check error:", e)
            return []