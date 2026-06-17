"""Event-first bridge for T007 collector artifacts.

This is the production write path used at the collector boundary: raw source
rows are normalized and synchronously written into SQLite before JSONL/CSV
compatibility artifacts are emitted. JSONL remains useful for inspection, but
SQLite owns the canonical lifecycle truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Mapping
import sqlite3

from .t007_birth_verification import verify_birth_candidate
from .t007_event_store import T007EventStore
from .t007_protocol_codecs import event_hash
from .t007_retry_classification import classify_curve_probe


@dataclass(frozen=True)
class ArtifactEventMapping:
    event_type: str | None
    source_lane: str
    decision_time_safe: bool
    replay_source: bool = False


class T007ProductionEventFirstWriter:
    def __init__(self, output_root: str | Path, *, db_name: str = "t007_lifecycle_state.sqlite") -> None:
        self.output_root = Path(output_root)
        self.db_path = self.output_root / db_name
        self.output_root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            T007EventStore.initialize_schema(connection)

    def record_artifact_row(self, filename: str, row: Mapping[str, Any], *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        enriched = self.enrich_row(filename, row, context=context)
        with sqlite3.connect(self.db_path) as connection:
            T007EventStore.initialize_schema(connection)
            T007EventStore.insert_raw_envelope_on_connection(connection, self.raw_envelope(filename, enriched, context=context))
            domain = self.domain_event(filename, enriched, context=context)
            if domain is not None:
                T007EventStore.insert_domain_event_on_connection(connection, domain)
            connection.commit()
        return enriched

    def enrich_row(self, filename: str, row: Mapping[str, Any], *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        ctx = dict(context or {})
        out = dict(row or {})
        run_id = out.get("collector_run_id") or out.get("run_id") or ctx.get("collector_run_id") or ctx.get("run_id")
        out.setdefault("collector_run_id", run_id)
        out.setdefault("run_id", run_id)
        out.setdefault("source_received_at", out.get("received_at") or out.get("created_at") or time())
        out.setdefault("feature_observed_at", out.get("collector_observed_at") or out.get("source_received_at") or time())
        out.setdefault("source_artifact", filename)
        if filename.endswith("migration_backfill_jobs.jsonl") or "migration_backfill" in filename:
            out.setdefault("campaign_start_time", ctx.get("campaign_start_time") or ctx.get("source_start_time") or ctx.get("wall_clock_source_start"))
            out.setdefault("campaign_end_time", ctx.get("campaign_end_time") or ctx.get("source_end_time") or ctx.get("wall_clock_source_stop"))
            out.setdefault("source_duration_seconds", ctx.get("source_duration_seconds") or ctx.get("requested_source_duration_seconds"))
            out.setdefault("watcher_window_id", ctx.get("watcher_window_id") or run_id)
            out.setdefault("originating_run_id", ctx.get("originating_run_id") or run_id)
            out["decision_time_safe"] = False
            out["replay_source"] = True
        domain = self.domain_event(filename, out, context=ctx)
        if domain is not None:
            out.setdefault("event_type", domain["event_type"])
            out.setdefault("decision_time_safe", domain["decision_time_safe"])
            out.setdefault("replay_source", domain["replay_source"])
            out.setdefault("event_id", domain["event_id"])
        return out

    def raw_envelope(self, filename: str, row: Mapping[str, Any], *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        ctx = dict(context or {})
        lane = self.infer_source_lane(filename, row)
        envelope = dict(row)
        envelope.update({
            "lane": lane,
            "collector_run_id": row.get("collector_run_id") or ctx.get("collector_run_id") or ctx.get("run_id"),
            "source_route": row.get("source_route") or lane,
            "received_at": row.get("source_received_at") or time(),
            "pool_address": row.get("pool_address") or row.get("pool_or_pair_address"),
        })
        envelope.setdefault("envelope_id", event_hash({**envelope, "event_type": f"raw:{filename}"}))
        return envelope

    def domain_event(self, filename: str, row: Mapping[str, Any], *, context: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        ctx = dict(context or {})
        event_type: str | None = None
        decision_safe = False
        replay = bool(row.get("replay_source"))
        fn = filename.lower()
        payload = dict(row)
        if "birth" in fn or "launch" in fn or "create" in fn:
            result = verify_birth_candidate(row)
            payload.update(result.normalized)
            payload["birth_verification_status"] = result.status
            payload["birth_verification_reasons"] = list(result.reasons)
            event_type = "pump_birth_verified" if result.verified else "pump_birth_rejected"
            decision_safe = result.verified
        elif "curve" in fn or "progress" in fn or "observation" in fn:
            classification = classify_curve_probe(row)
            event_type = classification.event_type
            payload["curve_probe_status"] = classification.status
            payload["curve_probe_final"] = classification.final
            payload["curve_probe_reason"] = classification.reason
            if classification.retry_after_ms is not None:
                payload["retry_after_ms"] = classification.retry_after_ms
            decision_safe = event_type == "curve_state_decoded"
        elif "trade" in fn or "flow" in fn:
            event_type = "trade_flow_window_updated"
            decision_safe = True
        elif "holder" in fn or "dev" in fn or "organic" in fn:
            event_type = "holder_dev_snapshot_seen"
            decision_safe = True
        elif "threshold" in fn:
            event_type = "progress_threshold_crossed" if row.get("threshold_crossed", True) is not False else "progress_threshold_evaluated"
            decision_safe = True
        elif "global_migration" in fn or "migration" in fn or "pumpswap" in fn or "pool" in fn:
            if "backfill" in fn:
                event_type = "replay_birth_context_seen"
                replay = True
                decision_safe = False
            else:
                pool = row.get("pool_address") or row.get("pool_or_pair_address")
                quote = row.get("quote_asset") or row.get("quote_mint")
                event_type = "pumpswap_pool_verified" if pool and quote else "pumpswap_pool_seen"
                decision_safe = bool(pool and quote)
        elif "quote" in fn:
            strict_quote = bool(row.get("quote_timestamp") or row.get("quote_observed_at") or row.get("feature_observed_at")) and bool(row.get("price_impact_bps") is not None or row.get("expected_output_amount") is not None)
            event_type = "quote_observation_seen"
            decision_safe = strict_quote
            payload["quote_status"] = "verified" if strict_quote else "partial"
        elif "depth" in fn or "post_migration" in fn:
            ready = bool(row.get("pool_address") or row.get("pool_or_pair_address")) and bool(row.get("base_reserve") is not None or row.get("quote_reserve") is not None or row.get("liquidity_usd") is not None)
            event_type = "post_migration_depth_seen"
            decision_safe = ready
            payload["post_migration_pool_status"] = "verified" if ready else "partial"
        if event_type is None:
            return None
        payload.update({
            "event_type": event_type,
            "collector_run_id": row.get("collector_run_id") or row.get("run_id") or ctx.get("collector_run_id") or ctx.get("run_id"),
            "source_route": row.get("source_route") or self.infer_source_lane(filename, row),
            "source_received_at": row.get("source_received_at") or row.get("received_at") or time(),
            "feature_observed_at": row.get("feature_observed_at") or row.get("collector_observed_at") or row.get("source_received_at") or time(),
            "decision_time_safe": bool(decision_safe and not replay),
            "replay_source": bool(replay),
            "live_source": not bool(replay),
            "pool_address": row.get("pool_address") or row.get("pool_or_pair_address"),
        })
        payload.setdefault("event_id", event_hash(payload))
        return payload

    def infer_source_lane(self, filename: str, row: Mapping[str, Any]) -> str:
        fn = filename.lower()
        if "birth" in fn or "launch" in fn or "create" in fn:
            return "pump_transaction_subscribe"
        if "curve" in fn or "progress" in fn or "observation" in fn:
            return "curve_account_subscribe"
        if "global_migration" in fn or "pumpswap" in fn or "pool" in fn or "migration" in fn:
            return "pumpswap_pool_program_subscribe"
        if "quote" in fn or "depth" in fn or "post_migration" in fn:
            return "post_migration_pool_state"
        if "backfill" in fn or "replay" in fn:
            return "bounded_readonly_replay"
        return str(row.get("source_lane") or row.get("source_route") or "artifact_compatibility")

# --- T007_EVENT_BUS_PROOF_HARDENING_V4 --------------------------------------
try:
    from .t007_invariants import check_lifecycle_invariants, feature_status as _t007_feature_status
    from .t007_latency_metrics import derive_basic_latency_fields
    from .t007_protocol_codecs import PUMP_PUBLIC_DOCS_COMMIT
except Exception:  # pragma: no cover
    check_lifecycle_invariants = None
    _t007_feature_status = None
    derive_basic_latency_fields = None
    PUMP_PUBLIC_DOCS_COMMIT = None

if 'T007ProductionEventFirstWriter' in globals():
    _t007_v4_original_enrich_row = T007ProductionEventFirstWriter.enrich_row
    _t007_v4_original_domain_event = T007ProductionEventFirstWriter.domain_event
    _t007_v4_original_record = T007ProductionEventFirstWriter.record_artifact_row

    def _t007_v4_enrich_row(self, filename, row, *, context=None):
        out = _t007_v4_original_enrich_row(self, filename, row, context=context)
        ctx = dict(context or {})
        out.setdefault('observed_commitment', out.get('commitment') or ctx.get('commitment') or 'processed')
        out.setdefault('first_seen_slot', out.get('slot'))
        out.setdefault('first_seen_at', out.get('source_received_at') or out.get('received_at'))
        out.setdefault('confirmed_slot', out.get('confirmed_slot'))
        out.setdefault('confirmed_at', out.get('confirmed_at'))
        out.setdefault('finalized_slot', out.get('finalized_slot'))
        out.setdefault('finalized_at', out.get('finalized_at'))
        out.setdefault('dropped_or_reorged', False)
        if PUMP_PUBLIC_DOCS_COMMIT:
            out.setdefault('parser_git_sha', PUMP_PUBLIC_DOCS_COMMIT)
        if derive_basic_latency_fields is not None:
            out.update({k: v for k, v in derive_basic_latency_fields(out).items() if k not in out})
        if _t007_feature_status is not None:
            for feature, source_key in (
                ('trade_flow', 'trade_flow_available'),
                ('holder_dev', 'holder_dev_available'),
                ('quote', 'quote_ready_verified'),
                ('post_migration_pool', 'post_migration_pool_ready_verified'),
            ):
                status, reason = _t007_feature_status(out.get(source_key), attempted=bool(out.get(f'{feature}_attempted', True)), source_gap=bool(out.get('source_gap')), parser_rejected=bool(out.get('parser_rejected')))
                out.setdefault(f'{feature}_status', status)
                out.setdefault(f'{feature}_null_reason', reason)
        return out

    def _t007_v4_domain_event(self, filename, row, *, context=None):
        event = _t007_v4_original_domain_event(self, filename, row, context=context)
        if event is None:
            return None
        event.setdefault('observed_commitment', row.get('observed_commitment') or row.get('commitment') or 'processed')
        event.setdefault('first_seen_slot', row.get('first_seen_slot') or row.get('slot'))
        event.setdefault('first_seen_at', row.get('first_seen_at') or row.get('source_received_at'))
        event.setdefault('confirmed_slot', row.get('confirmed_slot'))
        event.setdefault('confirmed_at', row.get('confirmed_at'))
        event.setdefault('finalized_slot', row.get('finalized_slot'))
        event.setdefault('finalized_at', row.get('finalized_at'))
        event.setdefault('dropped_or_reorged', bool(row.get('dropped_or_reorged')))
        event.setdefault('codec_version', row.get('codec_version') or 't007_protocol_codecs_v1')
        event.setdefault('parser_git_sha', row.get('parser_git_sha') or PUMP_PUBLIC_DOCS_COMMIT)
        event.setdefault('decode_confidence', row.get('decode_confidence') or ('verified' if event.get('decision_time_safe') else 'partial'))
        return event

    def _t007_v4_record_artifact_row(self, filename, row, *, context=None):
        enriched = _t007_v4_original_record(self, filename, row, context=context)
        try:
            if check_lifecycle_invariants is not None:
                violations = check_lifecycle_invariants(enriched)
                if violations:
                    with sqlite3.connect(self.db_path) as connection:
                        T007EventStore.initialize_schema(connection)
                        for violation in violations:
                            payload = violation.details
                            violation_id = event_hash({'event_type': 'invariant_violation', 'mint': payload.get('mint'), 'signature': payload.get('signature'), 'feature_observed_at': payload.get('feature_observed_at'), 'code': violation.code})
                            connection.execute(
                                "INSERT OR IGNORE INTO lifecycle_invariant_violations (violation_id, collector_run_id, mint, event_id, code, severity, payload_json, inserted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (violation_id, payload.get('collector_run_id') or payload.get('run_id'), payload.get('mint'), payload.get('event_id'), violation.code, violation.severity, json.dumps(payload, sort_keys=True, default=str), _now_iso()),
                            )
                        connection.commit()
        except Exception:
            pass
        return enriched

    def _now_iso():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    T007ProductionEventFirstWriter.enrich_row = _t007_v4_enrich_row
    T007ProductionEventFirstWriter.domain_event = _t007_v4_domain_event
    T007ProductionEventFirstWriter.record_artifact_row = _t007_v4_record_artifact_row

# --- T007_EVENT_BUS_BIRTH_REASON_EXPORT_FIX_V5 ------------------------------
# Keep strict birth rejection reasons visible in compatibility artifacts, not only
# inside the canonical domain event payload.
try:
    from .t007_birth_verification import verify_birth_candidate as _t007_v5_verify_birth_candidate
except Exception:  # pragma: no cover
    _t007_v5_verify_birth_candidate = None

if 'T007ProductionEventFirstWriter' in globals() and _t007_v5_verify_birth_candidate is not None:
    _t007_v5_original_enrich_row = T007ProductionEventFirstWriter.enrich_row

    def _t007_v5_enrich_row(self, filename, row, *, context=None):
        out = _t007_v5_original_enrich_row(self, filename, row, context=context)
        if any(token in str(filename).lower() for token in ('birth', 'launch', 'create')):
            result = _t007_v5_verify_birth_candidate(out)
            out.setdefault('birth_verification_status', result.status)
            out.setdefault('birth_verification_reasons', list(result.reasons))
        return out

    T007ProductionEventFirstWriter.enrich_row = _t007_v5_enrich_row
