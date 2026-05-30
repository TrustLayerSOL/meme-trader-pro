#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.archival_mint_snapshot_response_import import normalize_raw_responses, response_id  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


MODE = "PROVIDER_RESPONSE_CHUNK_COMBINE_REVIEW_ONLY"
VERSION = "provider_response_chunk_combine.v1"
DEFAULT_INPUT_GLOB = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "provider_recommended_archival_mint_supply_batch_raw.part*.json"
)
DEFAULT_OUTPUT_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "provider_recommended_archival_mint_supply_batch_raw.json"
)
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_response_chunk_combine_report.json"
)


def read_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def sorted_chunk_paths(input_glob: str | Path) -> list[Path]:
    return [Path(path) for path in sorted(glob.glob(str(input_glob)))]


def build_combined_provider_response_chunks(
    *,
    input_glob: str | Path = DEFAULT_INPUT_GLOB,
    generated_at: float | None = None,
) -> dict[str, Any]:
    chunk_paths = sorted_chunk_paths(input_glob)
    responses: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    invalid_chunks: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    source_files: list[str] = []
    chunk_rows: list[dict[str, Any]] = []

    for path in chunk_paths:
        payload, error = read_json(path)
        if error is not None:
            invalid_chunks.append({"path": relative_path(path, ROOT), "error": error})
            chunk_rows.append({"path": relative_path(path, ROOT), "status": "invalid_json", "responses": 0})
            continue
        normalized = normalize_raw_responses(payload)
        accepted = 0
        duplicates = 0
        for row in normalized:
            rid = response_id(row)
            if not rid:
                continue
            if rid in seen_ids:
                duplicate_ids.append(rid)
                duplicates += 1
                continue
            seen_ids.add(rid)
            responses.append(row)
            accepted += 1
        source_files.append(relative_path(path, ROOT))
        chunk_rows.append(
            {
                "path": relative_path(path, ROOT),
                "status": "combined",
                "responses": accepted,
                "duplicate_response_ids": duplicates,
            }
        )

    response_ids = Counter(response_id(row) for row in responses if response_id(row))
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "provider_calls_performed": False,
        "summary": {
            "chunk_files_scanned": len(chunk_paths),
            "responses_collected": len(responses),
            "unique_response_ids": len(response_ids),
            "duplicate_response_ids": len(duplicate_ids),
            "invalid_chunk_files": len(invalid_chunks),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "combined_response_payload": {
            "responses": responses,
            "source_files": source_files,
            "generated_by": VERSION,
        },
        "chunk_rows": chunk_rows,
        "invalid_chunks": invalid_chunks,
        "duplicate_response_ids": duplicate_ids,
        "operator_note": (
            "This combines saved provider response chunk files only. It performs no provider calls, "
            "imports no evidence by itself, and cannot mutate wallet trust or execution."
        ),
    }


def write_combined_provider_response_chunks(
    *,
    input_glob: str | Path = DEFAULT_INPUT_GLOB,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    output_path = Path(output_path)
    report_path = Path(report_path)
    report = build_combined_provider_response_chunks(input_glob=input_glob, generated_at=generated_at)
    report["input_paths"] = {"input_glob": str(input_glob)}
    report["output_paths"] = {
        "combined_raw_response": relative_path(output_path, ROOT),
        "report": relative_path(report_path, ROOT),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report["combined_response_payload"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine saved provider response chunk files into one import file.")
    parser.add_argument("--input-glob", default=str(DEFAULT_INPUT_GLOB))
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_combined_provider_response_chunks(
        input_glob=args.input_glob,
        output_path=args.output_path,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
