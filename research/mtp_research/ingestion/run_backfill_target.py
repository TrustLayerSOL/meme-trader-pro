"""Run one bounded historical backfill target."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from research.mtp_research.ingestion.backfill_jobs import BackfillTarget, make_target_id
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest
from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)


def _raw_record_from_body(
    signature: str,
    body: dict,
    target: BackfillTarget,
) -> RawTransactionRecord:
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return RawTransactionRecord(
        signature=signature,
        slot=body.get("slot"),
        block_time=body.get("blockTime"),
        success=(meta.get("err") is None if meta else None),
        address=target.address,
        role=target.role,
        token_mint=target.token_mint,
        fetched_at=datetime.now(timezone.utc),
        raw_json=body,
        metadata_json={"target_id": target.target_id, "source": target.source},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill one v3 research target.")
    parser.add_argument("address")
    parser.add_argument("--role", default="unknown")
    parser.add_argument("--token-mint")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = BackfillTarget(
        target_id=make_target_id(args.address, args.role, args.token_mint),
        address=args.address,
        role=args.role,
        token_mint=args.token_mint,
    )

    try:
        adapter = HeliusHistoricalAdapter.from_env()
    except ValueError as exc:
        print(str(exc))
        return 1

    signature_result = adapter.fetch_signatures_for_address(
        HeliusBackfillRequest(
            address=target.address,
            token_mint=target.token_mint,
            role=target.role,
            limit=args.limit,
            include_failed=args.include_failed,
        )
    )
    signatures = [record.signature for record in signature_result.records]

    if args.dry_run:
        print(f"target_id={target.target_id}")
        print(f"address={target.address}")
        print(f"signatures_seen={len(signatures)}")
        print(f"next_before={signature_result.next_before}")
        for signature in signatures:
            print(f"signature={signature}")
        return 0

    bodies = adapter.fetch_transactions(signatures)
    raw_records = [
        _raw_record_from_body(signature, body, target)
        for signature, body in zip(signatures, bodies, strict=False)
        if body
    ]
    store = RawTransactionStore()
    counts = store.upsert_many(raw_records)

    print(f"target_id={target.target_id}")
    print(f"address={target.address}")
    print(f"signatures_seen={len(signatures)}")
    print(f"transactions_fetched={len(raw_records)}")
    print(f"inserted={counts['inserted']}")
    print(f"updated={counts['updated']}")
    print(f"next_before={signature_result.next_before}")
    print(f"output_path={store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
