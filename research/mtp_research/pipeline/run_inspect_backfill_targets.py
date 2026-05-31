"""CLI for inspecting planned backfill targets without network calls."""

from __future__ import annotations

import argparse

from research.mtp_research.pipeline.evidence_auditor import EvidenceAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local backfill target quality.")
    parser.add_argument("--target-plan-path", default="data/backtests/backfill_targets_plan.jsonl")
    parser.add_argument("--candidate-registry-path", default="data/normalized/candidate_registry.jsonl")
    args = parser.parse_args()

    auditor = EvidenceAuditor()
    candidate_rows = auditor.load_jsonl_rows(args.candidate_registry_path)
    target_rows = auditor.load_jsonl_rows(args.target_plan_path)
    summary = auditor.audit_target_quality(candidate_rows, target_rows)

    print(f"candidate_count={len(candidate_rows)}")
    print(f"target_count={summary.target_count}")
    print(f"role_counts={summary.role_counts}")
    print(f"candidates_with_pool_address={summary.candidates_with_pool_address}")
    print(f"candidates_with_creator_wallet={summary.candidates_with_creator_wallet}")
    for warning in summary.warning_flags:
        print(f"warning={warning}")
    for row in target_rows[:10]:
        print(
            "target "
            f"target_id={row.get('target_id')} "
            f"role={row.get('role')} "
            f"address={row.get('address')} "
            f"token_mint={row.get('token_mint')}"
        )
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
