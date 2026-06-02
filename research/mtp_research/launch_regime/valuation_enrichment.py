"""Offline valuation enrichment for launch lifecycle artifacts.

This module is intentionally conservative. It does not infer true market cap
or FDV unless supply, price, and USD conversion provenance are present.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SNAPSHOT_OUTPUT = "launch_lifecycle_snapshots_valuation_enriched.jsonl"
OUTCOME_OUTPUT = "launch_lifecycle_outcomes_valuation_enriched.jsonl"
REPORT_JSON = "valuation_enrichment_report.json"
REPORT_MD = "valuation_enrichment_report.md"
VALUATION_THRESHOLDS = (15_000, 35_000, 50_000, 100_000)


def enrich_snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
    return enrich_snapshot_row_with_context(row)


def enrich_snapshot_row_with_context(
    row: dict[str, Any],
    *,
    supply_by_mint: dict[str, dict[str, Any]] | None = None,
    sol_usd_rows: list[dict[str, Any]] | None = None,
    max_sol_usd_staleness_seconds: int = 7200,
) -> dict[str, Any]:
    enriched = dict(row)
    metadata = dict(row.get("metadata_json") or {})
    price_sol = _first_number(row, metadata, ("price_sol", "price_quote_sol"))
    price_usd = _first_number(row, metadata, ("price_usd", "price_quote_usd"))
    supply_row = (supply_by_mint or {}).get(str(row.get("token_mint")))
    total_supply = _first_number(row, metadata, ("total_supply", "token_total_supply"))
    if total_supply is None and supply_row:
        total_supply = _float_or_none(supply_row.get("total_supply"))
    circulating_supply = _first_number(row, metadata, ("circulating_supply",))
    sol_usd = _first_number(row, metadata, ("sol_usd", "sol_usd_price"))
    sol_usd_source = None
    sol_usd_staleness = None
    if sol_usd is None and sol_usd_rows:
        sol_usd_match = _nearest_sol_usd(
            sol_usd_rows,
            _price_timestamp(row, metadata),
            max_staleness_seconds=max_sol_usd_staleness_seconds,
        )
        if sol_usd_match:
            sol_usd = sol_usd_match["sol_usd"]
            sol_usd_source = sol_usd_match["source"]
            sol_usd_staleness = sol_usd_match["staleness_seconds"]
    liquidity_proxy_sol = _first_number(row, metadata, ("bonding_curve_liquidity_proxy_sol", "liquidity_proxy_sol", "liquidity_proxy"))
    if liquidity_proxy_sol is None:
        liquidity_proxy_sol = _float_or_none(row.get("liquidity_proxy"))
    liquidity_source = (
        metadata.get("liquidity_proxy_source")
        or metadata.get("liquidity_proxy_source_120m")
        or ("bonding_curve_post_balance" if liquidity_proxy_sol is not None else None)
    )

    _apply_valuation_fields(
        enriched,
        price_sol=price_sol,
        price_usd=price_usd,
        total_supply=total_supply,
        circulating_supply=circulating_supply,
        sol_usd=sol_usd,
        supply_source=supply_row.get("supply_source") if supply_row else None,
        sol_usd_source=sol_usd_source,
        sol_usd_staleness_seconds=sol_usd_staleness,
        liquidity_proxy_sol=liquidity_proxy_sol,
        liquidity_source=liquidity_source,
    )
    return enriched


def enrich_outcome_row(row: dict[str, Any]) -> dict[str, Any]:
    return enrich_outcome_row_with_context(row)


def enrich_outcome_row_with_context(
    row: dict[str, Any],
    *,
    supply_by_mint: dict[str, dict[str, Any]] | None = None,
    sol_usd_rows: list[dict[str, Any]] | None = None,
    max_sol_usd_staleness_seconds: int = 7200,
) -> dict[str, Any]:
    enriched = dict(row)
    metadata = dict(row.get("metadata_json") or {})
    price_sol = _first_number(row, metadata, ("price_sol", "price_quote_sol", "price_sol_at_120m", "price_sol_120m"))
    price_usd = _first_number(row, metadata, ("price_usd", "price_quote_usd", "price_usd_120m"))
    supply_row = (supply_by_mint or {}).get(str(row.get("token_mint")))
    total_supply = _first_number(row, metadata, ("total_supply", "token_total_supply"))
    if total_supply is None and supply_row:
        total_supply = _float_or_none(supply_row.get("total_supply"))
    circulating_supply = _first_number(row, metadata, ("circulating_supply",))
    sol_usd = _first_number(row, metadata, ("sol_usd", "sol_usd_price"))
    sol_usd_source = None
    sol_usd_staleness = None
    if sol_usd is None and sol_usd_rows:
        sol_usd_match = _nearest_sol_usd(
            sol_usd_rows,
            _price_timestamp(row, metadata),
            max_staleness_seconds=max_sol_usd_staleness_seconds,
        )
        if sol_usd_match:
            sol_usd = sol_usd_match["sol_usd"]
            sol_usd_source = sol_usd_match["source"]
            sol_usd_staleness = sol_usd_match["staleness_seconds"]
    liquidity_proxy_sol = _first_number(
        row,
        metadata,
        ("bonding_curve_liquidity_proxy_sol", "liquidity_proxy_at_120m", "liquidity_proxy_sol"),
    )
    liquidity_source = (
        metadata.get("liquidity_proxy_source_120m")
        or metadata.get("liquidity_proxy_source")
        or ("bonding_curve_post_balance" if liquidity_proxy_sol is not None else None)
    )

    _apply_valuation_fields(
        enriched,
        price_sol=price_sol,
        price_usd=price_usd,
        total_supply=total_supply,
        circulating_supply=circulating_supply,
        sol_usd=sol_usd,
        supply_source=supply_row.get("supply_source") if supply_row else None,
        sol_usd_source=sol_usd_source,
        sol_usd_staleness_seconds=sol_usd_staleness,
        liquidity_proxy_sol=liquidity_proxy_sol,
        liquidity_source=liquidity_source,
    )
    return enriched


def run_valuation_enrichment(
    *,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    output_dir: Path | str,
    supply_path: Path | str | None = None,
    sol_usd_path: Path | str | None = None,
    max_sol_usd_staleness_seconds: int = 7200,
) -> dict[str, Any]:
    output = Path(output_dir)
    supply_by_mint = _supply_by_mint(Path(supply_path)) if supply_path else {}
    sol_usd_rows = _load_jsonl(Path(sol_usd_path)) if sol_usd_path else []
    snapshots = [
        enrich_snapshot_row_with_context(
            row,
            supply_by_mint=supply_by_mint,
            sol_usd_rows=sol_usd_rows,
            max_sol_usd_staleness_seconds=max_sol_usd_staleness_seconds,
        )
        for row in _load_jsonl(Path(snapshots_path))
    ]
    outcomes = [
        enrich_outcome_row_with_context(
            row,
            supply_by_mint=supply_by_mint,
            sol_usd_rows=sol_usd_rows,
            max_sol_usd_staleness_seconds=max_sol_usd_staleness_seconds,
        )
        for row in _load_jsonl(Path(outcomes_path))
    ]

    snapshot_output = output / SNAPSHOT_OUTPUT
    outcome_output = output / OUTCOME_OUTPUT
    _write_jsonl(snapshot_output, snapshots)
    _write_jsonl(outcome_output, outcomes)

    rows = [*snapshots, *outcomes]
    report = {
        "snapshot_count": len(snapshots),
        "outcome_count": len(outcomes),
        "true_market_cap_available_count": _count_true(rows, "true_market_cap_available"),
        "fdv_available_count": _count_true(rows, "fdv_available"),
        "valuation_proxy_available_count": _count_true(rows, "valuation_proxy_available"),
        "bonding_curve_liquidity_proxy_available_count": _count_positive(rows, "bonding_curve_liquidity_proxy_sol"),
        "threshold_outcomes_usable_count": _count_true(rows, "threshold_outcomes_usable"),
        "proxy_threshold_outcomes_usable_count": _count_true(rows, "proxy_threshold_outcomes_usable"),
        "price_sol_available_count": _count_true(rows, "price_sol_available"),
        "price_usd_available_count": _count_true(rows, "price_usd_available"),
        "supply_available_count": _count_true(rows, "supply_available"),
        "sol_usd_available_count": _count_true(rows, "sol_usd_available"),
        "valuation_missing_reason_counts": _sorted_counter(row.get("valuation_missing_reason") for row in rows),
        "threshold_outcomes_missing_reason_counts": dict(
            _sorted_counter(row.get("threshold_outcomes_missing_reason") for row in rows)
        ),
        "snapshot_output_path": str(snapshot_output),
        "outcome_output_path": str(outcome_output),
        "network_calls": 0,
    }
    _write_report(report, output)
    return report


def _apply_valuation_fields(
    row: dict[str, Any],
    *,
    price_sol: float | None,
    price_usd: float | None,
    total_supply: float | None,
    circulating_supply: float | None,
    sol_usd: float | None,
    supply_source: str | None = None,
    sol_usd_source: str | None = None,
    sol_usd_staleness_seconds: int | None = None,
    liquidity_proxy_sol: float | None,
    liquidity_source: str | None,
) -> None:
    supply = circulating_supply if circulating_supply is not None else total_supply
    supply_source = _supply_source(total_supply=total_supply, circulating_supply=circulating_supply)
    derived_price_usd = price_usd
    if derived_price_usd is None and price_sol is not None and sol_usd is not None:
        derived_price_usd = price_sol * sol_usd
    true_market_cap = supply * derived_price_usd if circulating_supply is not None and derived_price_usd is not None else None
    fdv = total_supply * derived_price_usd if total_supply is not None and derived_price_usd is not None else None
    valuation_proxy = fdv

    row.update(
        {
            "price_sol_available": price_sol is not None,
            "price_usd_available": derived_price_usd is not None,
            "supply_available": supply is not None,
            "total_supply_available": total_supply is not None,
            "circulating_supply_available": circulating_supply is not None,
            "sol_usd_available": sol_usd is not None,
            "true_market_cap_available": true_market_cap is not None,
            "fdv_available": fdv is not None,
            "valuation_proxy_available": valuation_proxy is not None,
            "true_market_cap_usd": true_market_cap,
            "fdv_usd": fdv,
            "valuation_proxy_usd": valuation_proxy,
            "bonding_curve_liquidity_proxy_sol": liquidity_proxy_sol,
            "bonding_curve_liquidity_proxy_available": liquidity_proxy_sol is not None and liquidity_proxy_sol > 0,
            "valuation_source": liquidity_source,
            "valuation_confidence": "fdv_proxy" if valuation_proxy is not None else ("liquidity_proxy_only" if liquidity_proxy_sol is not None else "missing"),
            "valuation_missing_reason": _valuation_missing_reason(
                price_sol=price_sol,
                price_usd=derived_price_usd,
                supply=supply,
                sol_usd=sol_usd,
            ),
            "supply_source": supply_source or _supply_source(total_supply=total_supply, circulating_supply=circulating_supply),
            "supply_missing_reason": None if supply is not None else "trusted_supply_not_available",
            "sol_usd_source": sol_usd_source,
            "sol_usd_missing_reason": None if sol_usd is not None else "historical_sol_usd_not_available",
            "sol_usd_staleness_seconds": sol_usd_staleness_seconds,
            "price_source": _price_source(price_sol=price_sol, price_usd=price_usd),
            "threshold_outcomes_usable": true_market_cap is not None,
            "threshold_outcomes_source": "true_market_cap_usd" if true_market_cap is not None else None,
            "threshold_outcomes_missing_reason": None if true_market_cap is not None else "usd_valuation_unavailable",
            "threshold_outcomes_semantics": "true_market_cap_usd" if true_market_cap is not None else "unusable_no_usd_valuation",
            "proxy_threshold_outcomes_usable": valuation_proxy is not None,
            "proxy_threshold_outcomes_source": "valuation_proxy_usd" if valuation_proxy is not None else None,
            "proxy_threshold_outcomes_semantics": "fdv_usd_current_supply_proxy" if valuation_proxy is not None else "unusable_no_usd_valuation_proxy",
        }
    )
    for threshold in VALUATION_THRESHOLDS:
        row[f"ever_hit_valuation_proxy_{threshold // 1000}k"] = valuation_proxy >= threshold if valuation_proxy is not None else None


def _valuation_missing_reason(
    *,
    price_sol: float | None,
    price_usd: float | None,
    supply: float | None,
    sol_usd: float | None,
) -> str | None:
    if supply is not None and price_usd is not None:
        return None
    missing = []
    if supply is None:
        missing.append("supply")
    if price_usd is None:
        if price_sol is not None and sol_usd is None:
            missing.append("sol_usd")
        else:
            missing.append("price")
    return "missing_" + "_and_".join(missing)


def _price_source(*, price_sol: float | None, price_usd: float | None) -> str | None:
    if price_usd is not None:
        return "provided_usd_price"
    if price_sol is not None:
        return "provided_sol_price"
    return None


def _supply_source(*, total_supply: float | None, circulating_supply: float | None) -> str | None:
    if circulating_supply is not None:
        return "provided_circulating_supply"
    if total_supply is not None:
        return "provided_total_supply"
    return None


def _first_number(row: dict[str, Any], metadata: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
        value = _float_or_none(metadata.get(key))
        if value is not None:
            return value
    return None


def _price_timestamp(row: dict[str, Any], metadata: dict[str, Any]) -> int | None:
    for key in ("price_event_block_time", "price_event_block_time_120m", "snapshot_ts", "launch_ts"):
        value = row.get(key)
        if value is None:
            value = metadata.get(key)
        if value is not None:
            return int(value)
    return None


def _nearest_sol_usd(
    rows: list[dict[str, Any]],
    ts: int | None,
    *,
    max_staleness_seconds: int,
) -> dict[str, Any] | None:
    if ts is None or not rows:
        return None
    best = min(rows, key=lambda row: abs(int(row["ts"]) - ts))
    staleness = abs(int(best["ts"]) - ts)
    if staleness > max_staleness_seconds:
        return None
    return {
        "sol_usd": _float_or_none(best.get("sol_usd")),
        "source": best.get("source"),
        "staleness_seconds": staleness,
    }


def _supply_by_mint(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["mint"]): row for row in _load_jsonl(path) if row.get("mint")}


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_true(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) is True)


def _count_positive(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if (_float_or_none(row.get(key)) or 0) > 0)


def _sorted_counter(values) -> dict[str, int]:
    counts = Counter("none" if value is None else str(value) for value in values)
    return dict(sorted(counts.items()))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    tmp_path.replace(path)


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REPORT_JSON).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Valuation Enrichment Report",
        "",
        "Offline data-quality report only. No backtests, validation, thesis evaluation, or trading logic.",
        "",
        f"- snapshots: `{report['snapshot_count']}`",
        f"- outcomes: `{report['outcome_count']}`",
        f"- true_market_cap_available_count: `{report['true_market_cap_available_count']}`",
        f"- fdv_available_count: `{report['fdv_available_count']}`",
        f"- valuation_proxy_available_count: `{report['valuation_proxy_available_count']}`",
        f"- bonding_curve_liquidity_proxy_available_count: `{report['bonding_curve_liquidity_proxy_available_count']}`",
        f"- threshold_outcomes_usable_count: `{report['threshold_outcomes_usable_count']}`",
        f"- network_calls: `{report['network_calls']}`",
        "",
    ]
    (output_dir / REPORT_MD).write_text("\n".join(lines), encoding="utf-8")
