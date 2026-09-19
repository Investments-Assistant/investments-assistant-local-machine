#!/usr/bin/env bash
# Explicit disposable fixture, never a system service or production database.
set -euo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
fixture_root="$repo_dir/.qa"
export LD_LIBRARY_PATH="$fixture_root/postgres-root/usr/lib/x86_64-linux-gnu"
fixture_bin="$fixture_root/postgres-root/usr/lib/postgresql/16/bin"
mkdir -p "$fixture_root/socket"
chmod 700 "$fixture_root/socket"
if [[ ! -x "$fixture_bin/pg_ctl" ]]; then
  printf '%s\n' 'Extract PostgreSQL 16 packages under .qa/postgres-root first.' >&2
  exit 1
fi
if [[ ! -d "$fixture_root/pgdata" ]]; then
  "$fixture_bin/initdb" -D "$fixture_root/pgdata" --auth-local=trust --auth-host=reject --no-locale -E UTF8 > "$fixture_root/initdb.log"
fi
if "$fixture_bin/pg_ctl" -D "$fixture_root/pgdata" status >/dev/null 2>&1; then
  printf '%s\n' 'Owned disposable PostgreSQL is already running.'
else
  "$fixture_bin/pg_ctl" -D "$fixture_root/pgdata" -l "$fixture_root/postgres.log" -o "-k $fixture_root/socket -p 55439 -c listen_addresses=''" -w start
fi
