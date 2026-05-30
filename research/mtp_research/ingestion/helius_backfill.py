"""Helius historical RPC adapter for v3 research backfills."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib import request as urllib_request

from research.mtp_research.ingestion.helius_models import (
    HeliusBackfillRequest,
    HeliusBackfillResult,
    HeliusTransactionRecord,
)


HttpPost = Callable[[str, dict[str, Any], int], dict[str, Any]]


class HeliusHistoricalAdapter:
    """Small JSON-RPC adapter for low-cost historical signature discovery."""

    def __init__(
        self,
        api_key: str | None = None,
        rpc_url: str | None = None,
        timeout_sec: int = 30,
        http_post: HttpPost | None = None,
    ):
        self.api_key = api_key
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self._http_post = http_post or self._post_json

    @classmethod
    def from_env(cls) -> "HeliusHistoricalAdapter":
        api_key = os.getenv("HELIUS_API_KEY")
        if not api_key:
            raise ValueError("HELIUS_API_KEY is required for real Helius RPC calls")
        return cls(api_key=api_key)

    def build_rpc_url(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        if not self.api_key:
            raise ValueError("HELIUS_API_KEY is required to build the Helius RPC URL")
        return f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"

    def build_get_signatures_payload(self, request: HeliusBackfillRequest) -> dict[str, Any]:
        options: dict[str, Any] = {"limit": request.limit}
        if request.before:
            options["before"] = request.before
        if request.until:
            options["until"] = request.until

        return {
            "jsonrpc": "2.0",
            "id": "mtp-helius-get-signatures-for-address",
            "method": "getSignaturesForAddress",
            "params": [request.address, options],
        }

    def parse_signature_rows(
        self,
        request: HeliusBackfillRequest,
        rows: list[dict[str, Any]],
    ) -> HeliusBackfillResult:
        records: list[HeliusTransactionRecord] = []

        for row in rows:
            signature = row.get("signature")
            if not signature:
                continue

            success = row.get("err") is None
            if not success and not request.include_failed:
                continue

            records.append(
                HeliusTransactionRecord(
                    signature=signature,
                    slot=row.get("slot"),
                    block_time=row.get("blockTime"),
                    success=success,
                    raw_json=dict(row),
                )
            )

        next_before = records[-1].signature if records else None
        return HeliusBackfillResult(
            request=request,
            records=records,
            next_before=next_before,
            metadata_json={
                "source": "helius_json_rpc",
                "method": "getSignaturesForAddress",
            },
        )

    def fetch_signatures_for_address(
        self,
        request: HeliusBackfillRequest,
    ) -> HeliusBackfillResult:
        payload = self.build_get_signatures_payload(request)
        response = self._http_post(self.build_rpc_url(), payload, self.timeout_sec)

        if "error" in response:
            raise RuntimeError(f"Helius RPC error: {response['error']}")

        rows = response.get("result")
        if not isinstance(rows, list):
            raise RuntimeError("Helius RPC response did not include a result list")

        return self.parse_signature_rows(request, rows)

    def build_get_transaction_payload(self, signature: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": "mtp-helius-get-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }

    def fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = self.build_get_transaction_payload(signature)
        response = self._http_post(self.build_rpc_url(), payload, self.timeout_sec)

        if "error" in response:
            raise RuntimeError(f"Helius RPC error: {response['error']}")

        result = response.get("result")
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise RuntimeError("Helius RPC getTransaction result was not an object")
        return result

    def fetch_transactions(self, signatures: list[str]) -> list[dict[str, Any]]:
        return [self.fetch_transaction(signature) for signature in signatures]

    def _post_json(self, url: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
