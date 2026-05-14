"""Phase A observability: structured post-mortems, trade classification, rejection logging."""

from analysis.decision_lookup import fetch_stored_decision_payload, hints_from_stored_payload
from analysis.rejection_logger import record_rejection
from analysis.trade_postmortem import (
    append_postmortem_jsonl,
    build_postmortem_record,
    load_postmortem_ids,
)

__all__ = [
    "append_postmortem_jsonl",
    "build_postmortem_record",
    "fetch_stored_decision_payload",
    "hints_from_stored_payload",
    "load_postmortem_ids",
    "record_rejection",
]
