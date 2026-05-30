import pytest

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest


def test_build_get_signatures_payload_includes_address_and_limit() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")
    request = HeliusBackfillRequest(address="address-1", limit=25)

    payload = adapter.build_get_signatures_payload(request)

    assert payload["method"] == "getSignaturesForAddress"
    assert payload["params"][0] == "address-1"
    assert payload["params"][1]["limit"] == 25


def test_build_get_signatures_payload_only_includes_before_until_when_provided() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")
    empty_payload = adapter.build_get_signatures_payload(
        HeliusBackfillRequest(address="address-1")
    )

    assert "before" not in empty_payload["params"][1]
    assert "until" not in empty_payload["params"][1]

    payload = adapter.build_get_signatures_payload(
        HeliusBackfillRequest(
            address="address-1",
            before="before-signature",
            until="until-signature",
        )
    )

    assert payload["params"][1]["before"] == "before-signature"
    assert payload["params"][1]["until"] == "until-signature"


def test_parse_signature_rows_converts_rows_to_records() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")
    request = HeliusBackfillRequest(address="address-1")

    result = adapter.parse_signature_rows(
        request,
        [
            {
                "signature": "sig-1",
                "slot": 123,
                "blockTime": 1_700_000_000,
                "err": None,
            }
        ],
    )

    assert len(result.records) == 1
    assert result.records[0].signature == "sig-1"
    assert result.records[0].slot == 123
    assert result.records[0].block_time == 1_700_000_000
    assert result.records[0].success is True
    assert result.records[0].raw_json["signature"] == "sig-1"


def test_failed_transactions_are_excluded_by_default() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")
    request = HeliusBackfillRequest(address="address-1")

    result = adapter.parse_signature_rows(
        request,
        [
            {"signature": "sig-ok", "slot": 1, "blockTime": 100, "err": None},
            {"signature": "sig-failed", "slot": 2, "blockTime": 101, "err": {"code": 1}},
        ],
    )

    assert [record.signature for record in result.records] == ["sig-ok"]
    assert result.next_before == "sig-ok"


def test_failed_transactions_are_included_when_requested() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")
    request = HeliusBackfillRequest(address="address-1", include_failed=True)

    result = adapter.parse_signature_rows(
        request,
        [
            {"signature": "sig-ok", "slot": 1, "blockTime": 100, "err": None},
            {"signature": "sig-failed", "slot": 2, "blockTime": 101, "err": {"code": 1}},
        ],
    )

    assert [record.signature for record in result.records] == ["sig-ok", "sig-failed"]
    assert result.records[1].success is False
    assert result.next_before == "sig-failed"


def test_from_env_fails_clearly_if_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)

    with pytest.raises(ValueError, match="HELIUS_API_KEY is required"):
        HeliusHistoricalAdapter.from_env()


def test_fetch_signatures_for_address_uses_mocked_http_method() -> None:
    calls = []

    def fake_http_post(url: str, payload: dict, timeout_sec: int) -> dict:
        calls.append((url, payload, timeout_sec))
        return {
            "jsonrpc": "2.0",
            "result": [
                {"signature": "sig-1", "slot": 10, "blockTime": 1000, "err": None},
                {"signature": "sig-2", "slot": 11, "blockTime": 1001, "err": None},
            ],
        }

    adapter = HeliusHistoricalAdapter(
        rpc_url="https://mock-helius.invalid",
        timeout_sec=7,
        http_post=fake_http_post,
    )

    result = adapter.fetch_signatures_for_address(
        HeliusBackfillRequest(address="address-1", limit=2)
    )

    assert len(result.records) == 2
    assert result.next_before == "sig-2"
    assert calls[0][0] == "https://mock-helius.invalid"
    assert calls[0][1]["method"] == "getSignaturesForAddress"
    assert calls[0][1]["params"][1]["limit"] == 2
    assert calls[0][2] == 7


def test_build_get_transaction_payload_is_standard_json_rpc() -> None:
    adapter = HeliusHistoricalAdapter(api_key="test-key")

    payload = adapter.build_get_transaction_payload("sig-1")

    assert payload["method"] == "getTransaction"
    assert payload["params"][0] == "sig-1"
    assert payload["params"][1] == {
        "encoding": "jsonParsed",
        "maxSupportedTransactionVersion": 0,
    }


def test_fetch_transaction_uses_mocked_http_method() -> None:
    calls = []

    def fake_http_post(url: str, payload: dict, timeout_sec: int) -> dict:
        calls.append((url, payload, timeout_sec))
        return {
            "jsonrpc": "2.0",
            "result": {
                "slot": 10,
                "blockTime": 1000,
                "meta": {"err": None},
            },
        }

    adapter = HeliusHistoricalAdapter(
        rpc_url="https://mock-helius.invalid",
        timeout_sec=7,
        http_post=fake_http_post,
    )

    result = adapter.fetch_transaction("sig-1")

    assert result["slot"] == 10
    assert result["blockTime"] == 1000
    assert calls[0][1]["method"] == "getTransaction"


def test_fetch_transaction_handles_null_result() -> None:
    def fake_http_post(_url: str, _payload: dict, _timeout_sec: int) -> dict:
        return {"jsonrpc": "2.0", "result": None}

    adapter = HeliusHistoricalAdapter(
        rpc_url="https://mock-helius.invalid",
        http_post=fake_http_post,
    )

    assert adapter.fetch_transaction("sig-missing") == {}
