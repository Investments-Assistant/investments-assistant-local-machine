"""Bounded public HTTPS fetches with DNS pinned before TCP/TLS connection.

Feed parsers never receive URLs. Each redirect is revalidated; TLS authenticates
the original hostname while TCP connects to the validated numeric address.
"""

import ssl
import time
import socket
import ipaddress
import threading
from dataclasses import dataclass
import http.client
from urllib.parse import urljoin, urlsplit
from concurrent.futures import (
    TimeoutError as FutureTimeout,
    ThreadPoolExecutor,
)


class PublicFetchError(RuntimeError):
    def __init__(self, code, *, retry_after=None):
        super().__init__(code)
        self.retry_after = retry_after


def retry_delay(value):
    """Bound provider Retry-After guidance; never persist raw response headers."""
    from datetime import UTC, datetime
    from email.utils import parsedate_to_datetime

    try:
        if value is None:
            return None
        if str(value).strip().isdigit():
            seconds = int(value)
        else:
            timestamp = parsedate_to_datetime(value)
            if timestamp.tzinfo is None:
                return None
            seconds = int((timestamp - datetime.now(UTC)).total_seconds())
        return max(0, min(86400, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


_dns_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="public-dns")
_dns_slots = threading.BoundedSemaphore(2)


def public_addresses(host, port):
    if not _dns_slots.acquire(blocking=False):
        raise PublicFetchError("DNS_CAPACITY_EXCEEDED")
    future = _dns_workers.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _dns_slots.release())
    try:
        records = future.result(timeout=3)
    except (FutureTimeout, OSError) as exc:
        raise PublicFetchError("DNS_UNAVAILABLE") from exc
    addresses = []
    for _, _, _, _, sockaddr in records:
        value = sockaddr[0]
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and any(
            address in ipaddress.ip_network(prefix)
            for prefix in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")
        ):
            raise PublicFetchError("TRANSITION_ADDRESS_DENIED")
        # IPv4-mapped IPv6 must obey the underlying IPv4 policy too.
        underlying = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
        if not address.is_global or underlying and not underlying.is_global:
            raise PublicFetchError("NON_PUBLIC_ADDRESS")
        if value not in addresses:
            addresses.append(value)
    if not addresses:
        raise PublicFetchError("DNS_UNAVAILABLE")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._create_connection = self._public_connect

    def _public_connect(self, address, timeout, source_address=None):
        host, port = address
        addresses = public_addresses(host, port)
        # No second lookup of host: socket.create_connection receives a numeric
        # address, while HTTPSConnection still uses self.host for TLS SNI/verification.
        try:
            return socket.create_connection((addresses[0], port), timeout, source_address)
        except OSError as exc:
            raise PublicFetchError("PUBLIC_CONNECTION_FAILED") from exc


@dataclass(frozen=True)
class PublicResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    url: str

    @property
    def text(self):
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        import json

        return json.loads(self.body)


def fetch_public(url, *, headers=None, max_bytes=2_000_000, total_seconds=20):
    if not 1 <= max_bytes <= 4_000_000 or not 0 < total_seconds <= 30:
        raise ValueError("Invalid bounded public fetch policy")
    deadline = time.monotonic() + total_seconds
    safe_headers = {"User-Agent": "InvestmentAssistant/1.0", "Accept-Encoding": "identity"}
    for key, value in (headers or {}).items():
        if key.lower() not in {"accept", "user-agent", "if-none-match", "if-modified-since"}:
            raise PublicFetchError("UNSUPPORTED_REQUEST_HEADER")
        safe_headers[key] = value
    for _ in range(4):
        try:
            target = urlsplit(url)
            if (
                target.scheme != "https"
                or not target.hostname
                or target.username
                or target.password
                or target.port not in {None, 443}
                or len(url) > 4096
            ):
                raise PublicFetchError("PUBLIC_HTTPS_REQUIRED")
        except ValueError as exc:
            raise PublicFetchError("INVALID_PUBLIC_URL") from exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicFetchError("PUBLIC_FETCH_TIMEOUT")
        connection = PinnedHTTPSConnection(target.hostname, timeout=min(5, remaining))
        try:
            path = target.path or "/"
            if target.query:
                path += "?" + target.query
            connection.request("GET", path, headers=safe_headers)
            response = connection.getresponse()
            metadata = {key.lower(): value for key, value in response.getheaders()}
            if response.status in {301, 302, 303, 307, 308}:
                location = metadata.get("location")
                if not location:
                    raise PublicFetchError("INVALID_REDIRECT")
                url = urljoin(url, location)
                continue
            if response.status == 304:
                return PublicResponse(304, b"", metadata, url)
            if response.status != 200:
                # No raw URL/body/API key escapes through provider exception text.
                raise PublicFetchError(
                    f"PUBLIC_HTTP_{response.status}",
                    retry_after=retry_delay(metadata.get("retry-after")),
                )
            if metadata.get("content-encoding", "identity").lower() not in {"", "identity"}:
                raise PublicFetchError("UNSUPPORTED_CONTENT_ENCODING")
            data = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PublicFetchError("PUBLIC_FETCH_TIMEOUT")
                if connection.sock:
                    connection.sock.settimeout(min(5, remaining))
                chunk = response.read(min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise PublicFetchError("PUBLIC_RESPONSE_TOO_LARGE")
            return PublicResponse(200, bytes(data), metadata, url)
        except (OSError, http.client.HTTPException) as exc:
            raise PublicFetchError("PUBLIC_FETCH_UNAVAILABLE") from exc
        finally:
            connection.close()
    raise PublicFetchError("TOO_MANY_REDIRECTS")
