from research.mtp_research.ingestion.trade_event_normalizer import TradeEventNormalizer
from research.mtp_research.ingestion.trade_normalization_models import WSOL_MINT
from research.mtp_research.ingestion.transaction_parser_models import (
    TokenBalanceDelta,
    TransactionSummary,
    VenueClassification,
)


BASE_MINT = "BaseMint111111111111111111111111111111111111"
OTHER_BASE_MINT = "OtherBase1111111111111111111111111111111111"


def _delta(owner: str, mint: str, amount: float) -> TokenBalanceDelta:
    return TokenBalanceDelta(
        owner=owner,
        account=f"{owner}-{mint}",
        mint=mint,
        pre_amount=None,
        post_amount=None,
        delta=amount,
        decimals=6,
    )


def _summary(deltas: list[TokenBalanceDelta]) -> TransactionSummary:
    return TransactionSummary(
        signature="sig-1",
        slot=1,
        block_time=100,
        success=True,
        fee_lamports=5000,
        accounts=[],
        programs=[],
        token_balance_deltas=deltas,
        venue_classification=VenueClassification(
            venue="unknown_token_swap_candidate",
            confidence=0.3,
            reasons=["token_balance_deltas_present_without_known_venue"],
        ),
    )


def test_positive_base_negative_quote_infers_possible_buy() -> None:
    normalizer = TradeEventNormalizer()
    flows = normalizer.infer_trade_flows(
        _summary([_delta("owner-1", BASE_MINT, 10), _delta("owner-1", WSOL_MINT, -2)])
    )

    assert len(flows) == 1
    assert flows[0].inferred_side == "possible_buy"
    assert flows[0].base_mint == BASE_MINT
    assert flows[0].quote_mint == WSOL_MINT
    assert flows[0].confidence == 0.7


def test_negative_base_positive_quote_infers_possible_sell() -> None:
    normalizer = TradeEventNormalizer()
    flows = normalizer.infer_trade_flows(
        _summary([_delta("owner-1", BASE_MINT, -10), _delta("owner-1", WSOL_MINT, 2)])
    )

    assert len(flows) == 1
    assert flows[0].inferred_side == "possible_sell"


def test_positive_base_only_infers_accumulation() -> None:
    flows = TradeEventNormalizer().infer_trade_flows(
        _summary([_delta("owner-1", BASE_MINT, 10)])
    )

    assert len(flows) == 1
    assert flows[0].inferred_side == "accumulation"
    assert flows[0].confidence == 0.35


def test_negative_base_only_infers_distribution() -> None:
    flows = TradeEventNormalizer().infer_trade_flows(
        _summary([_delta("owner-1", BASE_MINT, -10)])
    )

    assert len(flows) == 1
    assert flows[0].inferred_side == "distribution"
    assert flows[0].confidence == 0.35


def test_only_quote_deltas_emit_no_flow() -> None:
    flows = TradeEventNormalizer().infer_trade_flows(
        _summary([_delta("owner-1", WSOL_MINT, 2)])
    )

    assert flows == []


def test_target_token_mint_filters_unrelated_flows() -> None:
    flows = TradeEventNormalizer().infer_trade_flows(
        _summary(
            [
                _delta("owner-1", BASE_MINT, 10),
                _delta("owner-1", WSOL_MINT, -2),
                _delta("owner-2", OTHER_BASE_MINT, 5),
                _delta("owner-2", WSOL_MINT, -1),
            ]
        ),
        target_token_mint=BASE_MINT,
    )

    assert len(flows) == 1
    assert flows[0].base_mint == BASE_MINT


def test_flow_to_event_calculates_price_quote() -> None:
    normalizer = TradeEventNormalizer()
    summary = _summary([_delta("owner-1", BASE_MINT, 10), _delta("owner-1", WSOL_MINT, -2)])
    flow = normalizer.infer_trade_flows(summary)[0]

    event = normalizer.flow_to_normalized_event(summary, flow, index=0)

    assert event.event_type == "possible_buy"
    assert event.side == "buy"
    assert event.base_qty == 10
    assert event.quote_qty == 2
    assert event.price_quote == 0.2
    assert event.metadata_json["confidence"] == 0.7
    assert event.metadata_json["reasons"] == [
        "positive_base_delta",
        "negative_quote_delta",
    ]
    assert event.metadata_json["parser_version"] == "trade_event_normalizer_v0"


def test_flow_to_event_stores_venue_evidence_metadata() -> None:
    normalizer = TradeEventNormalizer()
    summary = _summary([_delta("owner-1", BASE_MINT, 10), _delta("owner-1", WSOL_MINT, -2)])
    summary.venue_classification = VenueClassification(
        venue="pumpfun_buy",
        confidence=0.95,
        matched_program_ids=["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"],
        reasons=["matched_pumpfun_program_id_and_buy_instruction_log"],
    )
    summary.raw_record_role = "pumpfun_bonding_curve_lifecycle_2h"
    summary.raw_record_token_mint = BASE_MINT
    summary.raw_record_source = "helius_rpc"
    summary.raw_record_address = "curve-1"
    summary.raw_record_metadata_json = {"collection_method": "address_window"}
    flow = normalizer.infer_trade_flows(summary)[0]

    event = normalizer.flow_to_normalized_event(summary, flow, index=0)

    assert event.venue == "pumpfun_buy"
    assert event.metadata_json["venue_confidence"] == 0.95
    assert event.metadata_json["venue_reasons"] == ["matched_pumpfun_program_id_and_buy_instruction_log"]
    assert event.metadata_json["venue_matched_program_ids"] == ["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"]
    assert event.metadata_json["raw_record_role"] == "pumpfun_bonding_curve_lifecycle_2h"
    assert event.metadata_json["raw_record_token_mint"] == BASE_MINT
    assert event.metadata_json["raw_record_source"] == "helius_rpc"
    assert event.metadata_json["raw_record_address"] == "curve-1"
    assert event.metadata_json["raw_record_metadata_json"] == {"collection_method": "address_window"}


def test_multiple_token_deltas_lower_confidence_and_add_reason() -> None:
    flows = TradeEventNormalizer().infer_trade_flows(
        _summary(
            [
                _delta("owner-1", BASE_MINT, 10),
                _delta("owner-1", OTHER_BASE_MINT, 3),
                _delta("owner-1", WSOL_MINT, -2),
            ]
        )
    )

    assert len(flows) == 1
    assert flows[0].base_mint == BASE_MINT
    assert flows[0].confidence == 0.5
    assert "multiple_token_deltas" in flows[0].reasons


def test_normalize_summary_reports_emitted_flows() -> None:
    summary = _summary([_delta("owner-1", BASE_MINT, 10), _delta("owner-1", WSOL_MINT, -2)])
    result = TradeEventNormalizer().normalize_summary(summary)

    assert result.signature == "sig-1"
    assert result.venue == "unknown_token_swap_candidate"
    assert len(result.flows) == 1
    assert result.emitted_events == 1
