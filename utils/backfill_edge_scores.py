import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.edge_analyzer import EdgeAnalyzer


LIVE_STATE_FILE = Path("live_state.json")


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def backfill_alert(alert, analyzer):
    market_info = alert.get("market_info") or {}
    edge = analyzer.analyze(
        wallet_count=alert.get("wallet_count", 0),
        weighted_wallet_score=alert.get("weighted_wallet_score", 0),
        repeated_buys=0,
        wallet_quality=alert.get("wallet_quality") or {},
        wallet_performance=alert.get("wallet_performance") or {},
        liquidity_usd=market_info.get("liquidity", 0),
        volume_usd=market_info.get("volume", 0),
        true_launch_age_seconds=alert.get("true_launch_age_seconds"),
        token_age_seconds=alert.get("token_age_seconds"),
        social_match=alert.get("social_match") or {},
        rug_result={
            "risk_score": alert.get("risk_score", 0),
            "risk_label": alert.get("risk_label", "UNKNOWN"),
            "hard_block": alert.get("hard_block", False),
        },
        decision_score=alert.get("total_score", 0),
    )

    alert["edge_score"] = edge.get("edge_score")
    alert["edge_verdict"] = edge.get("edge_verdict")
    alert["edge_quote_worthy"] = edge.get("quote_worthy")
    alert["edge_paper_trade_worthy"] = edge.get("paper_trade_worthy")
    alert["edge_positives"] = edge.get("positives", [])
    alert["edge_risks"] = edge.get("risks", [])

    return alert


def main():
    state = load_json(LIVE_STATE_FILE, {})
    analyzer = EdgeAnalyzer()

    alerts = state.get("alerts", [])
    for alert in alerts:
        backfill_alert(alert, analyzer)

    latest_tokens = state.get("latest_tokens", {})
    for token in latest_tokens.values():
        if isinstance(token, dict):
            backfill_alert(token, analyzer)

    tokens = state.get("tokens", {})
    for token in tokens.values():
        if isinstance(token, dict):
            backfill_alert(token, analyzer)

    save_json(LIVE_STATE_FILE, state)
    print(f"Backfilled edge scores for {len(alerts)} alerts")


if __name__ == "__main__":
    main()
