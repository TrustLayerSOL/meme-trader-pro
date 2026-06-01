"""Conservative trade-event normalization from token balance deltas."""

from __future__ import annotations

from collections import defaultdict

from research.mtp_research.ingestion.normalization_models import (
    NormalizedEvent,
    make_event_id,
)
from research.mtp_research.ingestion.trade_normalization_models import (
    KNOWN_QUOTE_MINTS,
    TradeFlow,
    TradeNormalizationResult,
)
from research.mtp_research.ingestion.transaction_parser_models import (
    TokenBalanceDelta,
    TransactionSummary,
)


class TradeEventNormalizer:
    """Infer v0 trade-event candidates from token balance delta patterns."""

    def __init__(self, quote_mints: set[str] | None = None):
        self.quote_mints = quote_mints or set(KNOWN_QUOTE_MINTS)

    def group_deltas_by_owner(
        self,
        summary: TransactionSummary,
    ) -> dict[str, list[TokenBalanceDelta]]:
        grouped: dict[str, list[TokenBalanceDelta]] = defaultdict(list)
        for delta in summary.token_balance_deltas:
            owner_key = delta.owner or delta.account or "unknown"
            grouped[owner_key].append(delta)
        return dict(grouped)

    def infer_trade_flows(
        self,
        summary: TransactionSummary,
        target_token_mint: str | None = None,
    ) -> list[TradeFlow]:
        flows: list[TradeFlow] = []

        for owner, deltas in self.group_deltas_by_owner(summary).items():
            non_quote_deltas = [
                delta for delta in deltas if delta.mint not in self.quote_mints
            ]
            quote_deltas = [delta for delta in deltas if delta.mint in self.quote_mints]
            if target_token_mint:
                non_quote_deltas = [
                    delta for delta in non_quote_deltas if delta.mint == target_token_mint
                ]
            if not non_quote_deltas:
                continue

            reasons: list[str] = []
            confidence = 0.7
            if len(non_quote_deltas) > 1 or len(quote_deltas) > 1:
                confidence = 0.5
                reasons.append("multiple_token_deltas")

            positive_base = _largest_abs_delta(
                [delta for delta in non_quote_deltas if _delta_value(delta) > 0]
            )
            negative_base = _largest_abs_delta(
                [delta for delta in non_quote_deltas if _delta_value(delta) < 0]
            )
            positive_quote = _largest_abs_delta(
                [delta for delta in quote_deltas if _delta_value(delta) > 0]
            )
            negative_quote = _largest_abs_delta(
                [delta for delta in quote_deltas if _delta_value(delta) < 0]
            )

            flow = self._infer_owner_flow(
                owner=owner,
                positive_base=positive_base,
                negative_base=negative_base,
                positive_quote=positive_quote,
                negative_quote=negative_quote,
                base_reasons=reasons,
                base_confidence=confidence,
            )
            if flow:
                flows.append(flow)

        return flows

    def flow_to_normalized_event(
        self,
        summary: TransactionSummary,
        flow: TradeFlow,
        index: int,
    ) -> NormalizedEvent:
        event_type = _event_type_for_side(flow.inferred_side)
        side = _event_side_for_inferred_side(flow.inferred_side)
        reasons = list(flow.reasons)
        price_quote = _infer_price_quote(flow, reasons)
        price_inference_method = "balance_delta_quote_over_base_v0" if price_quote is not None else None
        quote_qty = abs(flow.quote_delta) if flow.quote_delta is not None else None
        quote_mint = flow.quote_mint
        if price_quote is None:
            native_quote_qty = _infer_native_quote_qty(summary, flow, reasons)
            if native_quote_qty is not None and flow.base_delta:
                quote_qty = native_quote_qty
                quote_mint = "native_sol"
                price_quote = native_quote_qty / abs(flow.base_delta)
                price_inference_method = "transaction_native_sol_quote_over_base_v0"

        venue = summary.venue_classification.venue if summary.venue_classification else None
        venue_confidence = (
            summary.venue_classification.confidence if summary.venue_classification else None
        )
        venue_reasons = summary.venue_classification.reasons if summary.venue_classification else []
        venue_matched_program_ids = (
            summary.venue_classification.matched_program_ids if summary.venue_classification else []
        )

        return NormalizedEvent(
            event_id=make_event_id(summary.signature, event_type, index=index),
            signature=summary.signature,
            slot=summary.slot,
            block_time=summary.block_time,
            event_type=event_type,
            token_mint=flow.base_mint,
            venue=venue,
            actor=flow.owner,
            side=side,
            base_qty=abs(flow.base_delta) if flow.base_delta is not None else None,
            quote_qty=quote_qty,
            price_quote=price_quote,
            source="trade_event_normalizer_v0",
            metadata_json={
                "quote_mint": quote_mint,
                "confidence": flow.confidence,
                "reasons": reasons,
                "venue_confidence": venue_confidence,
                "venue_reasons": venue_reasons,
                "venue_matched_program_ids": venue_matched_program_ids,
                "raw_record_address": summary.raw_record_address,
                "raw_record_role": summary.raw_record_role,
                "raw_record_token_mint": summary.raw_record_token_mint,
                "raw_record_source": summary.raw_record_source,
                "raw_record_metadata_json": summary.raw_record_metadata_json,
                "source_signature": summary.signature,
                "parser_version": "trade_event_normalizer_v0",
                "price_inference_method": price_inference_method,
                **flow.metadata_json,
            },
        )

    def normalize_summary(
        self,
        summary: TransactionSummary,
        target_token_mint: str | None = None,
    ) -> TradeNormalizationResult:
        flows = self.infer_trade_flows(summary, target_token_mint=target_token_mint)
        venue = summary.venue_classification.venue if summary.venue_classification else None
        return TradeNormalizationResult(
            signature=summary.signature,
            slot=summary.slot,
            block_time=summary.block_time,
            venue=venue,
            flows=flows,
            emitted_events=len(flows),
            metadata_json={
                "parser_version": "trade_event_normalizer_v0",
                "target_token_mint": target_token_mint,
            },
        )

    def _infer_owner_flow(
        self,
        owner: str,
        positive_base: TokenBalanceDelta | None,
        negative_base: TokenBalanceDelta | None,
        positive_quote: TokenBalanceDelta | None,
        negative_quote: TokenBalanceDelta | None,
        base_reasons: list[str],
        base_confidence: float,
    ) -> TradeFlow | None:
        if positive_base and negative_quote:
            return self._build_flow(
                owner,
                positive_base,
                negative_quote,
                "possible_buy",
                base_confidence,
                [*base_reasons, "positive_base_delta", "negative_quote_delta"],
            )
        if negative_base and positive_quote:
            return self._build_flow(
                owner,
                negative_base,
                positive_quote,
                "possible_sell",
                base_confidence,
                [*base_reasons, "negative_base_delta", "positive_quote_delta"],
            )
        if positive_base:
            return self._build_flow(
                owner,
                positive_base,
                None,
                "accumulation",
                min(base_confidence, 0.35),
                [*base_reasons, "positive_base_delta_without_quote_match"],
            )
        if negative_base:
            return self._build_flow(
                owner,
                negative_base,
                None,
                "distribution",
                min(base_confidence, 0.35),
                [*base_reasons, "negative_base_delta_without_quote_match"],
            )
        return None

    def _build_flow(
        self,
        owner: str,
        base_delta: TokenBalanceDelta,
        quote_delta: TokenBalanceDelta | None,
        inferred_side: str,
        confidence: float,
        reasons: list[str],
    ) -> TradeFlow:
        return TradeFlow(
            owner=owner,
            base_mint=base_delta.mint,
            quote_mint=quote_delta.mint if quote_delta else None,
            base_delta=base_delta.delta,
            quote_delta=quote_delta.delta if quote_delta else None,
            inferred_side=inferred_side,
            confidence=confidence,
            reasons=reasons,
        )


def _delta_value(delta: TokenBalanceDelta) -> float:
    return delta.delta or 0.0


def _largest_abs_delta(deltas: list[TokenBalanceDelta]) -> TokenBalanceDelta | None:
    if not deltas:
        return None
    return max(deltas, key=lambda delta: abs(_delta_value(delta)))


def _event_type_for_side(inferred_side: str | None) -> str:
    if inferred_side == "possible_buy":
        return "possible_buy"
    if inferred_side == "possible_sell":
        return "possible_sell"
    if inferred_side == "accumulation":
        return "token_accumulation"
    if inferred_side == "distribution":
        return "token_distribution"
    return "swap_candidate"


def _event_side_for_inferred_side(inferred_side: str | None) -> str:
    if inferred_side == "possible_buy":
        return "buy"
    if inferred_side == "possible_sell":
        return "sell"
    if inferred_side == "accumulation":
        return "accumulate"
    if inferred_side == "distribution":
        return "distribute"
    return "unknown"


def _infer_price_quote(flow: TradeFlow, reasons: list[str]) -> float | None:
    if flow.inferred_side not in {"possible_buy", "possible_sell"}:
        return None
    if "multiple_token_deltas" in reasons:
        reasons.append("ambiguous_price_inference")
        return None
    if flow.base_delta is None or flow.quote_delta is None:
        return None
    if flow.base_delta == 0:
        return None
    quote_qty = abs(flow.quote_delta)
    base_qty = abs(flow.base_delta)
    if base_qty <= 0 or quote_qty <= 0:
        return None
    return quote_qty / base_qty


def _infer_native_quote_qty(summary: TransactionSummary, flow: TradeFlow, reasons: list[str]) -> float | None:
    if flow.inferred_side not in {"accumulation", "distribution"}:
        return None
    if flow.base_delta is None or flow.base_delta == 0:
        return None
    native_deltas = [
        delta
        for delta in summary.native_balance_deltas
        if delta.delta_sol is not None and abs(delta.delta_sol) > 0
    ]
    if not native_deltas:
        return None
    largest = max(native_deltas, key=lambda delta: abs(delta.delta_sol or 0.0))
    quote_qty = abs(largest.delta_sol or 0.0)
    if quote_qty <= 0:
        return None
    reasons.append("native_sol_quote_proxy")
    return quote_qty
