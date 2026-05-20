from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from wallets.archival_mint_snapshot_response_import import normalize_raw_responses, response_id
from wallets.historical_market_context_backfill import relative_path


MODE = "PROVIDER_RECOMMENDED_RESPONSE_WORKFLOW_REVIEW_ONLY"
VERSION = "provider_recommended_response_workflow.v1"


def read_json(path: Path, default: Any) -> Any:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return parsed


def as_rooted_path(path: str | Path | None, root: Path) -> Path | None:
    if path is None:
        return None
    parsed = Path(str(path))
    return parsed if parsed.is_absolute() else root / parsed


def response_rows_from_path(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], str(exc)
    return normalize_raw_responses(payload), None


def count_combined_raw_responses(path: Path | None) -> tuple[int, bool, str | None]:
    if path is None or not path.exists():
        return 0, False, None
    rows, error = response_rows_from_path(path)
    if error is not None:
        return 0, True, error
    return len(rows), True, None


def build_chunk_status_rows(response_template_chunks: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in response_template_chunks:
        request_ids = {str(value) for value in chunk.get("request_ids", []) if str(value)}
        raw_response_path = as_rooted_path(chunk.get("raw_response_save_path"), root)
        display_path = relative_path(raw_response_path, root) if raw_response_path is not None else None

        if raw_response_path is None:
            rows.append(
                {
                    "index": chunk.get("index"),
                    "request_count": len(request_ids) or int(chunk.get("request_count") or 0),
                    "raw_response_save_path": None,
                    "status": "missing_raw_response_path",
                    "responses": 0,
                    "matched_response_ids": 0,
                    "missing_response_ids": sorted(request_ids),
                    "unexpected_response_ids": [],
                }
            )
            continue

        if not raw_response_path.exists():
            rows.append(
                {
                    "index": chunk.get("index"),
                    "request_count": len(request_ids) or int(chunk.get("request_count") or 0),
                    "raw_response_save_path": display_path,
                    "status": "missing_response_file",
                    "responses": 0,
                    "matched_response_ids": 0,
                    "missing_response_ids": sorted(request_ids),
                    "unexpected_response_ids": [],
                }
            )
            continue

        responses, error = response_rows_from_path(raw_response_path)
        if error is not None:
            rows.append(
                {
                    "index": chunk.get("index"),
                    "request_count": len(request_ids) or int(chunk.get("request_count") or 0),
                    "raw_response_save_path": display_path,
                    "status": "invalid_response_file",
                    "error": error,
                    "responses": 0,
                    "matched_response_ids": 0,
                    "missing_response_ids": sorted(request_ids),
                    "unexpected_response_ids": [],
                }
            )
            continue

        actual_ids = {str(response_id(row)) for row in responses if response_id(row)}
        matched_ids = request_ids & actual_ids
        missing_ids = request_ids - actual_ids
        unexpected_ids = actual_ids - request_ids
        if missing_ids:
            status = "partial_response_file"
        elif unexpected_ids:
            status = "ready_with_unexpected_responses"
        else:
            status = "ready_to_combine"
        rows.append(
            {
                "index": chunk.get("index"),
                "request_count": len(request_ids) or int(chunk.get("request_count") or 0),
                "raw_response_save_path": display_path,
                "status": status,
                "responses": len(responses),
                "matched_response_ids": len(matched_ids),
                "missing_response_ids": sorted(missing_ids),
                "unexpected_response_ids": sorted(unexpected_ids),
            }
        )
    return rows


def summary_from_rows(
    *,
    request_bundle_report: dict[str, Any],
    chunk_rows: list[dict[str, Any]],
    combined_raw_responses: int,
    combined_raw_response_exists: bool,
    response_import_report: dict[str, Any],
    proof_readiness_report: dict[str, Any],
) -> dict[str, Any]:
    bundle_summary = request_bundle_report.get("summary") if isinstance(request_bundle_report, dict) else {}
    import_summary = response_import_report.get("summary") if isinstance(response_import_report, dict) else {}
    proof_summary = proof_readiness_report.get("summary") if isinstance(proof_readiness_report, dict) else {}
    return {
        "focused_request_rows": int(bundle_summary.get("requests_bundled") or 0),
        "focused_target_tokens": int(bundle_summary.get("target_tokens") or 0),
        "filtered_out_broad_requests": int(bundle_summary.get("filtered_out_requests") or 0),
        "response_part_files_expected": len(chunk_rows),
        "response_part_files_present": sum(1 for row in chunk_rows if row.get("status") != "missing_response_file"),
        "response_part_files_missing": sum(1 for row in chunk_rows if row.get("status") == "missing_response_file"),
        "invalid_response_part_files": sum(1 for row in chunk_rows if row.get("status") == "invalid_response_file"),
        "partial_response_part_files": sum(1 for row in chunk_rows if row.get("status") == "partial_response_file"),
        "chunks_ready_to_combine": sum(
            1 for row in chunk_rows if row.get("status") in {"ready_to_combine", "ready_with_unexpected_responses"}
        ),
        "chunks_missing_response_files": sum(1 for row in chunk_rows if row.get("status") == "missing_response_file"),
        "responses_in_part_files": sum(int(row.get("responses") or 0) for row in chunk_rows),
        "matched_response_ids_in_part_files": sum(int(row.get("matched_response_ids") or 0) for row in chunk_rows),
        "combined_raw_response_exists": combined_raw_response_exists,
        "combined_raw_responses": combined_raw_responses,
        "raw_responses_scanned_by_import": int(import_summary.get("raw_responses_scanned") or 0),
        "snapshots_imported": int(import_summary.get("snapshots_imported") or 0),
        "blocked_missing_response": int(import_summary.get("blocked_missing_response") or 0),
        "proof_readiness_pct": int(proof_summary.get("proof_readiness_pct") or 0),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def choose_next_action(summary: dict[str, Any], chunk_rows: list[dict[str, Any]]) -> dict[str, str]:
    def format_paths(paths: list[str], limit: int = 5) -> str:
        shown = paths[:limit]
        suffix = f", and {len(paths) - limit} more" if len(paths) > limit else ""
        return ", ".join(shown) + suffix

    invalid = [row for row in chunk_rows if row.get("status") == "invalid_response_file"]
    if invalid:
        paths = format_paths([str(row.get("raw_response_save_path")) for row in invalid])
        return {
            "code": "fix_invalid_response_parts",
            "detail": f"Fix invalid JSON in response part file(s): {paths}",
        }

    missing = [row for row in chunk_rows if row.get("status") == "missing_response_file"]
    partial = [row for row in chunk_rows if row.get("status") == "partial_response_file"]
    if missing or partial:
        missing_paths = [str(row.get("raw_response_save_path")) for row in missing]
        partial_paths = [str(row.get("raw_response_save_path")) for row in partial]
        detail_parts = []
        if missing_paths:
            detail_parts.append("missing: " + format_paths(missing_paths))
        if partial_paths:
            detail_parts.append("partial: " + format_paths(partial_paths))
        return {
            "code": "fill_missing_response_parts",
            "detail": "Fill provider/manual response part file(s) before combining: " + "; ".join(detail_parts),
        }

    expected = int(summary.get("focused_request_rows") or 0)
    combined = int(summary.get("combined_raw_responses") or 0)
    part_responses = int(summary.get("responses_in_part_files") or 0)
    if expected and (not summary.get("combined_raw_response_exists") or combined < min(expected, part_responses)):
        return {
            "code": "run_response_combiner",
            "detail": "All response parts look present. Combine them into the focused raw response file.",
        }

    imported = int(summary.get("raw_responses_scanned_by_import") or 0)
    if combined and imported < combined:
        return {
            "code": "run_focused_import",
            "detail": "Combined raw responses exist but have not been imported into archival snapshot evidence yet.",
        }

    if int(summary.get("snapshots_imported") or 0) > 0:
        return {
            "code": "run_rebuild_chain",
            "detail": "Imported snapshots exist. Rebuild archival supply evidence, score-ready context, and proof-readiness reports.",
        }

    return {
        "code": "blocked_waiting_for_archival_responses",
        "detail": "No usable provider/manual response rows are available yet.",
    }


def operator_commands() -> list[str]:
    return [
        "python3 utils/build_provider_recommended_archival_mint_snapshot_request_bundle.py",
        "python3 utils/combine_provider_response_chunks.py",
        "python3 utils/import_provider_recommended_archival_mint_supply_snapshots.py",
        "python3 utils/build_archival_supply_evidence.py",
        "python3 utils/build_score_ready_market_context.py",
        "python3 utils/build_proof_readiness_blocker_reduction.py",
        "python3 utils/export_archival_supply_proof_readiness.py",
        "python3 main.py proof-readiness",
    ]


def build_provider_response_workflow_report(
    *,
    request_bundle_report: dict[str, Any],
    combined_raw_response_path: str | Path,
    response_import_report: dict[str, Any] | None = None,
    proof_readiness_report: dict[str, Any] | None = None,
    root: Path | str,
    generated_at: float | None = None,
) -> dict[str, Any]:
    root = Path(root)
    response_import_report = response_import_report or {"summary": {}}
    proof_readiness_report = proof_readiness_report or {"summary": {}}
    template_chunks = request_bundle_report.get("response_template_chunks")
    if not isinstance(template_chunks, list):
        template_chunks = []
    chunk_rows = build_chunk_status_rows(template_chunks, root)
    combined_path = as_rooted_path(combined_raw_response_path, root)
    combined_count, combined_exists, combined_error = count_combined_raw_responses(combined_path)
    summary = summary_from_rows(
        request_bundle_report=request_bundle_report,
        chunk_rows=chunk_rows,
        combined_raw_responses=combined_count,
        combined_raw_response_exists=combined_exists,
        response_import_report=response_import_report,
        proof_readiness_report=proof_readiness_report,
    )
    report = {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "provider_calls_performed": False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": summary,
        "next_action": choose_next_action(summary, chunk_rows),
        "operator_commands": operator_commands(),
        "chunk_rows": chunk_rows,
        "combined_raw_response": {
            "path": relative_path(combined_path, root) if combined_path is not None else None,
            "exists": combined_exists,
            "responses": combined_count,
            "error": combined_error,
        },
        "operator_note": (
            "This workflow only inspects saved focused provider/manual response files. It does not call providers, "
            "does not import evidence by itself, and cannot mutate wallet trust or execution."
        ),
    }
    return report
