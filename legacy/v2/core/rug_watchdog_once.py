from core.rug_watchdog import run_once


if __name__ == "__main__":
    watchlist = run_once()
    print(f"Checked {len(watchlist)} protected token(s)")
