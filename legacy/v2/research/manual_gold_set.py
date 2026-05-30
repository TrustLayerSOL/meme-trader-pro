from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


VERSION = "manual_gold_set.v1"
CONFIDENCE_TIERS = [
    "A_FULL_REPLAY_SAFE",
    "B_STRONG_PARTIAL",
    "C_SUGGESTIVE",
    "D_INSUFFICIENT",
]
TIER_STRENGTH = {tier: len(CONFIDENCE_TIERS) - idx for idx, tier in enumerate(CONFIDENCE_TIERS)}
MANUAL_RESEARCH_TEXT = """MANUAL RESEARCH:
1. Open the CSV file shown above.
2. Pick the first row.
3. Open the Solscan token/activity link.
4. Try to verify supply, market-cap, or historical activity evidence at or before the decision time.
5. If you find evidence, copy the value, source URL, and notes into the evidence template shown above.
6. Use confidence tier A only if the evidence is clearly decision-time safe.
7. If you are unsure, use C_SUGGESTIVE or D_INSUFFICIENT.
8. Do not guess."""

PACKET_COLUMNS = [
    "candidate_id",
    "mint",
    "decision_slot",
    "decision_timestamp",
    "wallet",
    "signal_type",
    "current_blocker",
    "exact_evidence_needed",
    "known_price",
    "known_liquidity",
    "missing_proof_reason",
    "why_high_priority",
    "solscan_token_link",
    "solscan_activity_link",
    "solana_explorer_link",
    "dexscreener_link",
    "notes",
    "manual_status",
]

GROUP_PACKET_COLUMNS = [
    "group_id",
    "representative_candidate_id",
    "mint",
    "decision_slot",
    "decision_timestamp",
    "decision_time_utc",
    "candidate_count",
    "unique_wallet_count",
    "known_price_min",
    "known_price_max",
    "known_liquidity_min",
    "known_liquidity_max",
    "why_high_priority",
    "candidate_ids",
    "wallets",
    "solscan_token_link",
    "solscan_activity_link",
    "solana_explorer_link",
    "dexscreener_link",
    "notes",
    "manual_status",
]

EVIDENCE_TEMPLATE_COLUMNS = [
    "candidate_id",
    "mint",
    "decision_slot",
    "decision_timestamp",
    "verified_supply",
    "verified_market_cap",
    "evidence_source",
    "evidence_url",
    "screenshot_path",
    "confidence_tier",
    "notes",
]

DEFAULT_MANUAL_TIMEZONE = "UTC"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def read_json(path: Path | str, default: Any) -> Any:
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def positive_float(value: Any) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix == "K":
        multiplier = 1_000.0
        text = text[:-1]
    elif suffix == "M":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif suffix == "B":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    cleaned = text.replace("$", "").replace(",", "").strip()
    parsed = safe_float(cleaned)
    if parsed is None:
        return None
    return parsed * multiplier


def safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def iso_timestamp(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return ""
    try:
        return datetime.fromtimestamp(parsed, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def local_decision_time(value: Any, timezone_name: str = DEFAULT_MANUAL_TIMEZONE) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return ""
    try:
        tz = ZoneInfo(timezone_name)
        return datetime.fromtimestamp(parsed, tz=timezone.utc).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except (OSError, OverflowError, ValueError):
        return ""


def minute_decision_time(value: Any, timezone_name: str = DEFAULT_MANUAL_TIMEZONE) -> str:
    local_time = local_decision_time(value, timezone_name)
    if len(local_time) >= 23:
        return f"{local_time[:16]} {local_time[20:]}"
    return local_time


def market_cap_input_value(value: Any) -> str:
    parsed = positive_float(value)
    if parsed is None:
        return ""
    if parsed.is_integer():
        return str(int(parsed))
    return f"{parsed:.8f}".rstrip("0").rstrip(".")


def evidence_key(wallet: str, mint: str, signature: str) -> tuple[str, str, str]:
    return (wallet.strip(), mint.strip(), signature.strip())


def candidate_id_for(row: dict[str, Any], plan_row: dict[str, Any] | None = None) -> str:
    mint = str(row.get("token_mint") or row.get("mint") or "").strip()
    slot = str((plan_row or {}).get("decision_slot") or row.get("decision_slot") or "").strip()
    signature = str(row.get("transaction_signature") or "").strip()
    short_sig = signature[:10] if signature else "nosig"
    if mint and slot and short_sig:
        return f"manual_{mint}_{slot}_{short_sig}"
    digest = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"manual_{digest}"


def index_recovery_plan(plan: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in as_list(plan.get("candidate_rows")):
        if not isinstance(row, dict):
            continue
        key = evidence_key(
            str(row.get("wallet") or ""),
            str(row.get("token_mint") or ""),
            str(row.get("transaction_signature") or ""),
        )
        indexed[key] = row
    return indexed


def manual_links(mint: str) -> dict[str, str]:
    return {
        "solscan_token_link": f"https://solscan.io/token/{mint}",
        "solscan_activity_link": f"https://solscan.io/token/{mint}#activities",
        "solana_explorer_link": f"https://explorer.solana.com/address/{mint}",
        "dexscreener_link": f"https://dexscreener.com/solana/{mint}",
    }


def rank_proof_candidates(
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    records = [row for row in as_list(score_ready_report.get("records")) if isinstance(row, dict)]
    plan_by_key = index_recovery_plan(recovery_plan)
    wallet_counts = Counter(str(row.get("wallet") or "") for row in records if row.get("wallet"))
    token_counts = Counter(str(row.get("token_mint") or "") for row in records if row.get("token_mint"))
    candidates: list[dict[str, Any]] = []

    for row in records:
        if row.get("readiness_status") != "needs_archival_supply_for_market_cap":
            continue
        if row.get("next_action") != "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT":
            continue
        if row.get("price_present") is not True or row.get("liquidity_present") is not True:
            continue
        if row.get("decision_time_safe") is not True:
            continue

        wallet = str(row.get("wallet") or "").strip()
        mint = str(row.get("token_mint") or "").strip()
        signature = str(row.get("transaction_signature") or "").strip()
        plan_row = plan_by_key.get(evidence_key(wallet, mint, signature), {})
        decision_slot = safe_int(plan_row.get("decision_slot") or row.get("decision_slot"))
        decision_ts = safe_float(plan_row.get("decision_block_time") or row.get("timestamp"), None)
        liquidity = positive_float(row.get("liquidity")) or 0
        price = positive_float(row.get("price")) or 0
        priority = 100
        priority += min(wallet_counts[wallet], 20) * 8
        priority += min(token_counts[mint], 20) * 4
        priority += min(int(liquidity // 10_000), 20)
        reasons = [
            "price/liquidity already recovered",
            "blocked only by decision-time supply/market-cap proof",
        ]
        if wallet_counts[wallet] > 1:
            reasons.append(f"wallet has {wallet_counts[wallet]} blocked observations")
        if token_counts[mint] > 1:
            reasons.append(f"token has {token_counts[mint]} blocked observations")

        links = manual_links(mint)
        candidates.append(
            {
                "candidate_id": candidate_id_for(row, plan_row),
                "token_mint": mint,
                "mint": mint,
                "decision_slot": decision_slot,
                "decision_timestamp": decision_ts,
                "decision_time_utc": iso_timestamp(decision_ts),
                "wallet": wallet,
                "signal_type": str(row.get("source_status") or "wallet_behavior_context"),
                "known_price": price,
                "known_liquidity": liquidity,
                "current_blocker": str(row.get("readiness_status") or ""),
                "missing_proof_reason": "missing_archival_supply",
                "exact_evidence_needed": str(
                    plan_row.get("required_evidence")
                    or "historical mint supply or market-cap proof at or before decision slot/time"
                ),
                "why_high_priority": "; ".join(reasons),
                "priority_score": priority,
                "transaction_signature": signature,
                **links,
            }
        )

    candidates.sort(key=lambda row: (-int(row.get("priority_score") or 0), str(row.get("token_mint") or "")))
    return candidates[: max(0, int(limit))]


def group_key_for_candidate(row: dict[str, Any]) -> tuple[str, str]:
    mint = str(row.get("token_mint") or row.get("mint") or "").strip()
    timestamp = safe_float(row.get("decision_timestamp"), None)
    return (mint, f"{timestamp:.6f}" if timestamp is not None else "")


def rank_proof_candidate_groups(
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    candidates = rank_proof_candidates(score_ready_report, recovery_plan, limit=10_000)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = group_key_for_candidate(candidate)
        if all(key):
            grouped[key].append(candidate)

    groups: list[dict[str, Any]] = []
    for (mint, timestamp_key), rows in grouped.items():
        rows.sort(key=lambda row: (-int(row.get("priority_score") or 0), str(row.get("candidate_id") or "")))
        representative = rows[0]
        prices = [positive_float(row.get("known_price")) for row in rows]
        prices = [value for value in prices if value is not None]
        liquidities = [positive_float(row.get("known_liquidity")) for row in rows]
        liquidities = [value for value in liquidities if value is not None]
        wallets = sorted({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
        candidate_ids = [str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")]
        decision_ts = safe_float(representative.get("decision_timestamp"), None)
        decision_slot = safe_int(representative.get("decision_slot"))
        priority = max(int(row.get("priority_score") or 0) for row in rows) + len(rows) * 25
        reasons = [
            f"{len(rows)} rows share the same mint and exact decision timestamp",
            "one Tier A market-cap check can cover this exact-time group",
        ]
        if len(wallets) > 1:
            reasons.append(f"{len(wallets)} wallets represented")
        groups.append(
            {
                "group_id": f"manual_group_{mint}_{decision_slot or timestamp_key}",
                "representative_candidate_id": representative.get("candidate_id"),
                "token_mint": mint,
                "mint": mint,
                "decision_slot": decision_slot,
                "decision_timestamp": decision_ts,
                "decision_time_utc": iso_timestamp(decision_ts),
                "candidate_count": len(rows),
                "unique_wallet_count": len(wallets),
                "candidate_ids": candidate_ids,
                "wallets": wallets,
                "known_price_min": min(prices) if prices else None,
                "known_price_max": max(prices) if prices else None,
                "known_liquidity_min": min(liquidities) if liquidities else None,
                "known_liquidity_max": max(liquidities) if liquidities else None,
                "why_high_priority": "; ".join(reasons),
                "priority_score": priority,
                **manual_links(mint),
            }
        )

    groups.sort(key=lambda row: (-int(row.get("priority_score") or 0), str(row.get("token_mint") or "")))
    return groups[: max(0, int(limit))]


def build_manual_research_packet(
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    *,
    output_dir: Path | str,
    limit: int = 25,
    generated_at: float | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = rank_proof_candidates(score_ready_report, recovery_plan, limit=limit)
    csv_path = output_dir / "manual_research_packet.csv"
    json_path = output_dir / "manual_research_packet.json"
    template_path = output_dir / "manual_evidence_template.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_COLUMNS)
        writer.writeheader()
        for row in candidates:
            writer.writerow(
                {
                    "candidate_id": row.get("candidate_id"),
                    "mint": row.get("token_mint"),
                    "decision_slot": row.get("decision_slot"),
                    "decision_timestamp": row.get("decision_timestamp"),
                    "wallet": row.get("wallet"),
                    "signal_type": row.get("signal_type"),
                    "current_blocker": row.get("current_blocker"),
                    "exact_evidence_needed": row.get("exact_evidence_needed"),
                    "known_price": row.get("known_price"),
                    "known_liquidity": row.get("known_liquidity"),
                    "missing_proof_reason": row.get("missing_proof_reason"),
                    "why_high_priority": row.get("why_high_priority"),
                    "solscan_token_link": row.get("solscan_token_link"),
                    "solscan_activity_link": row.get("solscan_activity_link"),
                    "solana_explorer_link": row.get("solana_explorer_link"),
                    "dexscreener_link": row.get("dexscreener_link"),
                    "notes": "",
                    "manual_status": "",
                }
            )

    with template_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_TEMPLATE_COLUMNS)
        writer.writeheader()
        for row in candidates:
            writer.writerow(
                {
                    "candidate_id": row.get("candidate_id"),
                    "mint": row.get("token_mint"),
                    "decision_slot": row.get("decision_slot"),
                    "decision_timestamp": row.get("decision_timestamp"),
                    "confidence_tier": "",
                    "notes": "",
                }
            )

    packet = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "summary": {"candidates_exported": len(candidates), "limit": limit},
        "output_paths": {
            "csv": str(csv_path),
            "json": str(json_path),
            "manual_evidence_template": str(template_path),
            "manual_group_evidence_template": str(template_path),
        },
        "template_columns": EVIDENCE_TEMPLATE_COLUMNS,
        "candidates": candidates,
        "manual_research_instructions": MANUAL_RESEARCH_TEXT,
    }
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def build_manual_research_group_packet(
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    *,
    output_dir: Path | str,
    limit: int = 25,
    generated_at: float | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = rank_proof_candidate_groups(score_ready_report, recovery_plan, limit=limit)
    csv_path = output_dir / "manual_research_group_packet.csv"
    json_path = output_dir / "manual_research_group_packet.json"
    template_path = output_dir / "manual_group_evidence_template.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GROUP_PACKET_COLUMNS)
        writer.writeheader()
        for row in groups:
            writer.writerow(
                {
                    "group_id": row.get("group_id"),
                    "representative_candidate_id": row.get("representative_candidate_id"),
                    "mint": row.get("token_mint"),
                    "decision_slot": row.get("decision_slot"),
                    "decision_timestamp": row.get("decision_timestamp"),
                    "decision_time_utc": row.get("decision_time_utc"),
                    "candidate_count": row.get("candidate_count"),
                    "unique_wallet_count": row.get("unique_wallet_count"),
                    "known_price_min": row.get("known_price_min"),
                    "known_price_max": row.get("known_price_max"),
                    "known_liquidity_min": row.get("known_liquidity_min"),
                    "known_liquidity_max": row.get("known_liquidity_max"),
                    "why_high_priority": row.get("why_high_priority"),
                    "candidate_ids": ";".join(row.get("candidate_ids") or []),
                    "wallets": ";".join(row.get("wallets") or []),
                    "solscan_token_link": row.get("solscan_token_link"),
                    "solscan_activity_link": row.get("solscan_activity_link"),
                    "solana_explorer_link": row.get("solana_explorer_link"),
                    "dexscreener_link": row.get("dexscreener_link"),
                    "notes": "",
                    "manual_status": "",
                }
            )

    with template_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_TEMPLATE_COLUMNS)
        writer.writeheader()
        for row in groups:
            writer.writerow(
                {
                    "candidate_id": row.get("representative_candidate_id"),
                    "mint": row.get("token_mint"),
                    "decision_slot": row.get("decision_slot"),
                    "decision_timestamp": row.get("decision_timestamp"),
                    "confidence_tier": "",
                    "notes": "",
                }
            )

    packet = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "summary": {
            "groups_exported": len(groups),
            "covered_candidate_rows": sum(int(row.get("candidate_count") or 0) for row in groups),
            "limit": limit,
        },
        "output_paths": {
            "csv": str(csv_path),
            "json": str(json_path),
            "manual_evidence_template": str(template_path),
        },
        "template_columns": EVIDENCE_TEMPLATE_COLUMNS,
        "group_columns": GROUP_PACKET_COLUMNS,
        "groups": groups,
        "manual_research_instructions": MANUAL_RESEARCH_TEXT,
    }
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def minute_prefill_key(mint: str, decision_timestamp: Any) -> str:
    minute = minute_decision_time(decision_timestamp)
    return f"{mint}|{minute}" if mint and minute else ""


def read_market_cap_prefills(output_dir: Path | str) -> dict[str, str]:
    output_dir = Path(output_dir)
    values: dict[str, str] = {}
    conflicts: set[str] = set()

    def add_prefill(row: dict[str, Any]) -> None:
        mint = str(row.get("mint") or row.get("token_mint") or "").strip()
        key = minute_prefill_key(mint, row.get("decision_timestamp"))
        value = market_cap_input_value(row.get("verified_market_cap"))
        if not key or not value:
            return
        existing = values.get(key)
        if existing and existing != value:
            conflicts.add(key)
            return
        values[key] = value

    imported_path = output_dir / "manual_evidence_imported.jsonl"
    for row in read_jsonl(imported_path):
        add_prefill(row)

    exports_dir = output_dir / "user_exports"
    for csv_path in sorted(exports_dir.glob("*.csv")):
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    add_prefill(row)
        except FileNotFoundError:
            continue

    for key in conflicts:
        values.pop(key, None)
    return values


def render_manual_market_cap_entry_page(
    groups: list[dict[str, Any]], *, title: str, prefills_by_minute: dict[str, str] | None = None
) -> str:
    prefills_by_minute = prefills_by_minute or {}
    rows_html: list[str] = []
    groups_by_mint: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in groups:
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        minute_label = minute_decision_time(row.get("decision_timestamp"))
        groups_by_mint[mint][minute_label].append(row)

    idx = 0
    for mint, minute_rows in groups_by_mint.items():
        first_row = next((rows[0] for rows in minute_rows.values() if rows), {})
        dexscreener_link = str((first_row or {}).get("dexscreener_link") or manual_links(mint)["dexscreener_link"])
        rows_html.append(
            "\n".join(
                [
                    '<section class="token-block">',
                    f'<div class="token-head"><a href="{html.escape(dexscreener_link)}" target="_blank" rel="noreferrer">Open Dexscreener</a>',
                    f'<span class="mint">{html.escape(mint)}</span></div>',
                ]
            )
        )
        for minute_label, bucket_rows in minute_rows.items():
            idx += 1
            targets = [
                {
                    "candidate_id": row.get("representative_candidate_id"),
                    "mint": mint,
                    "decision_slot": row.get("decision_slot"),
                    "decision_timestamp": row.get("decision_timestamp"),
                    "decision_time_local": local_decision_time(row.get("decision_timestamp")),
                    "evidence_url": dexscreener_link,
                }
                for row in bucket_rows
            ]
            minute_key = f"{mint}|{minute_label}"
            target_json = json.dumps(targets, separators=(",", ":"), sort_keys=True)
            prefill_value = prefills_by_minute.get(minute_key, "")
            rows_html.append(
                "\n".join(
                    [
                        '<div class="entry-row">',
                        f'<div class="row-number">{idx}</div>',
                        f'<div class="decision-time">{html.escape(minute_label)}</div>',
                        (
                            '<input class="market-cap-input" inputmode="decimal" '
                            'placeholder="market cap, ex: 104800" '
                            f'value="{html.escape(prefill_value)}" '
                            f'data-minute-key="{html.escape(minute_key)}" '
                            f'data-mint="{html.escape(mint)}" '
                            f'data-minute-label="{html.escape(minute_label)}" '
                            f'data-targets="{html.escape(target_json)}" '
                            "/>"
                        ),
                        "</div>",
                    ]
                )
            )
        rows_html.append("</section>")

    body = "\n".join(rows_html)
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080c12;
      --panel: #101722;
      --panel-2: #0c121b;
      --line: #243044;
      --text: #e9eef8;
      --muted: #9aa6b9;
      --accent: #5ee0a5;
      --accent-2: #6aa7ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: rgba(8, 12, 18, 0.96);
      backdrop-filter: blur(10px);
    }}
    h1 {{ margin: 0; font-size: 20px; }}
    .sub {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
    .actions {{ display: flex; align-items: center; gap: 10px; }}
    button {{
      border: 1px solid var(--line);
      background: #172235;
      color: var(--text);
      border-radius: 8px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.primary {{ background: var(--accent); color: #03110a; border-color: var(--accent); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; }}
    .help {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px 16px;
      background: var(--panel-2);
      color: var(--muted);
      margin-bottom: 16px;
      line-height: 1.45;
    }}
    .token-block {{
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      margin-bottom: 14px;
      overflow: hidden;
    }}
    .token-head {{
      display: grid;
      grid-template-columns: 180px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      padding: 13px 16px;
      border-bottom: 1px solid var(--line);
      background: #121b29;
    }}
    a {{ color: var(--accent-2); font-weight: 800; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .mint {{
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      overflow-wrap: anywhere;
    }}
    .entry-row {{
      display: grid;
      grid-template-columns: 52px 240px minmax(220px, 360px);
      gap: 14px;
      align-items: center;
      padding: 12px 16px;
      border-top: 1px solid rgba(36, 48, 68, 0.68);
    }}
    .entry-row:first-of-type {{ border-top: 0; }}
    .row-number {{ color: var(--muted); font-weight: 800; }}
    .decision-time {{ font-weight: 800; }}
    input {{
      width: 100%;
      min-height: 42px;
      border-radius: 8px;
      border: 1px solid #34445f;
      background: #080d15;
      color: var(--text);
      padding: 10px 12px;
      font-size: 16px;
    }}
    input:focus {{ outline: 2px solid var(--accent-2); border-color: var(--accent-2); }}
    .status {{ color: var(--muted); font-weight: 700; min-width: 86px; text-align: right; }}
    @media (max-width: 760px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .token-head, .entry-row {{ grid-template-columns: 1fr; }}
      .actions {{ width: 100%; }}
      button {{ flex: 1; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{safe_title}</h1>
      <div class="sub">Only enter raw market-cap dollars. Example: 104.80K becomes 104800.</div>
    </div>
    <div class="actions">
      <div id="filledStatus" class="status">0 filled</div>
      <button type="button" id="clearButton">Clear</button>
      <button type="button" id="exportButton" class="primary">Export CSV</button>
    </div>
  </header>
  <main>
    <div class="help">
      Open the Dexscreener link, set the chart to MCap, use UTC time, find the one-minute time bucket shown here, then type only the raw market cap number in the box. The export button creates an importer-ready CSV with B_STRONG_PARTIAL evidence for the exact rows inside that minute bucket.
    </div>
    {body}
  </main>
  <script>
    const storageKey = "memetraderpro_manual_market_cap_entry_v2";
    const inputs = Array.from(document.querySelectorAll(".market-cap-input"));
    const statusEl = document.getElementById("filledStatus");
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");

    function cleanValue(value) {{
      return String(value || "").replace(/[$, ]/g, "").trim();
    }}

    function updateStatus() {{
      const filled = inputs.filter(input => cleanValue(input.value)).length;
      statusEl.textContent = `${{filled}} filled`;
    }}

    function save() {{
      const payload = {{}};
      inputs.forEach(input => {{
        const value = cleanValue(input.value);
        if (value) payload[input.dataset.minuteKey] = value;
      }});
      localStorage.setItem(storageKey, JSON.stringify(payload));
      updateStatus();
    }}

    function csvEscape(value) {{
      const text = String(value ?? "");
      if (/[",\\n]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
      return text;
    }}

    function exportCsv() {{
      const columns = [
        "candidate_id", "mint", "decision_slot", "decision_timestamp",
        "verified_supply", "verified_market_cap", "evidence_source",
        "evidence_url", "screenshot_path", "confidence_tier", "notes"
      ];
      const rows = [columns];
      inputs.forEach(input => {{
        const value = cleanValue(input.value);
        if (!value) return;
        const targets = JSON.parse(input.dataset.targets || "[]");
        targets.forEach(target => {{
          rows.push([
            target.candidate_id,
            target.mint,
            target.decision_slot,
            target.decision_timestamp,
            "",
            value,
            "Dexscreener",
            target.evidence_url,
            "",
            "B_STRONG_PARTIAL",
            `Dexscreener MCap chart nearest one-minute bucket ${{input.dataset.minuteLabel}} shows market cap ${{value}}. Applied to exact decision time ${{target.decision_time_local}} as partial calibration evidence only; not archival account-state proof.`
          ]);
        }});
      }});
      const csv = rows.map(row => row.map(csvEscape).join(",")).join("\\n") + "\\n";
      const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "manual_market_cap_evidence_filled.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }}

    inputs.forEach(input => {{
      if (saved[input.dataset.minuteKey]) input.value = saved[input.dataset.minuteKey];
      input.addEventListener("input", save);
    }});
    document.getElementById("exportButton").addEventListener("click", exportCsv);
    document.getElementById("clearButton").addEventListener("click", () => {{
      if (!confirm("Clear all entered market caps from this browser?")) return;
      localStorage.removeItem(storageKey);
      inputs.forEach(input => input.value = "");
      updateStatus();
    }});
    updateStatus();
  </script>
</body>
</html>
"""


def build_manual_market_cap_entry_page(
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    *,
    output_dir: Path | str,
    limit: int = 25,
    generated_at: float | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = rank_proof_candidate_groups(score_ready_report, recovery_plan, limit=limit)
    html_path = output_dir / "manual_market_cap_entry.html"
    title = "MemeTraderPro Manual Market Cap Entry"
    prefills_by_minute = read_market_cap_prefills(output_dir)
    html_path.write_text(
        render_manual_market_cap_entry_page(groups, title=title, prefills_by_minute=prefills_by_minute),
        encoding="utf-8",
    )
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "summary": {
            "groups_exported": len(groups),
            "covered_candidate_rows": sum(int(row.get("candidate_count") or 0) for row in groups),
            "minute_prefills_loaded": len(prefills_by_minute),
            "limit": limit,
        },
        "output_paths": {
            "html": str(html_path),
            "download_csv_name": "manual_market_cap_evidence_filled.csv",
        },
        "operator_note": (
            "This HTML sheet is an easier entry surface for B_STRONG_PARTIAL Dexscreener market-cap evidence. "
            "It does not unlock live execution or mutate wallet trust."
        ),
    }


def candidate_index(score_ready_report: dict[str, Any], recovery_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["candidate_id"]: row
        for row in rank_proof_candidates(score_ready_report, recovery_plan, limit=10_000)
        if row.get("candidate_id")
    }


def validate_manual_row(row: dict[str, str], candidates: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    candidate_id = str(row.get("candidate_id") or "").strip()
    mint = str(row.get("mint") or "").strip()
    if not candidate_id:
        errors.append("missing_candidate_id")
    if not mint:
        errors.append("missing_mint")
    candidate = candidates.get(candidate_id)
    if candidate is None:
        errors.append("candidate_id_not_in_current_blocked_set")
    elif mint and mint != candidate.get("token_mint"):
        errors.append("mint_does_not_match_candidate")

    raw_supply = str(row.get("verified_supply") or "").strip()
    supply = positive_float(raw_supply)
    market_cap = positive_float(row.get("verified_market_cap"))
    tier = str(row.get("confidence_tier") or "").strip()
    if raw_supply and supply is None:
        errors.append("verified_supply_must_be_positive")
    if tier == "A_FULL_REPLAY_SAFE" and supply is None and market_cap is None:
        errors.append("tier_a_requires_verified_supply_or_market_cap")
    if market_cap is not None and market_cap > 1_000_000_000_000:
        errors.append("verified_market_cap_impossible")
    if market_cap is None and str(row.get("verified_market_cap") or "").strip():
        errors.append("verified_market_cap_must_be_positive")
    source = str(row.get("evidence_source") or "").strip()
    notes = str(row.get("notes") or "").strip()
    if not source:
        errors.append("missing_evidence_source")
    if not notes:
        errors.append("missing_notes")
    if tier not in CONFIDENCE_TIERS:
        errors.append("invalid_confidence_tier")
    decision_slot = safe_int(row.get("decision_slot"))
    decision_ts = safe_float(row.get("decision_timestamp"), None)
    if candidate and safe_int(candidate.get("decision_slot")) != decision_slot:
        errors.append("decision_slot_does_not_match_candidate")
    if candidate and safe_float(candidate.get("decision_timestamp"), None) != decision_ts:
        errors.append("decision_timestamp_does_not_match_candidate")

    if errors:
        return None, errors

    assert candidate is not None
    evidence_url = str(row.get("evidence_url") or "").strip()
    record = {
        "version": VERSION,
        "candidate_id": candidate_id,
        "mint": mint,
        "token_mint": mint,
        "wallet": candidate.get("wallet"),
        "transaction_signature": candidate.get("transaction_signature"),
        "decision_slot": decision_slot,
        "decision_timestamp": decision_ts,
        "verified_supply": supply,
        "verified_market_cap": market_cap,
        "evidence_source": source,
        "evidence_url": evidence_url,
        "screenshot_path": str(row.get("screenshot_path") or "").strip(),
        "confidence_tier": tier,
        "notes": notes,
        "proof_unblock_allowed": tier == "A_FULL_REPLAY_SAFE" and (supply is not None or market_cap is not None),
        "decision_time_safe": tier == "A_FULL_REPLAY_SAFE" and (supply is not None or market_cap is not None),
        "can_mutate_wallet_trust": False,
        "imported_at": time.time(),
    }
    return record, []


def stronger_or_equal(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    return TIER_STRENGTH.get(str(existing.get("confidence_tier")), 0) >= TIER_STRENGTH.get(
        str(incoming.get("confidence_tier")), 0
    )


def supply_record_from_manual(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("confidence_tier") != "A_FULL_REPLAY_SAFE" or row.get("proof_unblock_allowed") is not True:
        return None
    supply = positive_float(row.get("verified_supply"))
    if supply is None:
        return None
    return {
        "version": "manual_gold_set_supply.v1",
        "status": "archival_supply_recovered",
        "source": "manual_gold_set",
        "source_file": "data/manual_research/manual_evidence_imported.jsonl",
        "token_mint": row.get("token_mint") or row.get("mint"),
        "wallet": row.get("wallet"),
        "transaction_signature": row.get("transaction_signature"),
        "timestamp": row.get("decision_timestamp"),
        "decision_slot": row.get("decision_slot"),
        "snapshot_slot": row.get("decision_slot"),
        "decision_time_safe": True,
        "ui_supply": supply,
        "raw_supply": supply,
        "decimals": None,
        "confidence_tier": row.get("confidence_tier"),
        "evidence_url": row.get("evidence_url"),
        "can_mutate_wallet_trust": False,
    }


def import_manual_evidence(
    csv_path: Path | str,
    *,
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    output_dir: Path | str,
    generated_at: float | None = None,
) -> dict[str, Any]:
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    imported_path = output_dir / "manual_evidence_imported.jsonl"
    rejected_path = output_dir / "manual_evidence_rejected.csv"
    supply_path = output_dir / "manual_supply_evidence_records.jsonl"
    report_path = output_dir / "manual_evidence_import_report.json"

    candidates = candidate_index(score_ready_report, recovery_plan)
    existing_by_id = {str(row.get("candidate_id") or ""): row for row in read_jsonl(imported_path)}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    preserved_stronger = 0

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            record, errors = validate_manual_row(row, candidates)
            if errors or record is None:
                rejected.append({**row, "row_number": row_number, "rejection_reasons": ";".join(errors)})
                continue
            existing = existing_by_id.get(str(record["candidate_id"]))
            if existing and stronger_or_equal(existing, record):
                preserved_stronger += 1
                continue
            existing_by_id[str(record["candidate_id"])] = record
            accepted.append(record)

    stored = sorted(existing_by_id.values(), key=lambda row: str(row.get("candidate_id") or ""))
    write_jsonl(imported_path, stored)
    supply_rows = [row for row in (supply_record_from_manual(row) for row in stored) if row is not None]
    tier_a_market_cap_rows = [
        row
        for row in stored
        if row.get("confidence_tier") == "A_FULL_REPLAY_SAFE"
        and row.get("proof_unblock_allowed") is True
        and positive_float(row.get("verified_market_cap")) is not None
    ]
    write_jsonl(supply_path, supply_rows)

    with rejected_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(EVIDENCE_TEMPLATE_COLUMNS) + ["row_number", "rejection_reasons"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rejected:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    tier_counts = Counter(str(row.get("confidence_tier") or "UNKNOWN") for row in stored)
    report = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "rows_scanned": len(accepted) + len(rejected) + preserved_stronger,
            "accepted_rows": len(accepted),
            "rejected_rows": len(rejected),
            "preserved_stronger_rows": preserved_stronger,
            "stored_manual_rows": len(stored),
            "tier_counts": dict(sorted(tier_counts.items())),
            "manual_tier_a_supply_records": len(supply_rows),
            "manual_tier_a_market_cap_records": len(tier_a_market_cap_rows),
            "proof_unblock_allowed_rows": sum(1 for row in stored if row.get("proof_unblock_allowed") is True),
        },
        "output_paths": {
            "manual_evidence_imported": str(imported_path),
            "manual_supply_evidence_records": str(supply_path),
            "manual_evidence_rejected": str(rejected_path),
            "report": str(report_path),
        },
        "rejected_rows": rejected,
        "operator_note": (
            "Manual evidence is stored separately from provider evidence. A_FULL_REPLAY_SAFE rows with verified supply "
            "or verified market cap can unblock proof review; B/C/D rows remain review notes."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def normalized_csv_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(key or "").strip().lower().replace(" ", "_"): str(value or "").strip() for key, value in row.items()}


def format_solscan_token_amount(raw_amount: str, raw_decimals: str, token: str) -> str:
    amount = safe_float(raw_amount)
    decimals = safe_int(raw_decimals)
    if amount is None or decimals is None or decimals < 0:
        return str(raw_amount or "").strip()
    normalized = amount / (10**decimals)
    text = f"{normalized:.12f}".rstrip("0").rstrip(".")
    if token:
        return f"{text} {token}"
    return text


def solscan_amount_for_candidate(row: dict[str, str], mint: str) -> str:
    if row.get("amount"):
        return row.get("amount") or ""
    token1 = row.get("token1") or ""
    token2 = row.get("token2") or ""
    if mint and token1 == mint:
        return format_solscan_token_amount(row.get("amount1") or "", row.get("tokendecimals1") or "", token1)
    if mint and token2 == mint:
        return format_solscan_token_amount(row.get("amount2") or "", row.get("tokendecimals2") or "", token2)
    if row.get("amount1"):
        return format_solscan_token_amount(row.get("amount1") or "", row.get("tokendecimals1") or "", token1)
    if row.get("amount2"):
        return format_solscan_token_amount(row.get("amount2") or "", row.get("tokendecimals2") or "", token2)
    return ""


def import_solscan_historical_evidence(
    csv_path: Path | str,
    *,
    candidate_id: str,
    source_url: str,
    score_ready_report: dict[str, Any],
    recovery_plan: dict[str, Any],
    output_dir: Path | str,
    generated_at: float | None = None,
) -> dict[str, Any]:
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    imported_path = output_dir / "solscan_historical_evidence_imported.jsonl"
    rejected_path = output_dir / "solscan_historical_evidence_rejected.csv"
    report_path = output_dir / "solscan_historical_evidence_import_report.json"

    candidates = candidate_index(score_ready_report, recovery_plan)
    candidate = candidates.get(str(candidate_id).strip())
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    if candidate is None:
        report = {
            "generated_at": time.time() if generated_at is None else float(generated_at),
            "version": "solscan_historical_evidence.v1",
            "review_only": True,
            "live_execution_locked": True,
            "summary": {
                "rows_scanned": 0,
                "accepted_rows": 0,
                "rejected_rows": 0,
                "candidate_found": False,
            },
            "rejected_rows": [{"candidate_id": candidate_id, "rejection_reasons": "candidate_id_not_in_current_blocked_set"}],
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, raw_row in enumerate(reader, start=2):
            row = normalized_csv_row(raw_row)
            signature = row.get("signature") or row.get("transaction_signature") or row.get("txn") or ""
            action = row.get("action") or row.get("type") or ""
            candidate_mint = str(candidate.get("token_mint") or "")
            amount = solscan_amount_for_candidate(row, candidate_mint)
            value_text = row.get("value") or row.get("usd") or row.get("usd_value") or ""
            program = row.get("program") or row.get("programs") or ""
            observed_time = row.get("time") or row.get("human_time") or row.get("timestamp") or row.get("date") or row.get("block_time") or ""
            value_usd = parse_money(value_text)
            errors: list[str] = []
            if not signature:
                errors.append("missing_signature")
            if not action:
                errors.append("missing_action")
            if not amount:
                errors.append("missing_amount")
            if not source_url:
                errors.append("missing_source_url")
            if errors:
                rejected.append({**raw_row, "row_number": row_number, "rejection_reasons": ";".join(errors)})
                continue
            candidate_signature = str(candidate.get("transaction_signature") or "")
            accepted.append(
                {
                    "version": "solscan_historical_evidence.v1",
                    "candidate_id": candidate_id,
                    "mint": candidate.get("token_mint"),
                    "token_mint": candidate.get("token_mint"),
                    "wallet": candidate.get("wallet"),
                    "solscan_from": row.get("from") or "",
                    "decision_slot": candidate.get("decision_slot"),
                    "decision_timestamp": candidate.get("decision_timestamp"),
                    "solscan_signature": signature,
                    "candidate_signature": candidate_signature,
                    "signature_matches_candidate": bool(candidate_signature and signature == candidate_signature),
                    "observed_time": observed_time,
                    "action": action,
                    "amount": amount,
                    "value_text": value_text,
                    "value_usd": value_usd,
                    "program": program,
                    "evidence_source": "Solscan historical activity export",
                    "evidence_url": source_url,
                    "source_file": str(csv_path),
                    "confidence_tier": "B_STRONG_PARTIAL" if value_usd is not None else "C_SUGGESTIVE",
                    "proof_unblock_allowed": False,
                    "decision_time_safe": False,
                    "can_mutate_wallet_trust": False,
                    "notes": (
                        "Solscan historical export row. Useful for transaction/value/activity review, "
                        "but it is not archival mint supply proof by itself."
                    ),
                    "imported_at": time.time(),
                }
            )

    existing = read_jsonl(imported_path)
    merged_by_key = {
        f"{row.get('candidate_id')}|{row.get('solscan_signature')}|{row.get('observed_time')}": row
        for row in existing
    }
    for row in accepted:
        merged_by_key[f"{row.get('candidate_id')}|{row.get('solscan_signature')}|{row.get('observed_time')}"] = row
    stored = sorted(merged_by_key.values(), key=lambda row: str(row.get("candidate_id") or "") + str(row.get("solscan_signature") or ""))
    write_jsonl(imported_path, stored)

    with rejected_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["row_number", "rejection_reasons", "Signature", "Time", "Action", "Amount", "Value", "Program"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rejected:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    report = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": "solscan_historical_evidence.v1",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "rows_scanned": len(accepted) + len(rejected),
            "accepted_rows": len(accepted),
            "rejected_rows": len(rejected),
            "stored_rows": len(stored),
            "candidate_found": True,
            "proof_unblock_allowed_rows": 0,
        },
        "output_paths": {
            "solscan_historical_evidence_imported": str(imported_path),
            "solscan_historical_evidence_rejected": str(rejected_path),
            "report": str(report_path),
        },
        "operator_note": (
            "Solscan historical activity evidence is stored as partial review evidence. It does not unlock "
            "proof readiness unless separate decision-time supply evidence is imported through the manual Tier A path."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_proof_readiness_report(
    *,
    score_ready_report: dict[str, Any],
    stage8_report: dict[str, Any],
    manual_evidence_rows: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    score_summary = as_dict(score_ready_report.get("summary"))
    stage8_summary = as_dict(stage8_report.get("summary"))
    tier_counts = Counter(str(row.get("confidence_tier") or "UNKNOWN") for row in manual_evidence_rows)
    manual_unblocked = sum(1 for row in manual_evidence_rows if row.get("proof_unblock_allowed") is True)
    records_scanned = int(score_summary.get("records_scanned") or 0)
    base_score_ready = int(score_summary.get("score_ready_records") or 0)
    near_score_ready = int(score_summary.get("near_score_ready_records") or 0)
    adjusted_score_ready = base_score_ready + manual_unblocked
    readiness_pct = int(stage8_summary.get("proof_readiness_pct") or 0)
    adjusted_pct = readiness_pct
    if records_scanned > 0 and manual_unblocked > 0:
        adjusted_pct = max(readiness_pct, min(100, round((adjusted_score_ready / records_scanned) * 100)))
    remaining_blocked = max(0, near_score_ready - manual_unblocked)

    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "version": VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "total_blocked_rows": int(score_summary.get("records_scanned") or 0) - base_score_ready,
            "near_score_ready_rows": near_score_ready,
            "fully_replay_safe_rows": base_score_ready,
            "manual_tier_a_rows": tier_counts.get("A_FULL_REPLAY_SAFE", 0),
            "manual_tier_b_rows": tier_counts.get("B_STRONG_PARTIAL", 0),
            "manual_tier_c_rows": tier_counts.get("C_SUGGESTIVE", 0),
            "manual_tier_d_rows": tier_counts.get("D_INSUFFICIENT", 0),
            "manual_unblocked_rows": manual_unblocked,
            "remaining_blocked_rows": remaining_blocked,
            "wallet_score_readiness_pct": int(stage8_summary.get("stage6_data_score_readiness_pct") or 0),
            "proof_readiness_pct": readiness_pct,
            "manual_adjusted_score_ready_rows": adjusted_score_ready,
            "manual_adjusted_proof_readiness_pct": adjusted_pct,
            "top_blockers": as_dict(score_summary.get("status_counts")),
        },
        "operator_note": (
            "Manual-adjusted proof readiness is a review metric. Only Tier A rows count as replay-safe; "
            "lower tiers remain useful research notes but do not validate wallet trust."
        ),
    }
