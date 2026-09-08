# Local-machine quickstart

## 1. Prepare configuration

```bash
cp .env.example .env
python3 scripts/create_auth_hash.py
python3 scripts/create_broker_key.py
```

Copy the generated authentication values and the `BROKER_CREDENTIALS_KEY` line into `.env`.
Set a strong `POSTGRES_PASSWORD`. Keep `ENVIRONMENT=production`,
`AUTH_REQUIRE_LOGIN=true`, `LIVE_TRADING_ENABLED=false`, and use a model path under
`/app/models/`.

## 2. Add a local model

```bash
python3 scripts/download_model.py --list
python3 scripts/download_model.py qwen2.5-1.5b --output-dir ./models
```

The default Qwen 2.5 1.5B Q4 model is intended for responsive CPU-only local inference.
The 3B and 7B presets remain available when answer quality is more important than latency.

## 3. Deploy

```bash
make local-deploy
```

On WSL2 with Docker Desktop, Docker Desktop must be running. The deployment is
modular: use `make local-env-check`, `make local-model-check`, `make local-tls`,
`make local-build`, `make local-up`, `make local-wait`, or `make local-ready`
when diagnosing a specific stage. Authentication hashes contain `$` characters; copy the
single-quoted `AUTH_PASSWORD_HASH` line printed by `scripts/create_auth_hash.py`
so Docker Compose does not truncate it.

Open `https://127.0.0.1:8443` locally, or
`https://investmentsassistant.home.arpa:8443` from a device on the configured LAN.
Port `8080` redirects to HTTPS. Only Nginx is published; the application and database
remain private to Docker.

## 4. Add users and brokerage accounts

New users can register at `https://127.0.0.1:8443/signup` when
`AUTH_ALLOW_SIGNUP=true`. To disable self-registration and provision an account
privately instead, set `AUTH_ALLOW_SIGNUP=false` and run:

```bash
docker compose exec app python scripts/create_user.py --username analyst
```

After logging in, use **Brokerage Accounts** in the sidebar. Add any number of named Alpaca,
Interactive Brokers, Coinbase, or Binance accounts. Credentials are encrypted before storage,
masked in the UI, and never included in the model prompt. Leave all broker accounts empty if
you only want market, news, ETF, crypto, NFT-risk, and simulation analysis.

If a requested action needs a missing account, the assistant reports the missing capability.
If multiple accounts match a provider, it asks for an account ID instead of guessing.

## 5. Verify

```bash
make local-status
make local-logs SERVICE=app
make local-ready
```

For LAN access, follow [LAN access](wiki/LAN-access.md) before opening the hostname.

The readiness endpoint is internal to the app container and is used by Compose. Full integration
tests require a running PostgreSQL service; focused unit tests can run with:

```bash
poetry run pytest -q --ignore=tests/integration
```

To stop the stack:

```bash
make local-down
```
