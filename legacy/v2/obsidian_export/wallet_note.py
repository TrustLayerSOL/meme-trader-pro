from __future__ import annotations

from typing import Any

from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
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


def wallet_stem(wallet: str) -> str:
    return f"WAL-{slugify(wallet, max_length=180)}"


def wallet_filename(wallet: str) -> str:
    return f"{wallet_stem(wallet)}.md"


def wallet_frontmatter(row: dict[str, Any]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or row.get("wallet_address") or "unknown")
    profile = as_dict(row.get("behavior_profile"))
    recommendation = as_dict(row.get("recommendation"))
    confidence = as_dict(row.get("confidence"))
    behavior_score = as_dict(row.get("behavior_score"))

    roi = first_present(profile.get("wallet_roi"), row.get("paper_watch_expectancy"), row.get("average_pnl_after_signal"))
    win_rate = first_present(profile.get("win_rate"), row.get("paper_watch_win_rate"))
    runner_count = first_present(
        row.get("runner_participation"),
        profile.get("participation_frequency_in_runners"),
        row.get("runner_count"),
    )
    rug_count = first_present(
        row.get("rug_participation"),
        profile.get("participation_frequency_in_rugs"),
        row.get("rug_count"),
    )
    avg_hold = first_present(profile.get("average_hold_duration"), row.get("avg_hold_seconds"))
    confidence_score = first_present(behavior_score.get("score"), confidence.get("score"), row.get("score"))
    last_seen = first_present(row.get("last_seen"), row.get("generated_at"))

    return {
        "type": "wallet",
        "source": "memetraderpro",
        "wallet_address": wallet,
        "status": first_present(recommendation.get("action"), row.get("status"), row.get("tier"), "unknown"),
        "tier": row.get("tier"),
        "roi": compact_number(roi, 6),
        "win_rate": compact_number(win_rate, 4),
        "runner_count": int(runner_count or 0),
        "rug_count": int(rug_count or 0),
        "average_hold_time": compact_number(avg_hold, 4),
        "confidence_score": compact_number(confidence_score, 4),
        "last_seen": iso_from_ts(last_seen),
        "generated_by": "memetraderpro",
    }


def render_wallet_note(
    row: dict[str, Any],
    *,
    recent_signals: list[dict[str, Any]] | None = None,
    related_wallets: list[str] | None = None,
    runners: list[str] | None = None,
    rugs: list[str] | None = None,
    postmortems: list[dict[str, Any]] | None = None,
) -> str:
    frontmatter = wallet_frontmatter(row)
    wallet = frontmatter["wallet_address"]
    recommendation = as_dict(row.get("recommendation"))
    profile = as_dict(row.get("behavior_profile"))
    relationships = as_dict(row.get("wallet_relationships"))
    related = related_wallets
    if related is None:
        related = relationships.get("related_wallets") if isinstance(relationships.get("related_wallets"), list) else []

    signals = recent_signals or []
    postmortem_rows = postmortems or []
    runner_links = [wikilink(f"SIG-{short_id(mint)}", str(mint)) for mint in (runners or [])[:20]]
    rug_links = [wikilink(f"SIG-{short_id(mint)}", str(mint)) for mint in (rugs or [])[:20]]

    body = f"""# Wallet {wallet}

{GENERATED_MARKER}

## Behavior Summary

- Status: {frontmatter.get("status") or "unknown"}
- Tier: {frontmatter.get("tier") or "unknown"}
- Confidence score: {frontmatter.get("confidence_score")}
- ROI / expectancy: {frontmatter.get("roi")}
- Win rate: {frontmatter.get("win_rate")}
- Runner count: {frontmatter.get("runner_count")}
- Rug count: {frontmatter.get("rug_count")}
- Average hold time: {frontmatter.get("average_hold_time")}
- Last seen: {frontmatter.get("last_seen") or "unknown"}

## Recommendation

{bullet_list([recommendation.get("action")] + list(recommendation.get("reasons") or []), empty="No recommendation available.")}

## Recent Signals

{_signal_table(signals)}

## Related Wallets

{bullet_list([wikilink(wallet_stem(str(item))) for item in related[:25]], empty="No related wallets recorded.")}

## Runners

{bullet_list(runner_links, empty="No runner links recorded.")}

## Rugs

{bullet_list(rug_links, empty="No rug links recorded.")}

## Linked Postmortems

{bullet_list([_postmortem_link(row) for row in postmortem_rows[:25]], empty="No linked postmortems recorded.")}

## Data Completeness

- Sample quality: {row.get("sample_quality") or profile.get("sample_quality") or "unknown"}
- Signals: {row.get("signal_count") or row.get("total_signals") or 0}
- Paper entries: {row.get("paper_watch_entries") or 0}
- Known outcomes: {row.get("known_outcomes") or 0}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _signal_table(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "No recent signals recorded."
    rows = []
    for signal in signals[:20]:
        mint = signal.get("mint") or signal.get("token_mint")
        rows.append(
            [
                iso_from_ts(signal.get("time") or signal.get("captured_at") or signal.get("recorded_at")),
                _signal_link(signal),
                signal.get("signal_type") or signal.get("type"),
                compact_number(signal.get("score") or signal.get("total_score"), 4),
                signal.get("should_trade"),
            ]
        )
    return table(["Time", "Mint", "Type", "Score", "Trade"], rows)


def _signal_link(signal: dict[str, Any]) -> str:
    mint = signal.get("mint") or signal.get("token_mint")
    decision_id = signal.get("decision_id")
    if decision_id:
        return wikilink(f"SIG-{slugify(decision_id)}", short_id(mint))
    ts = signal.get("captured_at") or signal.get("time") or signal.get("timestamp") or signal.get("recorded_at")
    if ts:
        return wikilink(f"SIG-{slugify(ts)}-{short_id(mint)}", short_id(mint))
    return short_id(mint)


def _postmortem_link(row: dict[str, Any]) -> str:
    pid = row.get("postmortem_id") or row.get("id") or row.get("trade_fingerprint")
    mint = row.get("mint") or row.get("token_mint") or pid
    if not pid:
        return str(mint)
    return wikilink(f"PM-{slugify(pid)}")
