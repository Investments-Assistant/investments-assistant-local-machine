# Isolated container validation

The actual amd64 image build passed: `container-build-20261010-ad17fb8e.json`,
`.txt` and `.exit` in the evidence directory. Image:
`investment-assistant:container-build-20261010-ad17fb8e`.
Its source hashes and exported image digest are recorded. This is a local build;
the remote workflow has not run against the uncommitted checkout.

The current `ib_async==2.1.0` candidate also builds successfully as
`investment-assistant:local`; a network-disabled, non-root image smoke confirms
the package and read-only adapter imports. Evidence:
`evidence/container-build-ibasync-20261013.txt`. The separate current-candidate
runtime validation below now also passes.

At the 2026-10-14 checkpoint Docker Desktop is available and the candidate image
exists as `sha256:a64ce3a90cee80e7a93cd6e8e83828c583d3d70b37ff99de0c31ed8f27babe95`.
The pinned PostgreSQL image `postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` is also present locally, and the existing Qwen model is readable with SHA-256
`6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`. The app
image is linux/amd64 and runs as `appuser`. These checks avoided image pulls during
the runtime validation. The isolated runtime/migration/model/restart harness ran
after the 24-hour CPU soak reached terminal status, avoiding competing load:

```sh
.venv/bin/python scripts/verify_container_runtime.py \
  --docker docker \
  --image investment-assistant:local \
  --postgres postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output docs/acceptance/evidence/container-runtime-ibasync-new.json
```

### Current candidate runtime result — 2026-10-14

The command above completed with exit0 and `PASS`. A network-disabled source
comparison confirmed all178 source/migration and copied configuration files in
the cached image match the checkout; see
[source hashes](evidence/container-source-comparison-20261014.json).
The run verified the new database's disposable marker before migrations, actual
production-entrypoint database/model readiness, and a persistent operator halt
that denies new proposals after both application and PostgreSQL restarts.
Application recovery took6.584s and database recovery1.044s, each within the
unchanged15s budget. Image/model digests match the preflight.

[Runtime evidence](evidence/container-runtime-ibasync-new.json), the `.txt` log
and `.exit` record are retained. Runner cleanup passed; a separate read-only
[labelled-resource check](evidence/container-runtime-ibasync-cleanup-20261014.json)
found no owned containers, networks or volumes remaining. No host ports,
production storage, broker connections or external orders were used.
This does not establish LAN/firewall, physical sleep, remote broker/provider
recovery or strategy profitability. Use a new output path for any justified rerun.

A Windows Docker client network-none smoke ran as UID1000, produced a real PDF,
loaded llama.cpp, and checked that `.env`, `.qa` and model files were absent from
the image. GPU offload is unsupported. Library inspection and `ldd` verify the
ggml BLAS backend links OpenBLAS; a cold system-info call alone omitted this
backend and was insufficient to judge linkage. No Dockerfile change followed
that observation. Evidence: `container-native-smoke-windows.txt/.exit` and
`container-openblas-linkage.txt/.exit`.

The first native WSL runtime command failed before container startup because WSL
integration disappeared. The direct Windows client remained available; no image
rebuild was needed. Preserve that failed command as environment evidence, not an
application test failure.

## Production startup and restart runner

`scripts/verify_container_runtime.py` creates uniquely named, labelled internal
network, volume and PostgreSQL/application containers. It publishes no host ports
and mounts no production storage. It positively verifies the new test database
name and random disposable marker before explicit migrations. It copies an
existing local model into the owned application container, starts the production
entrypoint, checks real database/model readiness, and restarts the application
and database separately. The existing15-second restart budget is enforced.
Only identifiers returned by its own creates are removed during cleanup.

```sh
.venv/bin/python scripts/verify_container_runtime.py \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe' \
  --image investment-assistant:container-build-20261010-ad17fb8e \
  --postgres postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output docs/acceptance/evidence/container-runtime-new.json
```

Use a new output path. Inspect a previous run's live process/terminal result and
owned resource names before retrying. This tier does not establish Nginx/LAN
ingress, broker/provider connectivity, model answer quality, OS sleep or24hours
of stability. Readiness and marker persistence are not evidence of trading-state
reconciliation. Actual acceptance results remain in the named JSON/exit records.

The initial runtime attempt failed because a Unix-socket readiness check raced
PostgreSQL's temporary initialization server shutdown. Its resources were cleaned.
The runner now waits for the final TCP listener; the reproduction remains in
`container-runtime-20261010.json/.txt/.exit`. Do not classify an active retry as
PASS before its checks and cleanup finish.

## Verified recovery after startup import repair

v2 FAILED: application23.143s exceeded the fixed15s budget; database2.177s,
marker/schema persistence and cleanup succeeded. Import profiling found
market-data dependencies eagerly loaded during service startup. Their imports
now occur in synchronous data/simulation operations. The failing startup import
regression and47focusedPASS are preserved.

Updatedimage `investment-assistant:container-startup-20261010` builds successfully.
v3 PASS: application12.986s, database1.777s, realGGUF readiness and persisted
operatorhalt. The fixture invokes the actual halt service and verifies a new
proposal is denied OPERATOR_HALTED after each restart, with cash/reserve unchanged.
Cleanup passed. See `container-runtime-20261010-v3.json/.txt/.exit` and
`container-startup-review.json` for scope, image/model/source hashes. This short
run is not24h, thermal, physicalsleep, externalbroker or Dockeringress acceptance.

## Docker Desktop ingress (2026-10-10)

`container-ingress-20261010-v2.json/.txt/.exit` records PASS for the pinned
Nginx image, real application authentication/routes and a marked disposable
PostgreSQL database. Inference/providers are explicit fixtures. Verified TLS,
static success/error security headers, redirects, trusted proxy identity,
authenticated WSS and origin/authentication denials passed. A separate
non-allowlisted container received HTTPS403.

Windows curl verified the fixture certificate through a temporary port bound
only to127.0.0.1. The application observed172.18.0.1 (the Docker bridge gateway),
not the physical Windows client address. Do not treat this address as proof of
a LAN boundary. The fixture permits only its exact app/gateway addresses and
trusts only its exact Nginx peer. No firewall setting changed. All owned
containers, anonymous volumes and networks were removed.

The first attempt used an internal-only network, on which Docker suppressed
the published port. It passed five container-level checks but is preserved as
FAIL. The successful fixture matches Compose's bridge topology; it has no
production mounts, provider credentials or scheduler and explicitly rejects
broker connections. The bridge is not an egress-isolation claim.

Reproduce with a new output path:

```sh
.venv/bin/python scripts/verify_container_ingress.py \
  --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe' \
  --image investment-assistant:container-startup-20261010 \
  --postgres postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea \
  --nginx nginx:alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2 \
  --output docs/acceptance/evidence/container-ingress-new.json
```

## Security-updated image validation

The approved cd049bf image `investment-assistant:security-cd049bf` built with manifest `5f56ad6fd7a50fb91edd085f55a5ab8d60d25aa8ab2805713128ea710a0eb626`. Native non-root/PDF/CPU-library checks pass. Actual GGUF startup and restart checks pass: app10.954s, database1.615s within the unchanged15s budget, persistent halt denies proposals after both restarts, and owned-resource cleanup is verified. See [runtime evidence](evidence/container-runtime-security.json) and [build provenance](evidence/container-security-review.json).

[Current-image ingress](evidence/container-ingress-security.json) also passes all seven checks with cleanup verified. Windows loopback forwarding still exposes the Docker bridge gateway to the application. This is not LAN/firewall, physical sleep, thermal or24h acceptance. No real broker connection or order occurred.
