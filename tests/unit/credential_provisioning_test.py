"""Literal credentials survive local provisioning without hidden policy caps."""

from io import StringIO
import base64
from unittest.mock import AsyncMock

from dotenv import dotenv_values
import pytest

from scripts import create_user, create_auth_hash
from src.config import Settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def remove_bootstrap_environment(monkeypatch):
    monkeypatch.delenv("AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_USERNAME_BASE64", raising=False)


@pytest.mark.parametrize("username", [
    "Luís çãáé| ' \" € @ # $ ${HOME} \\",
    "  leading and trailing  ",
    "   ",
    "áçã€" * 10000,
    "e\u0301",
])
def test_legacy_plain_and_base64_config_preserve_exact_username(username):
    plain = Settings(_env_file=None, auth_username=username)
    assert plain.auth_username == username
    line = create_auth_hash.username_environment_line(username)
    loaded = dotenv_values(stream=StringIO(line))
    decoded = Settings(_env_file=None, auth_username="legacy", auth_username_base64=loaded["AUTH_USERNAME_BASE64"])
    assert decoded.auth_username == username
    assert "auth_username_base64" not in decoded.model_dump()
    assert "auth_username_base64" not in repr(decoded)


@pytest.mark.parametrize("encoded", ["", "not!base64", "/w==", "AA=="])
def test_base64_config_rejects_empty_invalid_utf8_and_nul(encoded):
    with pytest.raises(ValueError):
        Settings(_env_file=None, auth_username_base64=encoded)


@pytest.mark.parametrize("username", ["", "a\x00b"])
def test_plain_config_requires_nonempty_representable_login_id(username):
    with pytest.raises(ValueError):
        Settings(_env_file=None, auth_username=username)


def test_hash_cli_preserves_literal_username_and_password(monkeypatch, capsys):
    username = "  Luís|ç$${HOME}#'\"\\  "
    password = " x "
    received = []
    monkeypatch.setattr("builtins.input", lambda _prompt: username)
    monkeypatch.setattr(create_auth_hash.getpass, "getpass", lambda _prompt: password)
    monkeypatch.setattr(create_auth_hash, "hash_password", lambda value: received.append(value) or "scrypt$v1$fixture")
    monkeypatch.setattr(create_auth_hash.secrets, "token_urlsafe", lambda _length: "synthetic-session-secret")
    assert create_auth_hash.main() == 0
    assert received == [password]
    output = capsys.readouterr().out
    values = dotenv_values(stream=StringIO(output.split("Add these lines to .env:\n", 1)[1]))
    assert base64.b64decode(values["AUTH_USERNAME_BASE64"]).decode() == username
    assert values["AUTH_PASSWORD_HASH"] == "scrypt$v1$fixture"
    assert values["AUTH_SESSION_SECRET"] == "synthetic-session-secret"
    assert username not in output and password not in output


def test_user_cli_preserves_exact_arguments_without_echoing_login(monkeypatch, capsys):
    username = "  çã| \"$#\\  "
    password = " p "
    create = AsyncMock(return_value=0)
    monkeypatch.setattr(create_user.sys, "argv", ["create_user.py", "--username", username])
    monkeypatch.setattr(create_user.getpass, "getpass", lambda _prompt: password)
    monkeypatch.setattr(create_user, "_create_user", create)
    assert create_user.main() == 0
    create.assert_awaited_once_with(username, "", password)
    captured = capsys.readouterr()
    assert username not in captured.out + captured.err
    assert password not in captured.out + captured.err


@pytest.mark.parametrize("module", [create_user, create_auth_hash])
def test_cli_stops_for_empty_username_before_reading_password(module, monkeypatch, capsys):
    monkeypatch.setattr(module.sys, "argv", [module.__name__])
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt: pytest.fail("Password should not be read"))
    assert module.main() == 1
    assert "Enter a login ID" in capsys.readouterr().err
