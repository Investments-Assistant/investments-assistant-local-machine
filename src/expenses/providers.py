"""Bounded Bank Account Data protocol. Transport is explicit and never discovered.

No payments API, bank passwords, arbitrary URLs, or model tools are supported.
The production factory is separately gated; tests inject httpx.MockTransport.
"""

import json
import uuid
from typing import Protocol
import logging
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import httpx

# httpx INFO logs include provider account IDs in URLs. Keep only its warnings.
logging.getLogger("httpx").setLevel(logging.WARNING)


class ProviderError(Exception):
    def __init__(self, code, retry_after=0):
        self.code = code
        self.retry_after = min(86400, max(0, retry_after))
        super().__init__(code)


class BankProvider(Protocol):
    name: str

    async def token(self, credentials: dict) -> dict: ...
    async def consent(
        self, credentials: dict, *, institution: str, redirect: str, reference: str
    ) -> dict: ...
    async def accounts(self, credentials: dict) -> list[str]: ...
    async def transactions(self, credentials: dict, *, since: date) -> list[dict]: ...


def identifier(value):
    try:
        return str(uuid.UUID(str(value)))
    except ValueError as exc:
        raise ProviderError("INVALID_PROVIDER_IDENTIFIER") from exc


class GoCardless:
    name = "gocardless"
    BASE = "https://bankaccountdata.gocardless.com/api/v2/"

    def __init__(self, *, transport: httpx.AsyncBaseTransport):
        self.transport = transport

    async def _request(self, method, path, *, token=None, payload=None, params=None):
        # All paths originate in methods below. Never follow provider-supplied next/link URLs.
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=10, follow_redirects=False, trust_env=False
            ) as client, client.stream(
                method, self.BASE + path, headers=headers, json=payload, params=params
            ) as response:
                if response.status_code in {401, 403}:
                    raise ProviderError("CONSENT_OR_TOKEN_REQUIRED")
                if response.status_code == 402:
                    raise ProviderError("PROVIDER_ACCESS_REQUIRES_DECISION")
                if response.status_code == 429:
                    raw = response.headers.get("Retry-After", "3600")
                    raise ProviderError(
                        "PROVIDER_RATE_LIMIT", int(raw) if raw.isdigit() else 3600
                    )
                if response.status_code >= 500:
                    raise ProviderError("PROVIDER_UNAVAILABLE", 300)
                if response.status_code not in {200, 201}:
                    raise ProviderError("PROVIDER_REQUEST_REJECTED")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                value = json.loads(b"".join(chunks))
                if not isinstance(value, dict):
                    raise ProviderError("INVALID_PROVIDER_RESPONSE")
                return value
        except (httpx.HTTPError, TimeoutError) as exc:
            raise ProviderError("PROVIDER_UNAVAILABLE", 300) from exc
        except (ValueError, TypeError) as exc:
            raise ProviderError("INVALID_PROVIDER_RESPONSE") from exc

    async def token(self, credentials):
        now = datetime.now(UTC)
        result = dict(credentials)
        expiry = result.get("access_until")
        if (
            result.get("access")
            and expiry
            and datetime.fromisoformat(expiry) > now + timedelta(seconds=30)
        ):
            return result
        if result.get("refresh"):
            raw = await self._request(
                "POST", "token/refresh/", payload={"refresh": result["refresh"]}
            )
        elif result.get("secret_id") and result.get("secret_key"):
            raw = await self._request(
                "POST",
                "token/new/",
                payload={"secret_id": result["secret_id"], "secret_key": result["secret_key"]},
            )
            if not raw.get("refresh"):
                raise ProviderError("INVALID_PROVIDER_RESPONSE")
            result["refresh"] = raw["refresh"]
            # Initial response shapes may omit access. Exchange the refresh token explicitly.
            if not raw.get("access"):
                raw = await self._request(
                    "POST", "token/refresh/", payload={"refresh": raw["refresh"]}
                )
        else:
            raise ProviderError("CONSENT_OR_TOKEN_REQUIRED")
        if not isinstance(raw.get("access"), str) or not raw["access"]:
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        ttl = raw.get("access_expires")
        if not isinstance(ttl, int) or not 30 < ttl <= 172800:
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        result.update(access=raw["access"], access_until=(now + timedelta(seconds=ttl)).isoformat())
        result.pop("secret_key", None)
        result.pop("secret_id", None)
        return result

    async def consent(self, credentials, *, institution, redirect, reference):
        # redirect is operator-configured, never derived from Host or model input.
        target = urlsplit(redirect)
        if target.scheme != "https" or not target.hostname or target.username or target.fragment:
            raise ProviderError("INVALID_CONSENT_REDIRECT")
        raw = await self._request(
            "POST",
            "requisitions/",
            token=credentials["access"],
            payload={
                "institution_id": institution,
                "redirect": redirect,
                "reference": reference,
                "account_selection": True,
            },
        )
        link = urlsplit(str(raw.get("link", "")))
        if (
            link.scheme != "https"
            or link.hostname != "ob.gocardless.com"
            or link.username
            or link.port not in {None, 443}
        ):
            raise ProviderError("INVALID_CONSENT_LINK")
        return {"requisition_id": identifier(raw.get("id")), "link": raw["link"]}

    async def accounts(self, credentials):
        requisition = identifier(credentials.get("requisition_id"))
        raw = await self._request(
            "GET", f"requisitions/{requisition}/", token=credentials["access"]
        )
        if raw.get("reference") != credentials.get("reference"):
            raise ProviderError("CONSENT_REFERENCE_MISMATCH")
        if raw.get("status") != "LN":
            raise ProviderError("CONSENT_OR_TOKEN_REQUIRED")
        accounts = raw.get("accounts")
        if not isinstance(accounts, list) or len(accounts) > 100:
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        return [identifier(account) for account in accounts]

    async def transactions(self, credentials, *, since):
        account = identifier(credentials.get("account_id"))
        if account not in await self.accounts(credentials):
            raise ProviderError("ACCOUNT_NOT_CONSENTED")
        raw = await self._request(
            "GET",
            f"accounts/{account}/transactions/",
            token=credentials["access"],
            params={"date_from": since.isoformat()},
        )
        batches = raw.get("transactions")
        if not isinstance(batches, dict) or not isinstance(batches.get("booked"), list):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        result = []
        for lifecycle in ("pending", "booked"):
            records = batches.get(lifecycle, [])
            if not isinstance(records, list):
                raise ProviderError("INVALID_PROVIDER_RESPONSE")
            for record in records:
                if not isinstance(record, dict):
                    raise ProviderError("INVALID_PROVIDER_RESPONSE")
                result.append(
                    {
                        **record,
                        "account_id": account,
                        "lifecycle": lifecycle,
                        "pending": lifecycle == "pending",
                    }
                )
                if len(result) > 5000:
                    raise ProviderError("PROVIDER_BATCH_TOO_LARGE")
        return result
