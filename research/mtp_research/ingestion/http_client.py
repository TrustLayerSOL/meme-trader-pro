"""Small standard-library JSON HTTP client for public discovery APIs."""

from __future__ import annotations

import json
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


class SimpleJsonHttpClient:
    """Fetch JSON with urllib so v3 discovery has no new HTTP dependency."""

    USER_AGENT = "MemeTraderPro-v3-research/0.1"

    def get_json(self, url: str, timeout_sec: int = 20) -> Any:
        req = urllib_request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout_sec) as response:  # noqa: S310
                status = getattr(response, "status", 200)
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP GET failed for {url}: status={exc.code} reason={exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"HTTP GET failed for {url}: {exc.reason}") from exc

        if status != 200:
            raise RuntimeError(f"HTTP GET failed for {url}: status={status}")

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {url}") from exc
