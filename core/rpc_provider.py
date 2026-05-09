import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.redaction import redact_secrets


DEFAULT_GATEKEEPER_URL = "https://beta.helius-rpc.com/?api-key={api_key}"
DEFAULT_MAINNET_URL = "https://mainnet.helius-rpc.com/?api-key={api_key}"
DEFAULT_PUBLIC_SOLANA_URL = "https://api.mainnet-beta.solana.com"


@dataclass(frozen=True)
class HeliusRpcProvider:
    name: str
    url: str

    @property
    def safe_url(self):
        return redact_secrets(self.url)


class RpcProviderError(Exception):
    def __init__(self, failures):
        self.failures = failures
        detail = "; ".join(
            f"{item.get('name')}: {item.get('detail') or item.get('http_status') or item.get('error')}"
            for item in failures
        )
        super().__init__(redact_secrets(detail))


def _with_api_key(url, api_key):
    if "{api_key}" in url:
        return url.format(api_key=api_key)
    if "api-key=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}api-key={api_key}"


def _split_urls(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def build_helius_rpc_providers(api_key=None, primary_url=None, fallback_urls=None):
    api_key = api_key or os.getenv("HELIUS_API_KEY")
    if not api_key:
        return [HeliusRpcProvider(name="solana_public", url=DEFAULT_PUBLIC_SOLANA_URL)]

    primary_url = primary_url or os.getenv("HELIUS_RPC_PRIMARY_URL")
    fallback_urls = fallback_urls if fallback_urls is not None else os.getenv("SOLANA_RPC_FALLBACK_URLS")

    if primary_url:
        urls = [("primary", primary_url)]
        urls.extend((f"fallback_{index}", url) for index, url in enumerate(_split_urls(fallback_urls), start=1))
    else:
        urls = [
            ("helius_gatekeeper", DEFAULT_GATEKEEPER_URL),
            ("helius_mainnet", DEFAULT_MAINNET_URL),
        ]
        urls.extend((f"fallback_{index}", url) for index, url in enumerate(_split_urls(fallback_urls), start=1))
        urls.append(("solana_public", DEFAULT_PUBLIC_SOLANA_URL))

    providers = []
    seen = set()
    for name, url in urls:
        final_url = _with_api_key(url, api_key) if "helius" in url or "{api_key}" in url else url
        if final_url in seen:
            continue
        providers.append(HeliusRpcProvider(name=name, url=final_url))
        seen.add(final_url)
    return providers


def choose_first_healthy_provider(health_rows):
    for row in health_rows or []:
        if row.get("ok"):
            return row
    return None


def summarize_provider_health(health_rows):
    health_rows = health_rows or []
    active = choose_first_healthy_provider(health_rows)
    if not health_rows:
        state = "missing_key"
    elif active and health_rows[0].get("ok"):
        state = "healthy"
    elif active:
        state = "degraded"
    else:
        state = "offline"
    return {
        "state": state,
        "active_provider": active.get("name") if active else None,
        "providers": health_rows,
        "live_execution_unlocked": False,
    }


def _failure(provider, **fields):
    row = {"name": provider.name, "ok": False, "safe_url": provider.safe_url}
    row.update(fields)
    if row.get("detail"):
        row["detail"] = redact_secrets(row["detail"])[:240]
    return row


async def post_json_with_provider_failover(session, payload, providers=None):
    providers = providers or build_helius_rpc_providers()
    if not providers:
        return None, None

    failures = []
    for provider in providers:
        try:
            async with session.post(provider.url, json=payload) as resp:
                text = await resp.text()
                if resp.status == 200:
                    return json.loads(text), provider.name
                failures.append(_failure(provider, http_status=resp.status, detail=text))
        except Exception as exc:
            failures.append(_failure(provider, error=type(exc).__name__, detail=str(exc)))

    raise RpcProviderError(failures)


def check_helius_provider_health(timeout=5):
    providers = build_helius_rpc_providers()
    if not providers:
        return summarize_provider_health([])

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getHealth"}).encode("utf-8")
    rows = []
    for provider in providers:
        request = Request(provider.url, data=payload, headers={"content-type": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                rows.append({
                    "name": provider.name,
                    "ok": response.status == 200 and data.get("result") == "ok",
                    "http_status": response.status,
                    "detail": data.get("result") or data.get("error") or "unknown",
                    "safe_url": provider.safe_url,
                })
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            rows.append(_failure(provider, http_status=exc.code, detail=detail))
        except (URLError, TimeoutError, OSError) as exc:
            rows.append(_failure(provider, error=type(exc).__name__, detail=str(exc)))

    return summarize_provider_health(rows)
