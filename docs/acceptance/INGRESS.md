# Isolated Nginx ingress verification

2026-10-09: seven checks PASS using an actual Ubuntu Nginx 1.24.0 binary,
OpenSSL, Uvicorn, application authentication/WebSocket routes and marked
PostgreSQL. Model responses and provider connections use the existing fixtures.

Verified TLS certificate validation, security headers, path/query/port-preserving
HTTP redirect, forwarded scheme and real-IP replacement, authenticated same-origin
WSS, rejection of invalid/missing origins and missing authentication, and HTTPS
denial for the non-allowlisted loopback source 127.0.0.2.

Evidence: [result](evidence/nginx-ingress-20261009-v3.json),
[exit](evidence/nginx-ingress-20261009-v3.exit),
[versions and source hashes](evidence/nginx-ingress-20261009-review.json).
Earlier failed fixture attempts remain saved: v1 lacked isolated temporary paths;
v2 generated a session ID longer than the application's existing limit. Both
fixture defects were corrected without changing application security controls.

Run from the checkout with the existing isolated database and extracted binary:

```sh
TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_browser_expenses?host=$PWD/.qa/socket&port=55439" \
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 \
.venv/bin/python scripts/verify_nginx_ingress.py \
  --nginx .qa/nginx-root/usr/sbin/nginx \
  --output docs/acceptance/evidence/nginx-ingress-new.json
```

The output path must be new. The runner verifies the database marker and migration
before seeding synthetic users. It binds only loopback, creates a short-lived
certificate trusted only by its clients, stores temporary files under `.qa`, and
terminates its own processes. No system package/service, firewall, certificate
store, production instance, or broker account is changed.

Production Nginx directives are used with fixture ports, certificate paths,
upstream address and allowlist include. The fixture application trusts only the
exact loopback proxy peer. This is not verification of Compose's `nginx:alpine`
image, Docker/WSL forwarding, real LAN clients/firewall, or production certificate
trust. Those deployment checks remain pending.

## Static-response regression repaired

The added success/404 static-response checks reproduced missing security headers
(`nginx-static-reproduction.exit1`). A location-level `add_header Cache-Control`
suppressed the server headers under Nginx inheritance rules. Replaced it with
`expires 1h`: successful assets retain a one-hour cache, while both success and
error responses inherit all four security headers. No newer-version-only
`add_header_inherit` directive is required. Primary reference:
https://nginx.org/en/docs/http/ngx_http_headers_module.html

All eight checks now PASS: [result](evidence/nginx-static-verified.json),
[exit](evidence/nginx-static-verified.exit),
[current hashes](evidence/nginx-static-review.json). Docker/WSL/LAN limits above
still apply. The previous seven-check result predates this configuration repair.

## CI regression coverage

The browser job now targets Ubuntu24.04 and runs this actual ingress harness after
the Chromium workflow, using the same marked/migrated disposable PostgreSQL
service. It downloads/extracts Ubuntu Nginx without installing or starting a
system service, records package SHA256 and binary version, and uploads the ingress
result/log alongside explicit synthetic browser PNGs and the fixture server log.
The package is the runner's repository candidate, recorded per run, not a claim
of validating the Compose image. Repository/package outages fail the step.

The screenshot path was corrected from `/tmp/ia-browser-evidence` to the runner's
`.qa/browser-evidence`; hidden-file inclusion is scoped to the listed synthetic
files. The runner now creates missing parent directories on fresh checkouts.
Local YAML/shell syntax and fresh-directory preflight checks pass in
`evidence/ci-ingress-wiring-review.json`. The full real browser rerun passes in
`evidence/browser-ci-ingress-wiring.txt` (exit0). The remote workflow has not run
against these uncommitted changes; no upload or publication was performed here.
