import os

from core.env_loader import load_env


load_env()


# ================= API KEY =================

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")


# ================= RPC CONFIG =================

RPC_URL = f"https://beta.helius-rpc.com/?api-key={HELIUS_API_KEY}"
RPC_FALLBACK = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
WS_URL = f"wss://beta.helius-rpc.com/?api-key={HELIUS_API_KEY}"


# ================= ENHANCED APIs =================

PARSE_TX_URL = f"https://api-mainnet.helius-rpc.com/v0/transactions/?api-key={HELIUS_API_KEY}"
PARSE_ADDRESS_URL = f"https://api-mainnet.helius-rpc.com/v0/addresses/{{address}}/transactions/?api-key={HELIUS_API_KEY}"


# ================= MODE =================

MODE = "SNIPER"


# ================= STRATEGY =================

SAFE = {
    "min_liquidity": 15000,
    "min_buys": 15,
    "buy_sell_ratio": 1.5,
    "min_volume": 8000,
    "max_liq_to_vol_ratio": 10
}

SNIPER = {
    "min_liquidity": 3000,
    "min_buys": 3,
    "buy_sell_ratio": 1.1,
    "min_volume": 1000,
    "max_liq_to_vol_ratio": 25
}


# ================= TRADING =================

INITIAL_PORTFOLIO = 1000
RISK_PER_TRADE = 0.05

TAKE_PROFIT_1 = 3
TAKE_PROFIT_2 = 10
TRAILING_STOP = 0.30


# ================= FILTERS =================

MIN_HOLDERS = 20
MAX_DEV_WALLET_PERCENT = 20
CHECK_FAKE_LIQUIDITY = True


# ================= SCAN =================

SCAN_INTERVAL = 2


# ================= DEBUG =================

DEBUG = True
