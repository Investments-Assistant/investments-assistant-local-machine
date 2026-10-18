"""Startup must use the predeclared 15-second budget, not a polling-count proxy."""

from types import SimpleNamespace

import httpx
import pytest

from scripts import soak_acceptance as soak


@pytest.mark.parametrize("ready_at", [12, 16])
def test_startup_uses_full_budget_but_never_extends_it(monkeypatch, tmp_path, ready_at):
    clock = [0.0]
    terminated = []
    process = SimpleNamespace(poll=lambda: None)

    class Client:
        headers = {}
        cookies = {"ia_csrf": "synthetic"}

        def get(self, *args, **kwargs):
            if clock[0] < ready_at:
                raise httpx.ConnectError("synthetic server still starting")
            return SimpleNamespace(status_code=200)

        def post(self, *args, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None)

        def close(self):
            pass

    def wait(seconds):
        clock[0] += seconds
        return False

    monkeypatch.setattr(soak.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(soak, "STOP", SimpleNamespace(wait=wait))
    monkeypatch.setattr(soak.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(soak.httpx, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(soak, "terminate", lambda item: terminated.append(item))
    if ready_at < 15:
        assert soak.start_server({"user": "fixture"}, tmp_path, {})[0] is process
        assert 12 <= clock[0] < 15 and not terminated
    else:
        with pytest.raises(RuntimeError, match="FIXTURE_STARTUP_BUDGET"):
            soak.start_server({"user": "fixture"}, tmp_path, {})
        assert 15 <= clock[0] < 15.11 and terminated == [process]


@pytest.mark.parametrize(
    "persisted_halted, persisted_orders, rejected",
    [
        (False, [], True),
        (True, [], False),
        (True, [{"status": "filled"}], True),
    ],
    ids=["lost-halt", "preserved-halt", "unexpected-order"],
)
def test_existing_halt_is_observed_before_startup_can_reassert_it(
    monkeypatch, tmp_path, persisted_halted, persisted_orders, rejected,
):
    """A healthy restarted service can still have lost durable safety state."""
    account_path = "/api/simulator/accounts/synthetic-persisted-halt"
    persisted = {"halted": persisted_halted, "orders": persisted_orders}
    calls, terminated = [], []
    process = SimpleNamespace(poll=lambda: None)

    def response(payload=None):
        return SimpleNamespace(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: dict(payload or {}),
        )

    class Client:
        def __init__(self):
            self.headers = {}
            self.cookies = {"ia_csrf": "synthetic"}
            self.closed = False

        def get(self, path, **_kwargs):
            calls.append(("GET", path))
            if path == "/api/health":
                return response()
            assert path == account_path
            return response(persisted)

        def post(self, path, **_kwargs):
            calls.append(("POST", path))
            if path == account_path + "/halt":
                # This models the masking bug: writing first repairs lost halt.
                persisted["halted"] = True
                return response(persisted)
            assert path == "/api/auth/login"
            return response()

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(soak.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(soak.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(soak, "terminate", lambda item: terminated.append(item))
    state = {"user": "fixture", "halt_account": "synthetic-persisted-halt"}
    if rejected:
        with pytest.raises(RuntimeError, match="HALT"):
            soak.start_server(state, tmp_path, {})
        assert client.closed and terminated == [process]
    else:
        returned_process, returned_client, _base = soak.start_server(state, tmp_path, {})
        assert returned_process is process and returned_client is client
        assert not client.closed and terminated == []
    assert calls == [
        ("GET", "/api/health"),
        ("POST", "/api/auth/login"),
        ("GET", account_path),
    ]
    assert persisted["halted"] is persisted_halted


def test_fresh_start_has_no_existing_halt_to_inspect(monkeypatch, tmp_path):
    """First startup precedes fixture creation; no account read/write is valid."""
    calls = []
    process = SimpleNamespace(poll=lambda: None)

    class Client:
        headers = {}
        cookies = {"ia_csrf": "synthetic"}

        def get(self, path, **_kwargs):
            calls.append(("GET", path))
            assert path == "/api/health"
            return SimpleNamespace(status_code=200)

        def post(self, path, **_kwargs):
            calls.append(("POST", path))
            assert path == "/api/auth/login"
            return SimpleNamespace(raise_for_status=lambda: None)

        def close(self):
            raise AssertionError("Successful first startup must retain its client")

    client = Client()
    monkeypatch.setattr(soak.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(soak.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(soak, "terminate", lambda item: pytest.fail("Unexpected startup cleanup"))
    assert soak.start_server({"user": "fixture"}, tmp_path, {})[:2] == (process, client)
    assert calls == [("GET", "/api/health"), ("POST", "/api/auth/login")]


@pytest.mark.parametrize(
    "login_seconds, guard_seconds, rejected, guard_attempted, finished_at",
    [
        (2, 2, True, True, 16),
        (1, 1, False, True, 14),
        (3, 0, True, False, 15),
    ],
    ids=["guard-completes-too-late", "whole-startup-in-budget", "login-exhausts-budget"],
)
def test_login_and_persisted_halt_share_original_startup_deadline(
    monkeypatch, tmp_path, login_seconds, guard_seconds, rejected, guard_attempted, finished_at,
):
    """Health readiness must not grant login or state inspection a fresh budget."""
    clock = [0.0]
    calls, terminated = [], []
    process = SimpleNamespace(poll=lambda: None)
    account_path = "/api/simulator/accounts/synthetic-persisted-halt"

    def response(payload=None):
        return SimpleNamespace(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: dict(payload or {}),
        )

    def spend_request_time(seconds, timeout):
        # Individual HTTP operations are bounded by time still available. An
        # operation can nonetheless return late, e.g. after a streaming response;
        # successful HTTP status alone cannot prove total elapsed-time compliance.
        assert 0 < timeout <= min(5, 15 - clock[0])
        clock[0] += seconds

    class Client:
        def __init__(self):
            self.headers = {}
            self.cookies = {"ia_csrf": "synthetic"}
            self.closed = False

        def get(self, path, **kwargs):
            if path == "/api/health":
                if clock[0] < 12:
                    raise httpx.ConnectError("synthetic startup not ready")
                return response()
            calls.append(("GET", path))
            assert path == account_path
            spend_request_time(guard_seconds, kwargs["timeout"])
            return response({"halted": True, "orders": []})

        def post(self, path, **kwargs):
            calls.append(("POST", path))
            assert path == "/api/auth/login"
            spend_request_time(login_seconds, kwargs["timeout"])
            return response()

        def close(self):
            self.closed = True

    def wait(seconds):
        clock[0] = round(clock[0] + seconds, 9)
        return False

    client = Client()
    monkeypatch.setattr(soak.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(soak, "STOP", SimpleNamespace(wait=wait))
    monkeypatch.setattr(soak.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(soak.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(soak, "terminate", lambda item: terminated.append(item))
    state = {"user": "fixture", "halt_account": "synthetic-persisted-halt"}
    if rejected:
        with pytest.raises(RuntimeError, match="FIXTURE_STARTUP_BUDGET"):
            soak.start_server(state, tmp_path, {})
        assert client.closed and terminated == [process]
    else:
        assert soak.start_server(state, tmp_path, {})[:2] == (process, client)
        assert not client.closed and terminated == []
    assert clock[0] == finished_at
    assert calls == [("POST", "/api/auth/login")] + (
        [("GET", account_path)] if guard_attempted else []
    )
