#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.candidate_walk_forward_validation import DEFAULT_CANDIDATE_WALLETS  # noqa: E402
from wallets.dune_candidate_feasibility import (  # noqa: E402
    build_dune_candidate_feasibility_report,
    build_dune_sql_queries,
)


DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
DEFAULT_DUNE_API_BASE = "https://api.dune.com/api/v1"
WALLET_FIELDS = [
    "wallet_address",
    "transaction_history_rows",
    "first_seen",
    "last_seen",
    "dex_trade_rows",
    "token_transfer_rows",
    "candidate_token_count",
    "dune_historical_activity_available",
    "dune_quote_anchor_candidate_available",
    "dune_price_context_candidate_available",
    "dune_liquidity_context_candidate_available",
    "dune_market_cap_context_candidate_available",
    "proof_ready_from_dune_alone",
]


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def default_start_date() -> str:
    return (date.today() - timedelta(days=30)).isoformat()


def default_end_date() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def parse_wallets(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WALLET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in WALLET_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    capability = report.get("dune_capability_assessment") if isinstance(report.get("dune_capability_assessment"), dict) else {}
    lines = [
        "# Dune Candidate Feasibility Probe",
        "",
        "Candidate-only review of whether Dune can support historical walk-forward evidence. This is not a trade signal.",
        "",
        "## Summary",
        "",
        f"- Candidate wallets: {summary.get('candidate_wallets', 0)}",
        f"- Queries completed: {summary.get('queries_completed', 0)}",
        f"- Queries failed: {summary.get('queries_failed', 0)}",
        f"- Rows returned: {summary.get('rows_returned_total', 0)}",
        f"- Wallets with transaction history: {summary.get('wallets_with_transaction_history', 0)}",
        f"- Wallets with DEX matches: {summary.get('wallets_with_dex_matches', 0)}",
        f"- Quote-anchor candidate rows: {summary.get('quote_anchor_candidate_rows', 0)}",
        f"- Price-context candidate rows: {summary.get('price_context_candidate_rows', 0)}",
        f"- Liquidity-context candidate rows: {summary.get('liquidity_context_candidate_rows', 0)}",
        f"- Market-cap context candidate rows: {summary.get('market_cap_context_candidate_rows', 0)}",
        f"- Proof-ready rows from Dune alone: {summary.get('proof_ready_rows', 0)}",
        "",
        "## Capability Assessment",
        "",
        f"- Historical wallet activity: {capability.get('historical_wallet_activity')}",
        f"- Same-transaction quote-anchor candidates: {capability.get('same_transaction_quote_anchor_candidates')}",
        f"- Token price-context candidates: {capability.get('token_price_context_candidates')}",
        f"- Decision-time liquidity: {capability.get('decision_time_liquidity')}",
        f"- Decision-time market cap: {capability.get('decision_time_market_cap')}",
        f"- Safe for walk-forward backfill: {capability.get('safe_for_walk_forward_backfill')}",
        f"- Safe as trust source by itself: {capability.get('safe_as_trust_source_by_itself')}",
        "",
        "## Wallets",
        "",
        "| Wallet | Tx Rows | DEX Rows | Transfer Rows | Token Count | Quote Anchor Candidate | Proof Ready From Dune Alone |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('transaction_history_rows')} | "
            f"{row.get('dex_trade_rows')} | {row.get('token_transfer_rows')} | "
            f"{row.get('candidate_token_count')} | {row.get('dune_quote_anchor_candidate_available')} | "
            f"{row.get('proof_ready_from_dune_alone')} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Review only.",
            "- Candidate wallets only.",
            "- No live trading.",
            "- No wallet promotion.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
            "- No proof-ready claim unless price, liquidity, and market-cap context are complete.",
        ]
    )
    return "\n".join(lines) + "\n"


class DuneClient:
    def __init__(self, api_key: str, api_base: str = DEFAULT_DUNE_API_BASE) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")

    def request_json(self, method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Dune-Api-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(text)
            except json.JSONDecodeError:
                return exc.code, {"raw_error": text[:1000]}

    def execute_sql(self, sql: str, *, performance: str = "small", max_polls: int = 45) -> list[dict[str, Any]]:
        status, payload = self.request_json(
            "POST",
            f"{self.api_base}/sql/execute",
            {"sql": sql, "performance": performance},
        )
        if status != 200 or not payload.get("execution_id"):
            raise RuntimeError(f"Dune SQL execution failed: http={status} payload={payload}")
        execution_id = payload["execution_id"]
        final: dict[str, Any] = {}
        for _ in range(max_polls):
            time.sleep(2)
            status, final = self.request_json("GET", f"{self.api_base}/execution/{execution_id}/status")
            state = final.get("state")
            if state in {"QUERY_STATE_COMPLETED", "QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"}:
                break
        if final.get("state") != "QUERY_STATE_COMPLETED":
            raise RuntimeError(f"Dune SQL did not complete: http={status} payload={final}")
        status, result = self.request_json("GET", f"{self.api_base}/execution/{execution_id}/results?limit=10000")
        if status != 200:
            raise RuntimeError(f"Dune result fetch failed: http={status} payload={result}")
        rows = ((result.get("result") if isinstance(result.get("result"), dict) else {}).get("rows")) or []
        return [row for row in rows if isinstance(row, dict)]


def execute_queries(
    queries: dict[str, str],
    *,
    api_key: str,
    api_base: str,
    performance: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    client = DuneClient(api_key=api_key, api_base=api_base)
    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for name, sql in queries.items():
        try:
            results[name] = client.execute_sql(sql, performance=performance)
        except Exception as exc:  # pragma: no cover - live API safety path
            errors[name] = str(exc)
    return results, errors


def write_dune_candidate_feasibility_probe(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    candidate_wallets: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    execute: bool = False,
    api_key: str | None = None,
    api_key_env: str = "DUNE_API_KEY",
    api_base: str = DEFAULT_DUNE_API_BASE,
    performance: str = "small",
    limit: int = 500,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    candidates = candidate_wallets or DEFAULT_CANDIDATE_WALLETS
    start = start_date or default_start_date()
    end = end_date or default_end_date()
    queries = build_dune_sql_queries(candidate_wallets=candidates, start_date=start, end_date=end, limit=limit)
    query_results: dict[str, list[dict[str, Any]]] = {}
    query_errors: dict[str, str] = {}
    execution_mode = "dry_run"
    if execute:
        resolved_key = api_key or os.environ.get(api_key_env)
        if not resolved_key:
            raise RuntimeError(f"--execute requires {api_key_env} to be set or an API key passed by the caller")
        query_results, query_errors = execute_queries(
            queries,
            api_key=resolved_key,
            api_base=api_base,
            performance=performance,
        )
        execution_mode = "dune_api"

    report = build_dune_candidate_feasibility_report(
        candidate_wallets=candidates,
        start_date=start,
        end_date=end,
        query_results=query_results,
        generated_at=generated_at,
        execution_mode=execution_mode,
        query_errors=query_errors,
        limit=limit,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_feasibility_{run_id}.json"
    csv_path = output / f"dune_candidate_feasibility_wallets_{run_id}.csv"
    md_path = output / f"dune_candidate_feasibility_{run_id}.md"
    sql_path = output / f"dune_candidate_feasibility_sql_{run_id}.json"
    rows_path = output / f"dune_candidate_feasibility_rows_{run_id}.json"
    report["run_id"] = run_id
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "sql": str(sql_path),
        "rows": str(rows_path),
    }
    write_json(json_path, report)
    write_json(output / "dune_candidate_feasibility.json", report)
    write_json(sql_path, queries)
    write_json(rows_path, query_results)
    write_json(output / "dune_candidate_feasibility_rows.json", query_results)
    write_csv(csv_path, [row for row in report.get("wallets", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a candidate-only Dune historical feasibility probe.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--candidate-wallets", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--execute", action="store_true", help="Run live Dune API queries. Default only writes SQL.")
    parser.add_argument("--api-key-env", default="DUNE_API_KEY")
    parser.add_argument("--api-base", default=DEFAULT_DUNE_API_BASE)
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="small")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_feasibility_probe(
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_wallets=parse_wallets(args.candidate_wallets),
        start_date=args.start_date,
        end_date=args.end_date,
        execute=args.execute,
        api_key_env=args.api_key_env,
        api_base=args.api_base,
        performance=args.performance,
        limit=args.limit,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
