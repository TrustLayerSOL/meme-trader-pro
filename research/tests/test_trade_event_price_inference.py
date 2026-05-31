from research.mtp_research.ingestion.trade_event_normalizer import TradeEventNormalizer
from research.mtp_research.ingestion.trade_normalization_models import TradeFlow, WSOL_MINT
from research.mtp_research.ingestion.transaction_parser_models import NativeBalanceDelta, TransactionSummary


BASE_MINT = "BaseMint111111111111111111111111111111111111"


def _summary() -> TransactionSummary:
    return TransactionSummary(
        signature="sig-price",
        slot=1,
        block_time=100,
        success=True,
        fee_lamports=5000,
        accounts=[],
        programs=[],
        token_balance_deltas=[],
    )


def _summary_with_native_quote(delta_sol: float) -> TransactionSummary:
    return TransactionSummary(
        signature="sig-native-price",
        slot=1,
        block_time=100,
        success=True,
        fee_lamports=5000,
        accounts=[],
        programs=[],
        token_balance_deltas=[],
        native_balance_deltas=[
            NativeBalanceDelta(
                account="acct-1",
                owner=None,
                pre_lamports=2_000_000_000,
                post_lamports=int(2_000_000_000 + delta_sol * 1_000_000_000),
                delta_lamports=int(delta_sol * 1_000_000_000),
            )
        ],
    )


def _flow(side="possible_buy", base=10.0, quote=-2.0, reasons=None):
    return TradeFlow(
        owner="owner-1",
        base_mint=BASE_MINT,
        quote_mint=WSOL_MINT,
        base_delta=base,
        quote_delta=quote,
        inferred_side=side,
        confidence=0.7,
        reasons=reasons or [],
    )


def test_possible_buy_gets_price_quote_from_base_and_quote_quantities() -> None:
    event = TradeEventNormalizer().flow_to_normalized_event(_summary(), _flow("possible_buy", 10, -2), 0)

    assert event.price_quote == 0.2
    assert event.metadata_json["price_inference_method"] == "balance_delta_quote_over_base_v0"


def test_possible_sell_gets_price_quote_from_base_and_quote_quantities() -> None:
    event = TradeEventNormalizer().flow_to_normalized_event(_summary(), _flow("possible_sell", -10, 2), 0)

    assert event.price_quote == 0.2
    assert event.metadata_json["price_inference_method"] == "balance_delta_quote_over_base_v0"


def test_missing_or_zero_quantities_do_not_infer_price() -> None:
    normalizer = TradeEventNormalizer()

    assert normalizer.flow_to_normalized_event(_summary(), _flow(base=0, quote=-2), 0).price_quote is None
    assert normalizer.flow_to_normalized_event(_summary(), _flow(base=10, quote=None), 0).price_quote is None


def test_ambiguous_flow_does_not_get_fake_precision() -> None:
    event = TradeEventNormalizer().flow_to_normalized_event(
        _summary(),
        _flow(reasons=["multiple_token_deltas"]),
        0,
    )

    assert event.price_quote is None
    assert "ambiguous_price_inference" in event.metadata_json["reasons"]


def test_base_only_flow_gets_diagnostic_native_sol_price_proxy() -> None:
    event = TradeEventNormalizer().flow_to_normalized_event(
        _summary_with_native_quote(-2.0),
        _flow(side="accumulation", base=10, quote=None),
        0,
    )

    assert event.price_quote == 0.2
    assert event.quote_qty == 2.0
    assert event.metadata_json["quote_mint"] == "native_sol"
    assert event.metadata_json["price_inference_method"] == "transaction_native_sol_quote_over_base_v0"
    assert "native_sol_quote_proxy" in event.metadata_json["reasons"]
