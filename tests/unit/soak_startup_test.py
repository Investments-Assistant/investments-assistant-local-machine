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
