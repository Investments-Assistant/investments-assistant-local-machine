"""Portable local CI transport never admits remote or ambiguous database hosts."""

import pytest

from scripts import soak_acceptance as soak


@pytest.mark.parametrize("address", [
    "remote.example/test_fixture",
    "/test_fixture",
    "localhost/test_fixture?host=remote.example",
    "localhost/test_fixture?host=/tmp",
    "localhost/test_fixture?host=.qa/socket",
    "localhost/test_fixture?host=/tmp&host=remote.example",
])
async def test_soak_rejects_unsafe_transport_before_connect(monkeypatch, address):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe transport reached database engine")

    monkeypatch.setattr(soak, "create_async_engine", forbidden)
    with pytest.raises(ValueError, match="Soak requires"):
        await soak.verify_database("postgresql+asyncpg://" + address, "fixture-marker")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
async def test_loopback_still_requires_database_verification(monkeypatch, host):
    class UnverifiedDatabase(Exception):
        pass

    def unavailable(*args, **kwargs):
        raise UnverifiedDatabase

    monkeypatch.setattr(soak, "create_async_engine", unavailable)
    with pytest.raises(UnverifiedDatabase):
        await soak.verify_database(f"postgresql+asyncpg://{host}/test_fixture", "fixture-marker")
