#!/usr/bin/env python3
"""Generate the password material used by the Pi browser login.

Usage:
    python3 scripts/create_auth_hash.py

Copy the three printed values into ``.env``.  The password itself is never
written to disk by this script.
"""

from __future__ import annotations

import sys
import base64
import getpass
from pathlib import Path
import secrets

# Make direct execution from the repository root work without requiring an
# editable install or a manually configured PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.web.auth import hash_password  # noqa: E402


def username_environment_line(username: str) -> str:
    """Transport exact text safely across both dotenv and Compose parsers."""
    return "AUTH_USERNAME_BASE64='" + base64.b64encode(username.encode("utf-8")).decode("ascii") + "'"


def main() -> int:
    username = input("Login ID: ")
    if not username:
        print("Enter a login ID.", file=sys.stderr)
        return 1
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        password_hash = hash_password(first)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("\nAdd these lines to .env:\n")
    print(username_environment_line(username))
    # Compose treats `$NAME` as interpolation in unquoted .env values. The
    # scrypt format contains several dollars, so single-quote it for a safe
    # copy/paste into .env. dotenv parsers remove the surrounding quotes.
    print(f"AUTH_PASSWORD_HASH='{password_hash}'")
    print(f"AUTH_SESSION_SECRET={secrets.token_urlsafe(48)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
