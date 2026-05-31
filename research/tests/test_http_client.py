import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from research.mtp_research.ingestion.http_client import SimpleJsonHttpClient


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.payload


def test_get_json_parses_valid_json_using_mocked_urllib(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        assert req.headers["User-agent"] == "MemeTraderPro-v3-research/0.1"
        assert timeout == 7
        return FakeResponse(json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr("research.mtp_research.ingestion.http_client.urllib_request.urlopen", fake_urlopen)

    assert SimpleJsonHttpClient().get_json("https://example.test", timeout_sec=7) == {"ok": True}


def test_get_json_non_200_raises_clear_error(monkeypatch) -> None:
    def fake_urlopen(_req, timeout):
        raise HTTPError("https://example.test", 503, "Service Unavailable", {}, BytesIO())

    monkeypatch.setattr("research.mtp_research.ingestion.http_client.urllib_request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP GET failed"):
        SimpleJsonHttpClient().get_json("https://example.test")


def test_get_json_invalid_json_raises_clear_error(monkeypatch) -> None:
    def fake_urlopen(_req, timeout):
        return FakeResponse(b"not-json")

    monkeypatch.setattr("research.mtp_research.ingestion.http_client.urllib_request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Invalid JSON"):
        SimpleJsonHttpClient().get_json("https://example.test")
