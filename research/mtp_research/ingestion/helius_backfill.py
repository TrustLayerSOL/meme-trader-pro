"""Helius historical RPC adapter for v3 research backfills."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
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
        transaction_workers: int = 1,
        max_retries: int = 3,
        retry_base_sleep_sec: float = 1.0,
    ):
        self.api_key = api_key
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self._http_post = http_post or self._post_json
        self.transaction_workers = max(1, transaction_workers)
        self.max_retries = max(0, max_retries)
        self.retry_base_sleep_sec = max(0.0, retry_base_sleep_sec)

    @classmethod
    def from_env(
        cls,
        load_project_dotenv: bool = True,
        transaction_workers: int | None = None,
        timeout_sec: int | None = None,
    ) -> "HeliusHistoricalAdapter":
        if load_project_dotenv:
            _load_project_dotenv_if_needed()
        api_key = os.getenv("HELIUS_API_KEY")
        if not api_key:
            raise ValueError("HELIUS_API_KEY is required for real Helius RPC calls")
        return cls(
            api_key=api_key,
            timeout_sec=timeout_sec or _env_int("HELIUS_TIMEOUT_SEC", 30),
            transaction_workers=transaction_workers or _env_int("HELIUS_TRANSACTION_WORKERS", 1),
            max_retries=_env_int("HELIUS_MAX_RETRIES", 3),
            retry_base_sleep_sec=_env_float("HELIUS_RETRY_BASE_SLEEP_SEC", 1.0),
        )

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
        if self.transaction_workers == 1 or len(signatures) <= 1:
            return [self.fetch_transaction_or_empty(signature) for signature in signatures]
        with ThreadPoolExecutor(max_workers=self.transaction_workers) as executor:
            return list(executor.map(self.fetch_transaction_or_empty, signatures))

    def fetch_transaction_or_empty(self, signature: str) -> dict[str, Any]:
        try:
            return self.fetch_transaction(signature)
        except Exception:
            return {}

    def _post_json(self, url: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib_request.urlopen(req, timeout=timeout_sec) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                _sleep_for_retry(exc, attempt, self.retry_base_sleep_sec)
            except URLError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                _sleep_for_retry(exc, attempt, self.retry_base_sleep_sec)
        if last_error:
            raise last_error
        raise RuntimeError("Helius HTTP request failed without an exception")


def _load_project_dotenv_if_needed() -> None:
    if os.getenv("HELIUS_API_KEY"):
        return

    for directory in (Path.cwd(), *Path.cwd().parents):
        env_path = directory / ".env"
        if env_path.is_file():
            _load_dotenv_values(env_path)
            return


def _load_dotenv_values(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value.strip())


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _sleep_for_retry(exc: Exception, attempt: int, base_sleep_sec: float) -> None:
    retry_after = None
    if isinstance(exc, HTTPError):
        retry_after_header = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after_header:
            try:
                retry_after = float(retry_after_header)
            except ValueError:
                retry_after = None
    delay = retry_after if retry_after is not None else base_sleep_sec * (2 ** attempt)
    if delay > 0:
        time.sleep(delay)
