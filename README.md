# Investment Assistant — Local Machine

This repository is the local-machine deployment of the same private, local-reasoning
investment assistant architecture as the Raspberry Pi edition. It runs the FastAPI app,
PostgreSQL, local GGUF inference, encrypted per-user brokerage accounts, and Nginx in Docker.

Only Nginx is published on loopback TCP `8080` and `8443` by default; PostgreSQL
and the app remain private inside Docker. Access the UI at:

```text
https://127.0.0.1:8443
```

Restricted LAN access requires an explicit `LOCAL_BIND_ADDRESS` set to the host's
private LAN address, an appropriate generated Nginx allow-list, and verified host
firewall rules. A configuration file is not proof that firewall rules are active.
With approved LAN setup, devices can use `https://investmentsassistant.home.arpa:8443`
after configuring local DNS. Remote access requires separate setup; no public
exposure is configured or authorized here.

The self-signed certificate warning is expected on first use. A local ID/password login is
still required. PostgreSQL stores each user's chat history, profile, preferences, trading mode,
and trade audit rows. Each user can add multiple named Alpaca, IBKR, Coinbase, or Binance
accounts in the UI. Broker credentials are Fernet-encrypted at rest and never sent to the LLM;
accounts are resolved only for the authenticated owner. Users can chat and use market/news/
simulation tools without any broker credentials.

## Requirements

- Docker Engine with the Compose plugin
- A host with enough RAM for the selected GGUF model (the default 1.5B model is about 1 GB)
- OpenSSL for the local certificate
- A GGUF model downloaded into `models/`

Docker Desktop, native Linux Docker, and ARM64 Docker hosts are supported in principle. The
repository cannot validate Docker startup unless Docker is available on the host.

## Setup

```bash
cp .env.example .env
python3 scripts/create_auth_hash.py       # copy the generated values into .env
python3 scripts/create_broker_key.py      # append/copy BROKER_CREDENTIALS_KEY into .env
python3 scripts/download_model.py --list
python3 scripts/download_model.py qwen2.5-1.5b --output-dir ./models
```

Set at least `POSTGRES_PASSWORD`, `AUTH_PASSWORD_HASH`, `AUTH_SESSION_SECRET`,
`BROKER_CREDENTIALS_KEY`, and `LLM_MODEL_PATH` in `.env`. Keep `AUTH_REQUIRE_LOGIN=true`,
`ENVIRONMENT=production`, and `LIVE_TRADING_ENABLED=false` while validating. Broker API keys
are optional and should normally be entered by each user in the authenticated UI. The legacy
broker variables in `.env` are only a compatibility fallback for system/scheduler calls with
no authenticated user.

Deploy:

```bash
make local-deploy
```

For WSL2, Docker Desktop must be running. The deployment is split into
independent Make targets; run `make help` to inspect or rerun individual
stages such as `local-env-check`, `local-model-check`, `local-tls`,
`local-build`, `local-up`, and `local-ready`. If Docker is not the default
executable, pass it explicitly with `make DOCKER=/path/to/docker local-deploy`.
Copy the single-quoted `AUTH_PASSWORD_HASH` line from
`scripts/create_auth_hash.py`; the scrypt hash contains `$` characters that
Compose would otherwise interpolate.

New users can register at `https://127.0.0.1:8443/signup` when
`AUTH_ALLOW_SIGNUP=true`. Registration creates an independent account and signs
the user in immediately. To keep signup private, set `AUTH_ALLOW_SIGNUP=false`
and provision additional local users from the CLI instead:

```bash
docker compose exec app python scripts/create_user.py \
  --username second-user --display-name "Second User"
```

The **Simulation** tab runs fake-money historical backtests locally through the
same simulator used by the agent. It supports buy-and-hold, SMA crossover, RSI
mean reversion, and momentum strategies. It never submits orders to Alpaca,
IBKR, Coinbase, or Binance; only the historical market-data download is external.

The **Weekly Report** action is an agent workflow rather than a generic prompt:
it gathers the authenticated user's available broker data, trade audit, saved
simulations, market snapshot, and news before writing and saving the report.

## Local security boundary

Compose publishes only Nginx and defaults to `127.0.0.1`. PostgreSQL and the app
have no host port mappings. Nginx and application allow-lists provide additional
checks; broad private Docker/WSL source ranges alone cannot establish LAN safety.
Validate actual source addresses and forwarding on the target Docker installation
before enabling LAN ingress. Windows Firewall configuration requires separate
approval and has not been changed during acceptance. Signed sessions and CSRF
protection remain required. Do not create router forwards or enable UPnP.

Container logs rotate at 10 MiB per file with three files per service. This bounds
container stdout/stderr storage, not database/news/report retention. See
[acceptance runbooks](docs/acceptance/RUNBOOK.md) and the
[gate matrix](docs/acceptance/PLAN.md) for tested behavior and remaining limits.

## Persistence and multi-user behavior

Two users may chat concurrently without sharing history, profile context, trading mode, account
credentials, or confirmation tokens. One in-process GGUF model is shared and inference is
serialized, so the expected worst-case degradation is latency while one turn waits for another.
Database and broker/network work is kept off the FastAPI event loop where applicable.

The UI's Brokerage Accounts section supports multiple accounts per provider. Account-specific
operations use the single matching account automatically; if several match, the assistant asks
for the safe account ID. Empty account configuration does not disable the rest of the assistant.

## Useful commands

```bash
make local-status
make local-logs SERVICE=app
make local-logs SERVICE=nginx
make local-down
poetry run ruff check src tests scripts
poetry run pytest -q --ignore=tests/integration
```

The Raspberry Pi/VPN deployment remains documented in the sibling
`investments-assistant-raspberry-pi-5` repository. This repository is intentionally independent
and has no Git remote configured by default.
