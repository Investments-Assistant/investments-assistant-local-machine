from unittest.mock import MagicMock, patch

import pytest

from src.news.http import PublicFetchError, PinnedHTTPSConnection, fetch_public, public_addresses

pytestmark = pytest.mark.unit


def answer(ip):
    return [(2, 1, 6, "", (ip, 443))]


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"]
)
def test_non_public_dns_is_denied_before_connect(ip):
    with (
        patch("src.news.http.socket.getaddrinfo", return_value=answer(ip)),
        patch("src.news.http.socket.create_connection") as connect,
    ):
        with pytest.raises(PublicFetchError, match="NON_PUBLIC_ADDRESS"):
            PinnedHTTPSConnection("fixture.example", timeout=1)._public_connect(
                ("fixture.example", 443), 1
            )
        connect.assert_not_called()


def test_dns_is_pinned_and_mixed_public_private_answer_is_rejected():
    with (
        patch("src.news.http.socket.getaddrinfo", return_value=answer("93.184.216.34")) as resolve,
        patch("src.news.http.socket.create_connection") as connect,
    ):
        connection = PinnedHTTPSConnection("fixture.example", timeout=1)
        connection._public_connect(("fixture.example", 443), 1)
        connect.assert_called_once_with(("93.184.216.34", 443), 1, None)
        resolve.assert_called_once()
        assert connection.host == "fixture.example"  # TLS SNI/certificate hostname retained
    with patch(
        "src.news.http.socket.getaddrinfo",
        return_value=answer("93.184.216.34") + answer("10.0.0.1"),
    ), pytest.raises(PublicFetchError, match="NON_PUBLIC_ADDRESS"):
        public_addresses("fixture.example", 443)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com:22",
    ],
)
def test_invalid_schemes_credentials_and_ports_never_connect(url):
    with patch("src.news.http.PinnedHTTPSConnection") as connection:
        with pytest.raises(PublicFetchError, match="PUBLIC_HTTPS_REQUIRED"):
            fetch_public(url)
        connection.assert_not_called()


def test_redirect_target_revalidated_and_response_bound():
    conn = MagicMock()
    response = conn.getresponse.return_value
    response.status = 302
    response.getheaders.return_value = [("Location", "file:///private")]
    with (
        patch('src.news.http.PinnedHTTPSConnection', return_value=conn),
        pytest.raises(PublicFetchError, match='PUBLIC_HTTPS_REQUIRED'),
    ):
        fetch_public("https://fixture.example")
    response.status = 200
    response.getheaders.return_value = []
    response.read.return_value = b"a" * 11
    with (
        patch('src.news.http.PinnedHTTPSConnection', return_value=conn),
        pytest.raises(PublicFetchError, match='PUBLIC_RESPONSE_TOO_LARGE'),
    ):
        fetch_public("https://fixture.example", max_bytes=10)
    assert conn.close.call_count == 2


@pytest.mark.parametrize("ip", ["64:ff9b::7f00:1", "2002:7f00:1::1"])
def test_transition_addresses_cannot_tunnel_to_private_ipv4(ip):
    with (
        patch('src.news.http.socket.getaddrinfo', return_value=answer(ip)),
        pytest.raises(PublicFetchError, match='TRANSITION_ADDRESS_DENIED'),
    ):
        public_addresses("fixture.example", 443)


@pytest.mark.parametrize(
    "header,expected", [("900", 900), ("99999999", 86400), ("invalid", None), (None, None)]
)
def test_provider_retry_after_is_bounded_and_separate_from_error_text(header, expected):
    from src.news.http import retry_delay

    assert retry_delay(header) == expected
    conn = MagicMock()
    response = conn.getresponse.return_value
    response.status = 429
    response.getheaders.return_value = [("Retry-After", header)] if header else []
    with patch("src.news.http.PinnedHTTPSConnection", return_value=conn), pytest.raises(PublicFetchError) as error:
        fetch_public("https://fixture.example")
    assert str(error.value) == "PUBLIC_HTTP_429"
    assert error.value.retry_after == expected
