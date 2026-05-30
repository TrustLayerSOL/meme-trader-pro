from __future__ import annotations

from typing import Any

from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    as_list,
    bullet_list,
    compact_number,
    first_present,
    iso_from_ts,
    short_id,
    slugify,
    table,
    wikilink,
    yaml_frontmatter,
)
from obsidian_export.wallet_note import wallet_stem


def signal_stem(row: dict[str, Any]) -> str:
    decision_id = row.get("decision_id")
    if decision_id:
        return f"SIG-{slugify(decision_id)}"
    mint = row.get("mint") or row.get("token_mint") or "unknown"
    ts = row.get("captured_at") or row.get("time") or row.get("timestamp") or row.get("recorded_at") or "unknown"
    return f"SIG-{slugify(ts)}-{short_id(mint)}"


def signal_filename(row: dict[str, Any]) -> str:
    return f"{signal_stem(row)}.md"


def rejected_signal_stem(row: dict[str, Any]) -> str:
    decision_id = row.get("decision_id")
    if decision_id:
        return f"REJECT-{slugify(decision_id)}"
    mint = row.get("mint") or as_dict(row.get("signal context")).get("mint") or "unknown"
    ts = row.get("recorded_at") or "unknown"
    return f"REJECT-{slugify(ts)}-{short_id(mint)}"


def rejected_signal_filename(row: dict[str, Any]) -> str:
    return f"{rejected_signal_stem(row)}.md"


def paper_trade_stem(row: dict[str, Any]) -> str:
    decision_id = row.get("decision_id") or as_dict(row.get("signal_metadata")).get("decision_id")
    if decision_id:
        return f"TRADE-{slugify(decision_id)}"
    mint = row.get("token_mint") or row.get("mint") or "unknown"
    ts = row.get("entry_time") or row.get("time") or row.get("close_time") or "unknown"
    return f"TRADE-{slugify(ts)}-{short_id(mint)}"


def paper_trade_filename(row: dict[str, Any]) -> str:
    return f"{paper_trade_stem(row)}.md"


def postmortem_stem(row: dict[str, Any]) -> str:
    pid = row.get("postmortem_id") or row.get("trade_fingerprint")
    if pid:
        return f"PM-{slugify(pid)}"
    return f"PM-{short_id(row.get('mint') or 'unknown')}"


def postmortem_filename(row: dict[str, Any]) -> str:
    return f"{postmortem_stem(row)}.md"


def render_signal_note(row: dict[str, Any]) -> str:
    market = as_dict(row.get("market") or row.get("market_info"))
    risk = as_dict(row.get("risk"))
    scoring = as_dict(row.get("scoring"))
    mint = row.get("mint") or row.get("token_mint")
    wallets = _triggering_wallets(row)
    decision = _decision_label(row)
    frontmatter = {
        "type": "signal",
        "source": "memetraderpro",
        "timestamp": iso_from_ts(row.get("captured_at") or row.get("time") or row.get("entry_timestamp")),
        "token_mint": mint,
        "decision_id": row.get("decision_id"),
        "signal_type": row.get("signal_type"),
        "paper_lane": row.get("paper_lane"),
        "score": compact_number(first_present(scoring.get("score"), row.get("total_score"), row.get("score")), 4),
        "threshold": compact_number(first_present(scoring.get("threshold"), row.get("score_threshold"), row.get("threshold")), 4),
        "decision": decision,
        "liquidity": compact_number(market.get("liquidity"), 4),
        "market_cap": compact_number(market.get("market_cap"), 4),
        "token_age": compact_number(market.get("token_age_seconds"), 4),
        "risk_flags": _risk_flags(row),
        "triggering_wallets": wallets,
        "generated_by": "memetraderpro",
    }
    body = f"""# Signal {short_id(mint)}

{GENERATED_MARKER}

## Signal Context

- Timestamp: {frontmatter["timestamp"] or "unknown"}
- Mint: {mint or "unknown"}
- Signal type: {frontmatter["signal_type"] or "unknown"}
- Paper lane: {frontmatter["paper_lane"] or "unknown"}
- Score: {frontmatter["score"]} / threshold {frontmatter["threshold"]}
- Trade / skip decision: {decision}

## Triggering Wallets

{bullet_list([wikilink(wallet_stem(wallet), wallet) for wallet in wallets], empty="No triggering wallets recorded.")}

## Score Reasons

{bullet_list(_score_reasons(row), empty="No score reasons recorded.")}

## Market Snapshot

- Liquidity: {frontmatter["liquidity"]}
- Market cap: {frontmatter["market_cap"]}
- Token age seconds: {frontmatter["token_age"]}
- Buy velocity: {market.get("buy_velocity")}
- Sell velocity: {market.get("sell_velocity")}

## Risk Flags

{bullet_list(frontmatter["risk_flags"], empty="No risk flags recorded.")}

## Later Outcome

{_known_outcome_text(row)}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def render_rejected_signal_note(row: dict[str, Any]) -> str:
    ctx = as_dict(row.get("signal context"))
    outcome = as_dict(row.get("what would have happened afterward if traded"))
    mint = row.get("mint") or ctx.get("mint")
    merged = {**ctx, "decision_id": row.get("decision_id"), "mint": mint, "paper_lane": row.get("lane") or ctx.get("paper_lane")}
    wallets = _triggering_wallets(merged)
    market = as_dict(ctx.get("market") or ctx.get("market_info"))
    frontmatter = {
        "type": "rejected_signal",
        "source": "memetraderpro",
        "timestamp": iso_from_ts(row.get("recorded_at")),
        "token_mint": mint,
        "decision_id": row.get("decision_id"),
        "lane": row.get("lane"),
        "rejection_reason": row.get("rejection reason"),
        "outcome_status": outcome.get("status"),
        "liquidity": compact_number(market.get("liquidity"), 4),
        "market_cap": compact_number(market.get("market_cap"), 4),
        "triggering_wallets": wallets,
        "generated_by": "memetraderpro",
    }
    body = f"""# Rejected Signal {short_id(mint)}

{GENERATED_MARKER}

## Rejection Summary

- Recorded: {frontmatter["timestamp"] or "unknown"}
- Mint: {mint or "unknown"}
- Lane: {frontmatter["lane"] or "unknown"}
- Reason: {frontmatter["rejection_reason"] or "unknown"}
- Outcome status: {frontmatter["outcome_status"] or "unknown"}

## Triggering Wallets

{bullet_list([wikilink(wallet_stem(wallet), wallet) for wallet in wallets], empty="No triggering wallets recorded.")}

## Score Reasons

{bullet_list(_score_reasons(ctx), empty="No score reasons recorded.")}

## Counterfactual Outcome

```json
{_json_block(outcome)}
```
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def render_paper_trade_note(row: dict[str, Any]) -> str:
    metadata = as_dict(row.get("signal_metadata"))
    mint = row.get("token_mint") or row.get("mint")
    wallets = [str(wallet) for wallet in as_list(row.get("wallets"))]
    frontmatter = {
        "type": "paper_trade",
        "source": "memetraderpro",
        "token_mint": mint,
        "decision_id": row.get("decision_id") or metadata.get("decision_id"),
        "status": row.get("status"),
        "paper_lane": row.get("paper_lane") or metadata.get("paper_lane"),
        "opened_at": row.get("entry_time_iso") or iso_from_ts(row.get("entry_time") or row.get("time")),
        "closed_at": row.get("close_time_iso") or iso_from_ts(row.get("close_time")),
        "pnl": compact_number(row.get("total_pnl") or row.get("pnl"), 6),
        "pnl_pct": compact_number(row.get("total_pnl_pct") or row.get("pnl_pct"), 6),
        "triggering_wallets": wallets,
        "generated_by": "memetraderpro",
    }
    body = f"""# Paper Trade {short_id(mint)}

{GENERATED_MARKER}

## Trade Summary

- Status: {frontmatter["status"] or "unknown"}
- Lane: {frontmatter["paper_lane"] or "unknown"}
- Opened: {frontmatter["opened_at"] or "unknown"}
- Closed: {frontmatter["closed_at"] or "open"}
- PnL: {frontmatter["pnl"]}
- PnL pct: {frontmatter["pnl_pct"]}
- Entry reason: {row.get("entry_reason") or row.get("reason") or "unknown"}
- Close reason: {row.get("close_reason") or row.get("exit_reason") or "open"}

## Triggering Wallets

{bullet_list([wikilink(wallet_stem(wallet), wallet) for wallet in wallets], empty="No triggering wallets recorded.")}

## Score Reasons

{bullet_list(as_list(metadata.get("score_reasons"))[-12:], empty="No score reasons recorded.")}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def render_postmortem_note(row: dict[str, Any]) -> str:
    tracked = as_dict(row.get("tracked"))
    wallets = [str(wallet) for wallet in as_list(tracked.get("wallet cluster composition"))]
    mint = row.get("mint")
    frontmatter = {
        "type": "postmortem",
        "source": "memetraderpro",
        "postmortem_id": row.get("postmortem_id"),
        "token_mint": mint,
        "decision_id": row.get("decision_id"),
        "paper_lane": row.get("paper_lane"),
        "status": row.get("status"),
        "generated_at": iso_from_ts(row.get("generated_at")),
        "classifications": as_list(row.get("classifications")),
        "triggering_wallets": wallets,
        "generated_by": "memetraderpro",
    }
    body = f"""# Postmortem {short_id(row.get("postmortem_id") or mint)}

{GENERATED_MARKER}

## Failure / Outcome

- Mint: {mint or "unknown"}
- Status: {row.get("status") or "unknown"}
- Primary exit attribution: {row.get("primary_exit_attribution") or "unknown"}
- Entry reason: {tracked.get("entry reason") or "unknown"}
- Exit reason: {tracked.get("exit reason") or "unknown"}
- Market regime: {tracked.get("market regime") or "unknown"}

## Triggering Wallets

{bullet_list([wikilink(wallet_stem(wallet), wallet) for wallet in wallets], empty="No triggering wallets recorded.")}

## Classifications

{bullet_list(as_list(row.get("classifications")), empty="No classifications recorded.")}

## Notes

{bullet_list(as_list(row.get("classification_notes")), empty="No classification notes recorded.")}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _triggering_wallets(row: dict[str, Any]) -> list[str]:
    triggering = row.get("triggering_wallets")
    wallets = []
    if isinstance(triggering, list):
        for item in triggering:
            if isinstance(item, dict):
                wallet = item.get("wallet") or item.get("address")
            else:
                wallet = item
            if wallet:
                wallets.append(str(wallet))
    for item in as_list(row.get("wallets")):
        if isinstance(item, dict):
            item = item.get("wallet") or item.get("address")
        if item:
            wallets.append(str(item))
    return list(dict.fromkeys(wallets))


def _score_reasons(row: dict[str, Any]) -> list[str]:
    scoring = as_dict(row.get("scoring"))
    return [
        str(item)
        for item in (
            as_list(scoring.get("reasons_tail"))
            or as_list(row.get("score_reasons_tail"))
            or as_list(row.get("scoring_reasons_tail"))
            or as_list(row.get("score_reasons"))
        )
    ]


def _risk_flags(row: dict[str, Any]) -> list[str]:
    risk = as_dict(row.get("risk"))
    flags = []
    for key in ("risk_label", "hard_block_reason", "holder_concentration_risk"):
        value = risk.get(key) or row.get(key)
        if value not in (None, "", False):
            flags.append(f"{key}: {value}")
    if bool(risk.get("hard_block") or row.get("hard_block")):
        flags.append("hard_block: true")
    return flags


def _decision_label(row: dict[str, Any]) -> str:
    if row.get("final_action"):
        return str(row["final_action"])
    if row.get("should_trade") is True:
        return "trade"
    if row.get("should_trade") is False:
        return "skip"
    if row.get("skip_bucket"):
        return f"skip:{row['skip_bucket']}"
    return "unknown"


def _known_outcome_text(row: dict[str, Any]) -> str:
    outcome = first_present(row.get("later_outcome"), row.get("outcome"), row.get("result"))
    if outcome in (None, "", [], {}):
        return "No later outcome attached yet."
    if isinstance(outcome, dict):
        return f"```json\n{_json_block(outcome)}\n```"
    return str(outcome)


def _json_block(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
