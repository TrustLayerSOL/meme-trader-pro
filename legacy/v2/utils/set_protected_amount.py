import argparse
from pathlib import Path

from core.json_store import locked_update_json
from core.protection_amounts import apply_manual_amount_to_watchlist


WATCHLIST_FILE = Path("data/manual_watchlist.json")


def set_protected_amount(mint, wallet="", token_amount=None, token_decimals=None, token_amount_raw=None, test_amount=False):
    result = {"updated": False}

    def updater(rows):
        updated_rows = apply_manual_amount_to_watchlist(
            rows,
            mint=mint,
            wallet=wallet,
            token_amount=token_amount,
            token_decimals=token_decimals,
            token_amount_raw=token_amount_raw,
            test_amount=test_amount,
        )
        result["updated"] = True
        return updated_rows

    locked_update_json(WATCHLIST_FILE, [], updater)
    return result


def main():
    parser = argparse.ArgumentParser(description="Set token amount for a protected manual position.")
    parser.add_argument("--mint", required=True, help="Protected token mint.")
    parser.add_argument("--wallet", default="", help="Wallet recorded on the protected position, if any.")
    parser.add_argument("--amount", default=None, help="Decimal token amount, for example 12.5.")
    parser.add_argument("--decimals", default=None, help="Token decimals required when --amount is used.")
    parser.add_argument("--raw", default=None, help="Raw token amount. Overrides decimal conversion.")
    parser.add_argument("--test", action="store_true", help="Mark this as a simulated/test amount, not an owned wallet balance.")
    args = parser.parse_args()

    result = set_protected_amount(
        mint=args.mint.strip(),
        wallet=args.wallet.strip(),
        token_amount=args.amount,
        token_decimals=args.decimals,
        token_amount_raw=args.raw,
        test_amount=args.test,
    )
    prefix = "Updated test protected amount" if args.test else "Updated protected amount"
    print(prefix if result.get("updated") else "No update applied")


if __name__ == "__main__":
    main()
