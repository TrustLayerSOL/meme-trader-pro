"""Offline diagnostics for v3 evidence population runs."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.pipeline.evidence_audit_models import (
    EvidenceAuditReport,
    EvidenceDropoff,
    EvidenceStoreCount,
    TargetQualitySummary,
    make_evidence_audit_report_id,
)
from research.mtp_research.pipeline.real_candidate_filter import is_mock_candidate_row


STORE_SEQUENCE = [
    ("candidate_registry", "data/normalized/candidate_registry.jsonl"),
    ("backfill_targets_plan", "data/backtests/backfill_targets_plan.jsonl"),
    ("raw_transactions", "data/raw/helius_transactions.jsonl"),
    ("normalized_events", "data/normalized/events.jsonl"),
    ("feature_snapshots", "data/features/feature_snapshots.jsonl"),
    ("outcome_labels", "data/backtests/outcome_labels.jsonl"),
    ("research_dataset", "data/backtests/research_dataset.jsonl"),
    ("rule_backtest_results", "data/backtests/rule_backtest_results.jsonl"),
    ("walk_forward_results", "data/backtests/walk_forward_results.jsonl"),
    ("thesis_decisions", "data/backtests/thesis_decisions.jsonl"),
]

TRADE_LIKE_EVENT_TYPES = {
    "possible_buy",
    "possible_sell",
    "accumulation",
    "distribution",
}


class EvidenceAuditor:
    """Audit local JSONL artifacts without network calls."""

    def __init__(self, paths: dict[str, Path | str] | None = None):
        overrides = paths or {}
        self.paths = {
            name: Path(overrides.get(name, default_path))
            for name, default_path in STORE_SEQUENCE
        }

    def count_jsonl(self, path: Path | str) -> EvidenceStoreCount:
        jsonl_path = Path(path)
        warning_flags: list[str] = []
        if not jsonl_path.exists():
            return EvidenceStoreCount(
                name=jsonl_path.stem,
                path=str(jsonl_path),
                exists=False,
                warning_flags=["missing_file"],
            )

        row_count = 0
        malformed_count = 0
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    json.loads(text)
                    row_count += 1
                except json.JSONDecodeError:
                    malformed_count += 1

        if malformed_count:
            warning_flags.append("malformed_jsonl_lines")

        return EvidenceStoreCount(
            name=jsonl_path.stem,
            path=str(jsonl_path),
            exists=True,
            row_count=row_count,
            file_size_bytes=jsonl_path.stat().st_size,
            warning_flags=warning_flags,
        )

    def load_jsonl_rows(self, path: Path | str) -> list[dict[str, Any]]:
        jsonl_path = Path(path)
        if not jsonl_path.exists():
            return []

        rows: list[dict[str, Any]] = []
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def audit_target_quality(
        self,
        candidate_rows: list[dict[str, Any]],
        target_rows: list[dict[str, Any]],
    ) -> TargetQualitySummary:
        role_counts = Counter(str(row.get("role", "unknown")) for row in target_rows)
        candidates_with_pool_address = sum(1 for row in candidate_rows if row.get("pool_address"))
        candidates_with_creator_wallet = sum(1 for row in candidate_rows if row.get("creator_wallet"))
        candidate_count = len(candidate_rows)
        target_count = len(target_rows)

        token_mints_with_pool_or_creator = {
            str(row.get("token_mint"))
            for row in candidate_rows
            if row.get("pool_address") or row.get("creator_wallet")
        }
        mint_only_candidate_count = sum(
            1
            for row in candidate_rows
            if row.get("token_mint") and str(row.get("token_mint")) not in token_mints_with_pool_or_creator
        )

        warning_flags: list[str] = []
        if target_count and set(role_counts) == {"mint"}:
            warning_flags.append("mint_only_targets")
        if candidate_count and candidates_with_pool_address == 0:
            warning_flags.append("missing_pool_addresses")
        if candidate_count and candidates_with_creator_wallet == 0:
            warning_flags.append("missing_creator_wallets")
        if candidate_count and target_count <= candidate_count:
            warning_flags.append("low_targets_per_candidate")
        if any(is_mock_candidate_row(row) for row in candidate_rows):
            warning_flags.append("mock_candidates_present")

        return TargetQualitySummary(
            target_count=target_count,
            role_counts=dict(sorted(role_counts.items())),
            targets_with_token_mint=sum(1 for row in target_rows if row.get("token_mint")),
            targets_with_pool_role=role_counts.get("pool", 0),
            targets_with_creator_role=role_counts.get("creator", 0),
            targets_with_wallet_role=role_counts.get("wallet", 0),
            mint_only_candidate_count=mint_only_candidate_count,
            candidates_with_pool_address=candidates_with_pool_address,
            candidates_with_creator_wallet=candidates_with_creator_wallet,
            warning_flags=warning_flags,
            metadata_json={"candidate_count": candidate_count},
        )

    def count_event_types(self, events_rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = Counter(str(row.get("event_type", "unknown")) for row in events_rows)
        return dict(sorted(counts.items()))

    def count_label_quality(
        self,
        outcome_rows: list[dict[str, Any]],
        dataset_rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for row in outcome_rows:
            counts[str(row.get("label_quality") or row.get("quality") or "unknown")] += 1
        for row in dataset_rows:
            counts[str(row.get("label_quality") or row.get("outcome_label_quality") or "unknown")] += 1
        return dict(sorted(counts.items()))

    def count_thesis_recommendations(self, decision_rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = Counter(str(row.get("recommended_status", "unknown")) for row in decision_rows)
        return dict(sorted(counts.items()))

    def calculate_dropoffs(self, store_counts: list[EvidenceStoreCount]) -> list[EvidenceDropoff]:
        by_name = {count.name: count for count in store_counts}
        dropoffs: list[EvidenceDropoff] = []
        for (from_stage, _), (to_stage, _) in zip(STORE_SEQUENCE, STORE_SEQUENCE[1:], strict=False):
            from_count = by_name.get(from_stage, EvidenceStoreCount(from_stage, "", False)).row_count
            to_count = by_name.get(to_stage, EvidenceStoreCount(to_stage, "", False)).row_count
            retained_ratio = to_count / from_count if from_count > 0 else None
            warning_flags: list[str] = []
            if from_count == 0:
                warning_flags.append("missing_source_stage")
            if from_count > 0 and to_count == 0:
                warning_flags.append("empty_to_stage")
            if retained_ratio is not None and retained_ratio < 0.25 and from_count >= 10:
                warning_flags.append("large_dropoff")
            dropoffs.append(
                EvidenceDropoff(
                    from_stage=from_stage,
                    to_stage=to_stage,
                    from_count=from_count,
                    to_count=to_count,
                    retained_ratio=retained_ratio,
                    dropped_count=max(from_count - to_count, 0),
                    warning_flags=warning_flags,
                )
            )
        return dropoffs

    def infer_bottleneck(self, report: EvidenceAuditReport) -> str | None:
        counts = {count.name: count.row_count for count in report.store_counts}
        candidate_count = counts.get("candidate_registry", 0)
        target_count = counts.get("backfill_targets_plan", 0)
        raw_count = counts.get("raw_transactions", 0)
        event_count = counts.get("normalized_events", 0)
        feature_count = counts.get("feature_snapshots", 0)
        outcome_count = counts.get("outcome_labels", 0)
        dataset_count = counts.get("research_dataset", 0)
        walk_count = counts.get("walk_forward_results", 0)
        thesis_count = counts.get("thesis_decisions", 0)
        target_warnings = report.target_quality.warning_flags if report.target_quality else []

        if candidate_count == 0:
            return "candidate_registry_empty"
        if target_count == 0 and candidate_count > 0:
            return "no_backfill_targets"
        if raw_count == 0 and target_count > 0 and "mint_only_targets" in target_warnings:
            return "low_value_backfill_targets"
        if raw_count == 0 and target_count > 0:
            return "no_raw_transactions"
        if event_count == 0 and raw_count > 0:
            return "parser_coverage"
        if not any(report.event_type_counts.get(event_type, 0) for event_type in TRADE_LIKE_EVENT_TYPES) and event_count > 0:
            return "trade_event_inference"
        if feature_count == 0 and event_count > 0:
            return "feature_snapshot_builder"
        if outcome_count == 0 and feature_count > 0:
            return "outcome_labeling_or_price_proxy"
        if dataset_count == 0 and outcome_count > 0:
            return "dataset_join"
        if walk_count > 0 and thesis_count > 0 and set(report.thesis_recommendation_counts) == {"needs_more_data"}:
            return "insufficient_test_evidence"
        return "unknown_or_needs_more_data"

    def recommend_next_actions(self, report: EvidenceAuditReport) -> list[str]:
        actions = {
            "candidate_registry_empty": ["seed real candidate tokens or enable real discovery ingestors"],
            "no_backfill_targets": ["add pool_address/creator_wallet to candidate seeds or fix target planner"],
            "low_value_backfill_targets": [
                "seed candidates with pool_address and creator_wallet",
                "avoid mint-only evidence runs until target quality improves",
            ],
            "no_raw_transactions": [
                "inspect target plan and verify target addresses are real high-value addresses",
                "run one direct Helius probe on a known pool or creator address",
            ],
            "parser_coverage": ["inspect raw jsonParsed transaction shape and extend parser"],
            "trade_event_inference": ["inspect token balance deltas and quote mint detection"],
            "feature_snapshot_builder": ["check event block_time/token_mint presence"],
            "outcome_labeling_or_price_proxy": ["check price_quote availability and future event density"],
            "dataset_join": ["check snapshot_id joins and label generation"],
            "insufficient_test_evidence": ["run larger bounded backfill only after target quality is confirmed"],
            "unknown_or_needs_more_data": ["inspect generated reports manually"],
        }
        selected_actions = list(
            actions.get(report.bottleneck_stage or "unknown_or_needs_more_data", actions["unknown_or_needs_more_data"])
        )
        if report.metadata_json.get("mock_candidate_count", 0):
            selected_actions.append("run real-only dataset/report filters")
        return selected_actions

    def build_report(self) -> EvidenceAuditReport:
        store_counts = []
        for name, path in self.paths.items():
            count = self.count_jsonl(path)
            count.name = name
            store_counts.append(count)

        candidate_rows = self.load_jsonl_rows(self.paths["candidate_registry"])
        target_rows = self.load_jsonl_rows(self.paths["backfill_targets_plan"])
        events_rows = self.load_jsonl_rows(self.paths["normalized_events"])
        outcome_rows = self.load_jsonl_rows(self.paths["outcome_labels"])
        dataset_rows = self.load_jsonl_rows(self.paths["research_dataset"])
        decision_rows = self.load_jsonl_rows(self.paths["thesis_decisions"])
        real_candidate_count = sum(1 for row in candidate_rows if not is_mock_candidate_row(row))
        mock_candidate_count = sum(1 for row in candidate_rows if is_mock_candidate_row(row))
        real_token_mints = {
            str(row.get("token_mint"))
            for row in candidate_rows
            if row.get("token_mint") and not is_mock_candidate_row(row)
        }
        real_research_dataset_row_count = sum(
            1 for row in dataset_rows if row.get("token_mint") in real_token_mints
        )

        report = EvidenceAuditReport(
            report_id=make_evidence_audit_report_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            store_counts=store_counts,
            dropoffs=self.calculate_dropoffs(store_counts),
            target_quality=self.audit_target_quality(candidate_rows, target_rows),
            event_type_counts=self.count_event_types(events_rows),
            label_quality_counts=self.count_label_quality(outcome_rows, dataset_rows),
            thesis_recommendation_counts=self.count_thesis_recommendations(decision_rows),
            metadata_json={
                "real_candidate_count": real_candidate_count,
                "mock_candidate_count": mock_candidate_count,
                "real_research_dataset_row_count": real_research_dataset_row_count,
            },
        )
        report.bottleneck_stage = self.infer_bottleneck(report)
        report.top_warnings = _top_warnings(report)
        report.recommended_next_actions = self.recommend_next_actions(report)
        return report

    def build_report_from_counts(
        self,
        counts: dict[str, int],
        target_warnings: list[str] | None = None,
        event_type_counts: dict[str, int] | None = None,
        thesis_counts: dict[str, int] | None = None,
    ) -> EvidenceAuditReport:
        store_counts = [
            EvidenceStoreCount(name=name, path=path, exists=True, row_count=counts.get(name, 0))
            for name, path in STORE_SEQUENCE
        ]
        return EvidenceAuditReport(
            report_id="test-report",
            created_at=datetime.now(timezone.utc).isoformat(),
            store_counts=store_counts,
            target_quality=TargetQualitySummary(warning_flags=target_warnings or []),
            event_type_counts=event_type_counts or {},
            thesis_recommendation_counts=thesis_counts or {},
        )


def _top_warnings(report: EvidenceAuditReport) -> list[str]:
    warnings: list[str] = []
    if report.target_quality:
        warnings.extend(report.target_quality.warning_flags)
    for count in report.store_counts:
        warnings.extend(f"{count.name}:{warning}" for warning in count.warning_flags)
    for dropoff in report.dropoffs:
        warnings.extend(f"{dropoff.from_stage}->{dropoff.to_stage}:{warning}" for warning in dropoff.warning_flags)
    return list(dict.fromkeys(warnings))[:10]
