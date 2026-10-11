"""Real TLS handshakes verify pinned HTTPS still authenticates certificates."""

import ssl
import socket
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.news.http import PinnedHTTPSConnection


@pytest.mark.parametrize(
    "hostname,trusted", [("fixture.example", True), ("wrong.example", True), ("fixture.example", False)]
)
def test_pinned_connection_validates_certificate_and_original_hostname(tmp_path, hostname, trusted):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture.example")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("fixture.example")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_file, key_file)
    server_names = []
    server_context.set_servername_callback(lambda sock, name, context: server_names.append(name))
    connection = PinnedHTTPSConnection(hostname, timeout=2)
    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    assert connection._context.check_hostname
    if trusted:
        connection._context.load_verify_locations(cert_file)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)

        def serve():
            raw, _ = listener.accept()
            with raw:
                raw.settimeout(3)
                try:
                    with server_context.wrap_socket(raw, server_side=True) as secure:
                        secure.sendall(b"fixture")
                except ssl.SSLError:
                    # Expected peer alert for the two rejected certificates.
                    return

        # Redirect only this test connection's TCP transport to a local fixture.
        # Production DNS/public-address policy is tested in public_fetch_test.
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
            listener.getsockname(), timeout
        )
        with ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(serve)
            try:
                if trusted and hostname == "fixture.example":
                    connection.connect()
                    assert connection.sock.recv(7) == b"fixture"
                else:
                    with pytest.raises(ssl.SSLCertVerificationError):
                        connection.connect()
            finally:
                connection.close()
                future.result(timeout=4)
    assert server_names == [hostname]
